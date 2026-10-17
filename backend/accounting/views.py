"""Tenant-scoped, RBAC-enforced accounting APIs and compatibility reporting reads."""

from decimal import Decimal

from django.db import IntegrityError
from django.db.models import Q, Sum
from rest_framework import serializers, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounting.models import (
    AccountingEvent,
    AccountingEventStatus,
    AccountType,
    AccountingPeriod,
    ChartOfAccount,
    Expense,
    ExpenseCategory,
    FinancialAccountMapping,
    FinancialStatementRole,
    JournalEntry,
    JournalEntryLine,
    PostingRule,
)
from accounting.services import (
    AccountingValidationError,
    close_accounting_period,
    create_journal_draft,
    post_journal_entry,
    post_expense_to_journal,
    post_accounting_event,
    replace_journal_lines,
    reverse_accounting_event,
    reverse_journal_entry,
    transition_expense,
)
from audit.recorder import record, snapshot
from saas.permissions import HasActiveTenant, TenantRBACPermission, TenantScopedViewSetMixin

ZERO = Decimal("0.00")


def money_text(value):
    """Return deterministic decimal strings rather than lossy float JSON values."""
    return str((value or ZERO).quantize(Decimal("0.01")))


def view_error(exc):
    raise ValidationError({"detail": str(exc)})


class AccountSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    balance = serializers.SerializerMethodField()
    children = serializers.SerializerMethodField()

    class Meta:
        model = ChartOfAccount
        fields = ["id", "tenant", "code", "name", "type", "parent", "description", "is_active", "created_at", "balance", "children"]
        read_only_fields = ["tenant", "balance", "children"]

    def validate_parent(self, parent):
        request = self.context["request"]
        if parent and parent.tenant_id != request.tenant.id:
            raise serializers.ValidationError("The parent account must belong to the active tenant.")
        instance = self.instance
        if parent and instance:
            node = parent
            while node:
                if node.pk == instance.pk:
                    raise serializers.ValidationError("An account hierarchy cannot contain a cycle.")
                node = node.parent
        return parent

    def get_balance(self, obj):
        return money_text(obj.balance)

    def get_children(self, obj):
        return AccountSerializer(obj.children.all(), many=True, context=self.context).data


class JournalLineSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    account_name = serializers.CharField(source="account.name", read_only=True)
    account_code = serializers.CharField(source="account.code", read_only=True)

    class Meta:
        model = JournalEntryLine
        fields = ["id", "tenant", "entry", "account", "account_name", "account_code", "description", "debit", "credit"]
        read_only_fields = ["id", "account_name", "account_code"]


class JournalEntrySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    lines = JournalLineSerializer(many=True, read_only=True)
    is_balanced = serializers.BooleanField(read_only=True)
    created_by_name = serializers.SerializerMethodField()
    posted_by_name = serializers.SerializerMethodField()
    reversal_of_reference = serializers.CharField(source="reversal_of.reference", read_only=True, default=None)
    reversal_reference = serializers.CharField(source="reversal.reference", read_only=True, default=None)
    source_event_id = serializers.SerializerMethodField()
    source_event_type = serializers.SerializerMethodField()
    source_reference = serializers.SerializerMethodField()

    class Meta:
        model = JournalEntry
        fields = [
            "id", "reference", "date", "description", "status", "is_auto_posted", "is_balanced",
            "created_by", "created_by_name", "posted_by", "posted_by_name", "posted_at", "created_at",
            "reversal_of", "reversal_of_reference", "reversal_reference", "source_event_id", "source_event_type", "source_reference", "lines",
        ]
        read_only_fields = [
            "status", "is_auto_posted", "created_by", "posted_by", "posted_at", "created_at",
            "reversal_of", "lines",
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.get_full_name() or obj.created_by.username if obj.created_by else None

    def get_posted_by_name(self, obj):
        return obj.posted_by.get_full_name() or obj.posted_by.username if obj.posted_by else None

    def get_source_event_id(self, obj):
        return getattr(getattr(obj, "accounting_event", None), "id", None)

    def get_source_event_type(self, obj):
        return getattr(getattr(obj, "accounting_event", None), "event_type", None)

    def get_source_reference(self, obj):
        return getattr(getattr(obj, "accounting_event", None), "source_reference", None)


class ExpenseCategorySerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    class Meta:
        model = ExpenseCategory
        fields = ["id", "tenant", "name", "description"]
        read_only_fields = ["id", "tenant"]


class ExpenseSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    category_name = serializers.CharField(source="category.name", read_only=True)
    paid_by_name = serializers.SerializerMethodField()
    journal_reference = serializers.CharField(source="journal_entry.reference", read_only=True, default=None)

    class Meta:
        model = Expense
        fields = [
            "id", "category", "category_name", "amount", "description", "date", "paid_by", "paid_by_name",
            "receipt_image", "status", "journal_entry", "journal_reference", "created_at",
        ]
        read_only_fields = ["id", "tenant", "created_at"]

    def validate_category(self, category):
        if category.tenant_id != self.context["request"].tenant.id:
            raise serializers.ValidationError("The expense category must belong to the active tenant.")
        return category

    def get_paid_by_name(self, obj):
        return obj.paid_by.get_full_name() or obj.paid_by.username if obj.paid_by else None


class AccountingPeriodSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    closed_by_name = serializers.SerializerMethodField()

    class Meta:
        model = AccountingPeriod
        fields = ["id", "tenant", "code", "start_date", "end_date", "status", "closed_at", "closed_by", "closed_by_name", "created_at"]
        read_only_fields = ["id", "tenant", "status", "closed_at", "closed_by", "created_at"]

    def validate(self, attrs):
        start = attrs.get("start_date", getattr(self.instance, "start_date", None))
        end = attrs.get("end_date", getattr(self.instance, "end_date", None))
        if start and end and end < start:
            raise serializers.ValidationError({"end_date": "Period end date must be on or after its start date."})
        if start and end:
            query = AccountingPeriod.objects.filter(
                tenant=self.context["request"].tenant,
                start_date__lte=end,
                end_date__gte=start,
            )
            if self.instance:
                query = query.exclude(pk=self.instance.pk)
            if query.exists():
                raise serializers.ValidationError({"start_date": "Accounting periods for a tenant must not overlap."})
        return attrs

    def get_closed_by_name(self, obj):
        return obj.closed_by.get_full_name() or obj.closed_by.username if obj.closed_by else None


class PostingRuleSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    debit_account_name = serializers.CharField(source="debit_account.name", read_only=True)
    credit_account_name = serializers.CharField(source="credit_account.name", read_only=True)

    class Meta:
        model = PostingRule
        fields = [
            "id", "event_type", "source_key", "source_value", "name", "debit_account", "debit_account_name",
            "credit_account", "credit_account_name", "currency", "is_active", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant = self.context["request"].tenant
        debit = attrs.get("debit_account", getattr(self.instance, "debit_account", None))
        credit = attrs.get("credit_account", getattr(self.instance, "credit_account", None))
        source_key = attrs.get("source_key", getattr(self.instance, "source_key", ""))
        source_value = attrs.get("source_value", getattr(self.instance, "source_value", ""))
        if not debit or debit.tenant_id != tenant.id or not debit.is_active:
            raise serializers.ValidationError({"debit_account": "Choose an active debit account in the active tenant."})
        if not credit or credit.tenant_id != tenant.id or not credit.is_active:
            raise serializers.ValidationError({"credit_account": "Choose an active credit account in the active tenant."})
        if debit.id == credit.id:
            raise serializers.ValidationError({"credit_account": "Debit and credit accounts must be different."})
        if bool(source_key) != bool(source_value):
            raise serializers.ValidationError({"source_key": "Source key and source value must be supplied together."})
        return attrs


class FinancialAccountMappingSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    account_code = serializers.CharField(source="account.code", read_only=True)
    account_name = serializers.CharField(source="account.name", read_only=True)
    role_label = serializers.CharField(source="get_role_display", read_only=True)

    class Meta:
        model = FinancialAccountMapping
        fields = [
            "id", "account", "account_code", "account_name", "role", "role_label",
            "is_active", "notes", "created_at", "updated_at",
        ]
        read_only_fields = ["id", "tenant", "created_at", "updated_at"]

    def validate(self, attrs):
        tenant = self.context["request"].tenant
        account = attrs.get("account", getattr(self.instance, "account", None))
        role = attrs.get("role", getattr(self.instance, "role", None))
        if not account or account.tenant_id != tenant.id or not account.is_active:
            raise serializers.ValidationError({"account": "Choose an active account in the active tenant."})
        required_types = {
            FinancialStatementRole.COGS: AccountType.EXPENSE,
            FinancialStatementRole.OPERATING_EXPENSE: AccountType.EXPENSE,
            FinancialStatementRole.OTHER_EXPENSE: AccountType.EXPENSE,
            FinancialStatementRole.OTHER_INCOME: AccountType.REVENUE,
            FinancialStatementRole.CASH_BANK: AccountType.ASSET,
            FinancialStatementRole.RETAINED_EARNINGS: AccountType.EQUITY,
        }
        if role not in required_types or account.type != required_types[role]:
            raise serializers.ValidationError({"account": "The selected account type is not valid for this financial statement role."})
        return attrs


class AccountingEventSerializer(serializers.ModelSerializer):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    event_label = serializers.CharField(source="get_event_type_display", read_only=True)
    status_label = serializers.CharField(source="get_status_display", read_only=True)
    rule_name = serializers.CharField(source="rule.name", read_only=True, default=None)
    journal_reference = serializers.CharField(source="journal_entry.reference", read_only=True, default=None)
    reversal_event_id = serializers.IntegerField(source="reversal_of_id", read_only=True)

    class Meta:
        model = AccountingEvent
        fields = [
            "id", "source_domain", "event_type", "event_label", "source_id", "source_reference", "event_date",
            "currency", "amount", "status", "status_label", "rule", "rule_name", "journal_entry", "journal_reference",
            "reversal_of", "reversal_event_id", "exception_reason", "posted_at", "created_at", "updated_at",
        ]
        read_only_fields = fields


class AccountingRBACMixin:
    rbac_module = "accounting"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]

    def get_permissions(self):
        action_map = {
            "create_with_lines": "create",
            "replace_lines": "update",
            "post": "post",
            "reverse": "post",
            "approve": "update",
            "reject": "update",
            "post_to_journal": "post",
            "close": "manage",
            "destroy": "manage",
            "retry": "post",
            "reverse_event": "post",
        }
        self.rbac_action = action_map.get(getattr(self, "action", None))
        return [permission() for permission in self.permission_classes]


class ChartOfAccountViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    queryset = ChartOfAccount.objects.all()
    serializer_class = AccountSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        account_type = self.request.query_params.get("type")
        if account_type:
            qs = qs.filter(type=account_type)
        if self.request.query_params.get("root"):
            qs = qs.filter(parent__isnull=True)
        return qs.select_related("parent").prefetch_related("children")

    def perform_create(self, serializer):
        account = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=account, request=self.request, summary="Created chart account", icon="book-open-check", after=snapshot(account))

    def perform_update(self, serializer):
        account = self.get_object()
        if account.journal_lines.filter(entry__status=JournalEntry.STATUS_POSTED).exists():
            immutable = {"code", "type", "parent"}
            if immutable.intersection(serializer.validated_data):
                raise ValidationError({"detail": "Account code, type, and hierarchy are locked after posted activity exists."})
        before = snapshot(account)
        account = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=account, request=self.request, summary="Updated chart account", icon="book-open-check", before=before, after=snapshot(account))

    def destroy(self, request, *args, **kwargs):
        account = self.get_object()
        if account.children.exists() or account.journal_lines.exists():
            raise ValidationError({"detail": "Accounts with child accounts or journal history cannot be deleted; deactivate them instead."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=account, request=request, summary="Deleted empty chart account", icon="book-open-check", before=snapshot(account))
        return super().destroy(request, *args, **kwargs)


class JournalEntryViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "manage"
    queryset = JournalEntry.objects.prefetch_related("lines__account").all()
    serializer_class = JournalEntrySerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if start := self.request.query_params.get("start"):
            qs = qs.filter(date__gte=start)
        if end := self.request.query_params.get("end"):
            qs = qs.filter(date__lte=end)
        if entry_status := self.request.query_params.get("status"):
            qs = qs.filter(status=entry_status)
        return qs.select_related("created_by", "posted_by", "reversal_of")

    def create(self, request, *args, **kwargs):
        try:
            entry = create_journal_draft(tenant=request.tenant, data=request.data, user=request.user, request=request)
        except (AccountingValidationError, IntegrityError) as exc:
            view_error(exc)
        return Response(self.get_serializer(entry).data, status=status.HTTP_201_CREATED)

    @action(detail=False, methods=["post"], url_path="create-with-lines")
    def create_with_lines(self, request):
        return self.create(request)

    def perform_update(self, serializer):
        entry = self.get_object()
        if entry.status == JournalEntry.STATUS_POSTED:
            raise ValidationError({"detail": "Posted journal entries are immutable; create a reversal instead."})
        before = snapshot(entry)
        entry = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=entry, request=self.request, summary="Updated journal draft", icon="book-open-check", before=before, after=snapshot(entry))

    def destroy(self, request, *args, **kwargs):
        entry = self.get_object()
        if entry.status == JournalEntry.STATUS_POSTED:
            raise ValidationError({"detail": "Posted journal entries are immutable; create a reversal instead."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=entry, request=request, summary="Deleted journal draft", icon="book-open-check", before=snapshot(entry))
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def post(self, request, pk=None):
        try:
            entry = post_journal_entry(tenant=request.tenant, entry_id=pk, user=request.user, request=request)
        except (AccountingValidationError, JournalEntry.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"], url_path="replace-lines")
    def replace_lines(self, request, pk=None):
        try:
            entry = replace_journal_lines(tenant=request.tenant, entry_id=pk, raw_lines=request.data.get("lines"), user=request.user, request=request)
        except (AccountingValidationError, JournalEntry.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(entry).data)

    @action(detail=True, methods=["post"])
    def reverse(self, request, pk=None):
        try:
            reversal = reverse_journal_entry(
                tenant=request.tenant,
                entry_id=pk,
                reversal_date=request.data.get("date"),
                description=request.data.get("description", ""),
                user=request.user,
                request=request,
            )
        except (AccountingValidationError, JournalEntry.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(reversal).data, status=status.HTTP_201_CREATED)


class ExpenseCategoryViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    queryset = ExpenseCategory.objects.all()
    serializer_class = ExpenseCategorySerializer

    def perform_create(self, serializer):
        category = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=category, request=self.request, summary="Created expense category", icon="receipt-text", after=snapshot(category))

    def perform_update(self, serializer):
        category = self.get_object()
        before = snapshot(category)
        category = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=category, request=self.request, summary="Updated expense category", icon="receipt-text", before=before, after=snapshot(category))

    def destroy(self, request, *args, **kwargs):
        category = self.get_object()
        if category.expenses.exists():
            raise ValidationError({"detail": "Expense categories with expense history cannot be deleted."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=category, request=request, summary="Deleted expense category", icon="receipt-text", before=snapshot(category))
        return super().destroy(request, *args, **kwargs)


class ExpenseViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    queryset = Expense.objects.select_related("category", "paid_by", "journal_entry").all()
    serializer_class = ExpenseSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if category := self.request.query_params.get("category"):
            qs = qs.filter(category_id=category)
        if expense_status := self.request.query_params.get("status"):
            qs = qs.filter(status=expense_status)
        if start := self.request.query_params.get("start"):
            qs = qs.filter(date__gte=start)
        if end := self.request.query_params.get("end"):
            qs = qs.filter(date__lte=end)
        return qs

    def perform_create(self, serializer):
        expense = serializer.save(tenant=self.request.tenant, paid_by=self.request.user)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=expense, request=self.request, summary="Created pending expense", icon="receipt-text", after=snapshot(expense))

    def perform_update(self, serializer):
        expense = self.get_object()
        if expense.status != Expense.STATUS_PENDING:
            raise ValidationError({"detail": "Only pending expenses may be edited."})
        before = snapshot(expense)
        expense = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=expense, request=self.request, summary="Updated pending expense", icon="receipt-text", before=before, after=snapshot(expense))

    def destroy(self, request, *args, **kwargs):
        expense = self.get_object()
        if expense.status != Expense.STATUS_PENDING:
            raise ValidationError({"detail": "Only pending expenses may be deleted."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=expense, request=request, summary="Deleted pending expense", icon="receipt-text", before=snapshot(expense))
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None):
        self.rbac_action = "update"
        try:
            expense = transition_expense(tenant=request.tenant, expense_id=pk, target_status=Expense.STATUS_APPROVED, user=request.user, request=request)
        except (AccountingValidationError, Expense.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(expense).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        self.rbac_action = "update"
        try:
            expense = transition_expense(tenant=request.tenant, expense_id=pk, target_status=Expense.STATUS_REJECTED, user=request.user, request=request)
        except (AccountingValidationError, Expense.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(expense).data)

    @action(detail=True, methods=["post"], url_path="post-to-journal")
    def post_to_journal(self, request, pk=None):
        try:
            expense = post_expense_to_journal(
                tenant=request.tenant,
                expense_id=pk,
                expense_account_id=request.data.get("expense_account"),
                payment_account_id=request.data.get("payment_account"),
                reference=request.data.get("reference"),
                user=request.user,
                request=request,
            )
        except (AccountingValidationError, Expense.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(expense).data)


class AccountingPeriodViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    queryset = AccountingPeriod.objects.select_related("closed_by").all()
    serializer_class = AccountingPeriodSerializer

    def perform_create(self, serializer):
        period = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=period, request=self.request, summary="Created accounting period", icon="calendar-check-2", after=snapshot(period))

    def perform_update(self, serializer):
        period = self.get_object()
        if period.status == AccountingPeriod.STATUS_CLOSED:
            raise ValidationError({"detail": "Closed accounting periods are immutable."})
        before = snapshot(period)
        period = serializer.save(tenant=self.request.tenant)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=period, request=self.request, summary="Updated accounting period", icon="calendar-check-2", before=before, after=snapshot(period))

    def destroy(self, request, *args, **kwargs):
        period = self.get_object()
        if period.status == AccountingPeriod.STATUS_CLOSED:
            raise ValidationError({"detail": "Closed accounting periods are retained for auditability and cannot be deleted."})
        if JournalEntry.objects.filter(tenant=request.tenant, date__gte=period.start_date, date__lte=period.end_date).exists():
            raise ValidationError({"detail": "Accounting periods with journal history cannot be deleted."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=period, request=request, summary="Deleted empty open accounting period", icon="calendar-check-2", before=snapshot(period))
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def close(self, request, pk=None):
        try:
            period = close_accounting_period(tenant=request.tenant, period_id=pk, user=request.user, request=request)
        except (AccountingValidationError, AccountingPeriod.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(period).data)


class PostingRuleViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    """Manage the tenant-owned mappings consumed only by the canonical posting engine."""

    queryset = PostingRule.objects.select_related("debit_account", "credit_account").all()
    serializer_class = PostingRuleSerializer

    def get_permissions(self):
        self.rbac_action = "view" if self.action in {"list", "retrieve"} else "manage"
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        rule = serializer.save(tenant=self.request.tenant, created_by=self.request.user, updated_by=self.request.user)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=rule, request=self.request, summary="Created accounting posting rule", icon="git-branch", after=snapshot(rule))

    def perform_update(self, serializer):
        rule = self.get_object()
        before = snapshot(rule)
        rule = serializer.save(tenant=self.request.tenant, updated_by=self.request.user)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=rule, request=self.request, summary="Updated accounting posting rule", icon="git-branch", before=before, after=snapshot(rule))

    def destroy(self, request, *args, **kwargs):
        rule = self.get_object()
        if rule.events.exists():
            raise ValidationError({"detail": "Rules with accounting-event history cannot be deleted; deactivate them instead."})
        record(tenant=request.tenant, actor=request.user, action="delete", instance=rule, request=request, summary="Deleted unused accounting posting rule", icon="git-branch", before=snapshot(rule))
        return super().destroy(request, *args, **kwargs)


class FinancialAccountMappingViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    """Controlled account presentation configuration; no role is inferred or auto-created."""

    queryset = FinancialAccountMapping.objects.select_related("account").all()
    serializer_class = FinancialAccountMappingSerializer

    def get_permissions(self):
        self.rbac_action = "view" if self.action in {"list", "retrieve"} else "manage"
        return [permission() for permission in self.permission_classes]

    def perform_create(self, serializer):
        mapping = serializer.save(tenant=self.request.tenant, created_by=self.request.user, updated_by=self.request.user)
        record(tenant=self.request.tenant, actor=self.request.user, action="create", instance=mapping, request=self.request, summary="Configured financial account role", icon="landmark", after=snapshot(mapping))

    def perform_update(self, serializer):
        mapping = self.get_object()
        before = snapshot(mapping)
        mapping = serializer.save(tenant=self.request.tenant, updated_by=self.request.user)
        record(tenant=self.request.tenant, actor=self.request.user, action="update", instance=mapping, request=self.request, summary="Updated financial account role", icon="landmark", before=before, after=snapshot(mapping))

    def destroy(self, request, *args, **kwargs):
        mapping = self.get_object()
        record(tenant=request.tenant, actor=request.user, action="delete", instance=mapping, request=request, summary="Removed financial account role", icon="landmark", before=snapshot(mapping))
        return super().destroy(request, *args, **kwargs)


