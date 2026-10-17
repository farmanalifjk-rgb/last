from rest_framework import generics, status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import (
    Tenant, TenantMembership, SubscriptionPlan, Subscription,
    Invoice, TenantUsage,
)
from .serializers import (
    TenantSerializer, TenantMembershipSerializer, SubscriptionPlanSerializer,
    SubscriptionSerializer, InvoiceSerializer, CreateTenantSerializer,
    SwitchTenantSerializer,
)
from .permissions import HasActiveTenant, TenantRBACPermission
from .services import (
    provision_tenant, get_active_tenant_for_user, switch_active_tenant,
    capture_usage, enforce_limit,
    LimitExceeded,
)


def _ensure_membership(user, tenant, min_role=None):
    m = TenantMembership.objects.filter(user=user, tenant=tenant).first()
    if not m and not user.is_superuser:
        return None
    return m


class PlanListView(generics.ListAPIView):
    """Public: list active, public subscription plans."""
    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle]
    serializer_class = SubscriptionPlanSerializer

    def get_queryset(self):
        return SubscriptionPlan.objects.filter(is_active=True, is_public=True)


class TenantMeView(APIView):
    """Current tenant + subscription + usage for the logged-in user."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenant = get_active_tenant_for_user(request.user)
        if not tenant:
            return Response({"detail": "No active tenant."}, status=404)
        usage = capture_usage(tenant)
        sub = getattr(tenant, "subscription", None)
        return Response({
            "tenant": TenantSerializer(tenant).data,
            "subscription": SubscriptionSerializer(sub).data if sub else None,
            "usage": usage,
        })


class CreateTenantView(APIView):
    """Self-service tenant provisioning (sign-up)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """List only the current user's active canonical SaaS tenants for the switcher."""
        memberships = TenantMembership.objects.filter(
            user=request.user,
            tenant__is_active=True,
        ).select_related("tenant").order_by("tenant__name")
        data = []
        for membership in memberships:
            tenant = TenantSerializer(membership.tenant).data
            tenant["is_active_in_tenant"] = membership.is_active_in_tenant
            data.append(tenant)
        return Response(data)

    def post(self, request):
        ser = CreateTenantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        if Tenant.objects.filter(slug=d["slug"]).exists():
            return Response({"detail": "Slug already taken."}, status=400)
        tenant = provision_tenant(name=d["name"], slug=d["slug"],
                                  owner=request.user, plan_slug=d["plan_slug"])
        return Response(TenantSerializer(tenant).data, status=201)


class SwitchTenantView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = SwitchTenantSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            tenant = switch_active_tenant(request.user, ser.validated_data["tenant_id"])
        except TenantMembership.DoesNotExist:
            # Previously an unhandled 500. Same answer for "does not exist" and
            # "not yours" so tenant ids cannot be probed.
            return Response(
                {"detail": "You are not a member of that business, or it is inactive."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(TenantSerializer(tenant).data)


class TenantMembersView(generics.ListCreateAPIView):
    """Members of the caller's active tenant.

    GET lists the active tenant's memberships. POST adds a member and is
    restricted: before 2026-10-11 any authenticated user could POST
    ``{"tenant": <any id>, "user": <self>, "role": "owner"}`` and take over
    an arbitrary tenant. Now only an owner/admin of the *active* tenant (or a
    superuser) may add members, always to that tenant, never as owner (an
    ownership transfer is a business decision outside this endpoint), and the
    new member's active-tenant selection is never changed.
    """

    serializer_class = TenantMembershipSerializer
    permission_classes = [IsAuthenticated]
    MANAGER_ROLES = {TenantMembership.ROLE_OWNER, TenantMembership.ROLE_ADMIN}

    def get_queryset(self):
        tenant = get_active_tenant_for_user(self.request.user)
        if not tenant:
            return TenantMembership.objects.none()
        return TenantMembership.objects.filter(tenant=tenant).select_related("user")

    def create(self, request, *args, **kwargs):
        from django.db import IntegrityError, transaction

        from audit.recorder import record

        user = request.user
        tenant = get_active_tenant_for_user(user)
        if tenant is None:
            return Response({"detail": "No active tenant."}, status=status.HTTP_403_FORBIDDEN)
        caller = TenantMembership.objects.filter(tenant=tenant, user=user).first()
        if not user.is_superuser and (caller is None or caller.role not in self.MANAGER_ROLES):
            return Response(
                {"detail": "Only an owner or admin of the active business can add members."},
                status=status.HTTP_403_FORBIDDEN,
            )
        requested_tenant = request.data.get("tenant")
        if requested_tenant not in (None, "") and str(requested_tenant) != str(tenant.pk):
            return Response(
                {"tenant": ["Members can only be added to your active business."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        serializer = self.get_serializer(data={**request.data, "tenant": tenant.pk, "is_active_in_tenant": False})
        serializer.is_valid(raise_exception=True)
        if serializer.validated_data.get("role") == TenantMembership.ROLE_OWNER:
            return Response(
                {"role": ["The owner role cannot be granted here."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            with transaction.atomic():
                membership = serializer.save(tenant=tenant, is_active_in_tenant=False)
                record(
                    actor=user, action="saas.membership.created", instance=membership,
                    request=request, tenant=tenant, summary="Added a business member.",
                    after={"user": membership.user_id, "role": membership.role},
                )
        except IntegrityError:
            return Response(
                {"user": ["This user is already a member of the active business."]},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(self.get_serializer(membership).data, status=status.HTTP_201_CREATED)


class SubscriptionCheckoutView(APIView):
    rbac_module = "billing"
    rbac_action = "manage"
    """Start a Stripe Checkout session to subscribe/upgrade the current plan."""
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def post(self, request):
        return Response(
            {"detail": "Online SaaS subscription checkout is not enabled. Submit a configured manual payment through the billing workflow."},
            status=status.HTTP_410_GONE,
        )


class CancelSubscriptionView(APIView):
    rbac_module = "billing"
    rbac_action = "manage"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def post(self, request):
        tenant = get_active_tenant_for_user(request.user)
        if not tenant or not getattr(tenant, "subscription", None):
            return Response({"detail": "No subscription."}, status=404)
        sub = tenant.subscription
        sub.cancel_at_period_end = True
        sub.save(update_fields=["cancel_at_period_end"])
        return Response(SubscriptionSerializer(sub).data)


class InvoicesView(generics.ListAPIView):
    rbac_module = "billing"
    rbac_action = "view"
    serializer_class = InvoiceSerializer
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def get_queryset(self):
        tenant = get_active_tenant_for_user(self.request.user)
        if not tenant:
            return Invoice.objects.none()
        return Invoice.objects.filter(tenant=tenant).select_related("subscription")


class LimitCheckView(APIView):
    """Internal-ish endpoint used by create forms to pre-validate plan limits."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        metric = request.query_params.get("metric")
        tenant = get_active_tenant_for_user(request.user)
        if not tenant:
            return Response({"allowed": True})
        try:
            enforce_limit(tenant, metric)
            return Response({"allowed": True})
        except LimitExceeded as e:
            return Response({"allowed": False, "limit": e.limit, "current": e.current}, status=402)


@permission_classes([AllowAny])
class StripeWebhookView(APIView):
    """Receives Stripe events. Expects the raw signed payload forwarded by urls.py."""
    throttle_classes = [AnonRateThrottle]
    def post(self, request):
        return Response(
            {"detail": "SaaS subscription provider webhooks are disabled for the manual/offline billing release."},
            status=status.HTTP_410_GONE,
        )