class AccountingEventViewSet(AccountingRBACMixin, TenantScopedViewSetMixin, viewsets.ReadOnlyModelViewSet):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    """Read and resolve durable event outcomes without permitting arbitrary event edits."""

    queryset = AccountingEvent.objects.select_related("rule", "journal_entry", "reversal_of", "posted_by").all()
    serializer_class = AccountingEventSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        if event_status := self.request.query_params.get("status"):
            qs = qs.filter(status=event_status)
        if event_type := self.request.query_params.get("event_type"):
            qs = qs.filter(event_type=event_type)
        if source_domain := self.request.query_params.get("source_domain"):
            qs = qs.filter(source_domain=source_domain)
        if start := self.request.query_params.get("start"):
            qs = qs.filter(event_date__gte=start)
        if end := self.request.query_params.get("end"):
            qs = qs.filter(event_date__lte=end)
        return qs

    @action(detail=True, methods=["post"])
    def retry(self, request, pk=None):
        try:
            event = post_accounting_event(tenant=request.tenant, event_id=pk, user=request.user, request=request)
        except (AccountingValidationError, AccountingEvent.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(event).data)

    @action(detail=True, methods=["post"], url_path="reverse")
    def reverse_event(self, request, pk=None):
        try:
            event = reverse_accounting_event(
                tenant=request.tenant,
                event_id=pk,
                reversal_date=request.data.get("date"),
                user=request.user,
                request=request,
            )
        except (AccountingValidationError, AccountingEvent.DoesNotExist) as exc:
            view_error(exc)
        return Response(self.get_serializer(event).data, status=status.HTTP_201_CREATED)


class AccountingReportPermissionMixin(APIView):
    rbac_module = "accounting"
    rbac_action = "view"
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]


class LedgerView(AccountingReportPermissionMixin):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    def get(self, request, account_id):
        try:
            account = ChartOfAccount.objects.get(tenant=request.tenant, pk=account_id)
        except ChartOfAccount.DoesNotExist:
            return Response({"detail": "Account not found."}, status=status.HTTP_404_NOT_FOUND)
        lines = JournalEntryLine.objects.filter(
            tenant=request.tenant,
            account=account,
            entry__tenant=request.tenant,
            entry__status=JournalEntry.STATUS_POSTED,
        ).select_related("entry").order_by("entry__date", "id")
        running_balance = ZERO
        result = []
        for line in lines:
            if account.type in [AccountType.ASSET, AccountType.EXPENSE]:
                running_balance += line.debit - line.credit
            else:
                running_balance += line.credit - line.debit
            result.append({
                "date": str(line.entry.date),
                "reference": line.entry.reference,
                "description": line.description or line.entry.description,
                "debit": money_text(line.debit),
                "credit": money_text(line.credit),
                "balance": money_text(running_balance),
            })
        return Response({"account": AccountSerializer(account, context={"request": request}).data, "lines": result})


class TrialBalanceView(AccountingReportPermissionMixin):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    def get(self, request):
        accounts = ChartOfAccount.objects.filter(tenant=request.tenant).order_by("code")
        rows = []
        total_debit = ZERO
        total_credit = ZERO
        for account in accounts:
            balance = account.balance
            normal_debit = account.type in [AccountType.ASSET, AccountType.EXPENSE]
            debit = balance if normal_debit and balance >= ZERO else -balance if not normal_debit and balance < ZERO else ZERO
            credit = balance if not normal_debit and balance >= ZERO else -balance if normal_debit and balance < ZERO else ZERO
            rows.append({"code": account.code, "name": account.name, "type": account.type, "debit": money_text(debit), "credit": money_text(credit)})
            total_debit += debit
            total_credit += credit
        return Response({"rows": rows, "total_debit": money_text(total_debit), "total_credit": money_text(total_credit)})


class ProfitLossReportView(AccountingReportPermissionMixin):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        revenue_filter = Q(tenant=request.tenant, entry__tenant=request.tenant, entry__status=JournalEntry.STATUS_POSTED, account__type=AccountType.REVENUE)
        expense_filter = Q(tenant=request.tenant, entry__tenant=request.tenant, entry__status=JournalEntry.STATUS_POSTED, account__type=AccountType.EXPENSE)
        if start:
            revenue_filter &= Q(entry__date__gte=start)
            expense_filter &= Q(entry__date__gte=start)
        if end:
            revenue_filter &= Q(entry__date__lte=end)
            expense_filter &= Q(entry__date__lte=end)
        revenue_agg = JournalEntryLine.objects.filter(revenue_filter).aggregate(credits=Sum("credit"), debits=Sum("debit"))
        expense_agg = JournalEntryLine.objects.filter(expense_filter).aggregate(debits=Sum("debit"), credits=Sum("credit"))
        revenue = (revenue_agg["credits"] or ZERO) - (revenue_agg["debits"] or ZERO)
        expenses_total = (expense_agg["debits"] or ZERO) - (expense_agg["credits"] or ZERO)
        cogs = Expense.objects.filter(tenant=request.tenant, status=Expense.STATUS_APPROVED, category__name__icontains="cost of goods")
        if start:
            cogs = cogs.filter(date__gte=start)
        if end:
            cogs = cogs.filter(date__lte=end)
        cogs_total = cogs.aggregate(total=Sum("amount"))["total"] or ZERO
        gross_profit = revenue - cogs_total
        net_profit = gross_profit - expenses_total
        return Response({
            "revenue": money_text(revenue), "cogs": money_text(cogs_total), "gross_profit": money_text(gross_profit),
            "expenses": money_text(expenses_total), "net_profit": money_text(net_profit),
            "income_breakdown": [], "expense_breakdown": [],
        })


class BalanceSheetView(AccountingReportPermissionMixin):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    def get(self, request):
        def section(account_type):
            accounts = ChartOfAccount.objects.filter(tenant=request.tenant, type=account_type).order_by("code")
            rows = [{"code": account.code, "name": account.name, "balance": money_text(account.balance)} for account in accounts]
            total = sum((Decimal(row["balance"]) for row in rows), ZERO)
            return {"rows": rows, "total": money_text(total)}
        return Response({"assets": section(AccountType.ASSET), "liabilities": section(AccountType.LIABILITY), "equity": section(AccountType.EQUITY)})


class CashFlowReportView(AccountingReportPermissionMixin):
    permission_classes = [IsAuthenticated, HasActiveTenant, TenantRBACPermission]
    rbac_module = "accounting"
    rbac_action = "view"
    def get(self, request):
        start = request.query_params.get("start")
        end = request.query_params.get("end")
        revenue_filter = Q(tenant=request.tenant, entry__tenant=request.tenant, entry__status=JournalEntry.STATUS_POSTED, account__type=AccountType.REVENUE)
        expense_filter = Q(tenant=request.tenant, entry__tenant=request.tenant, entry__status=JournalEntry.STATUS_POSTED, account__type=AccountType.EXPENSE)
        if start:
            revenue_filter &= Q(entry__date__gte=start)
            expense_filter &= Q(entry__date__gte=start)
        if end:
            revenue_filter &= Q(entry__date__lte=end)
            expense_filter &= Q(entry__date__lte=end)
        revenue = JournalEntryLine.objects.filter(revenue_filter).aggregate(credits=Sum("credit"), debits=Sum("debit"))
        expenses = JournalEntryLine.objects.filter(expense_filter).aggregate(debits=Sum("debit"), credits=Sum("credit"))
        inflows = (revenue["credits"] or ZERO) - (revenue["debits"] or ZERO)
        outflows = (expenses["debits"] or ZERO) - (expenses["credits"] or ZERO)
        return Response({
            "total_inflows": money_text(inflows), "total_outflows": money_text(outflows), "net_cash_flow": money_text(inflows - outflows),
            "inflows": [{"label": "Sales Revenue", "amount": money_text(inflows)}],
            "outflows": [{"label": "Operating Expenses", "amount": money_text(outflows)}], "timeline": [],
        })
