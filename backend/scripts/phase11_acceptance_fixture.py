"""Provision or remove fully isolated Phase 11 browser-acceptance fixtures.

Run from the Django project directory:
    py -3.14 scripts/phase11_acceptance_fixture.py setup
    py -3.14 scripts/phase11_acceptance_fixture.py cleanup

This helper deliberately creates only disposable records with the P11-CERT
prefix, keeps all business data within the canonical saas.Tenant boundary, and
removes the tenant before its temporary users and RBAC roles.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from decimal import Decimal

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.settings")

import django

django.setup()

from django.contrib.auth import get_user_model
from django.db import transaction

from enterprise.models import Warehouse
from operations.models import ApprovalRule
from pos.models import Category, Product, PurchaseOrder, PurchaseOrderItem, Supplier
from rbac.models import Module, Permission, Role, UserRole
from saas.models import Tenant, TenantMembership
from system.models import ErrorLog, Webhook, WebhookDelivery


User = get_user_model()
TENANT_SLUG = "phase11-browser-cert-main"
OWNER_USERNAME = "phase11-browser-cert-owner"
VIEWER_USERNAME = "phase11-browser-cert-viewer"
REVIEWER_USERNAME = "phase11-browser-cert-reviewer"
OWNER_ROLE_KEY = "phase11-browser-cert-owner-role"
VIEWER_ROLE_KEY = "phase11-browser-cert-viewer-role"
REVIEWER_ROLE_KEY = "phase11-browser-cert-reviewer-role"
PASSWORD = "Phase10Cert!486"


@transaction.atomic
def cleanup() -> None:
    """Remove the narrowly named tenant fixture and all dependent temp records."""
    tenant_ids = list(Tenant.objects.filter(slug=TENANT_SLUG).values_list("id", flat=True))
    if tenant_ids:
        PurchaseOrderItem.objects.filter(tenant_id__in=tenant_ids).delete()
        PurchaseOrder.objects.filter(tenant_id__in=tenant_ids).delete()
    Tenant.objects.filter(id__in=tenant_ids).delete()
    User.objects.filter(username__in=[OWNER_USERNAME, VIEWER_USERNAME, REVIEWER_USERNAME]).delete()
    Role.objects.filter(key__in=[OWNER_ROLE_KEY, VIEWER_ROLE_KEY, REVIEWER_ROLE_KEY]).delete()
    print("Phase 11 acceptance fixtures removed.")


def permission_for(key: str) -> Permission:
    module_key, action = key.split(".", 1)
    module, _ = Module.objects.get_or_create(
        key=module_key,
        defaults={"label": module_key.replace("_", " ").title()},
    )
    permission, _ = Permission.objects.get_or_create(module=module, action=action)
    return permission


@transaction.atomic
def setup() -> None:
    """Create tenant-local owner/viewer and supported operational source data."""
    cleanup()

    owner = User.objects.create_user(
        username=OWNER_USERNAME,
        password=PASSWORD,
        first_name="Phase 11",
        last_name="Certification Owner",
        email="phase11-owner@example.test",
    )
    viewer = User.objects.create_user(
        username=VIEWER_USERNAME,
        password=PASSWORD,
        first_name="Phase 11",
        last_name="Certification Viewer",
        email="phase11-viewer@example.test",
    )
    reviewer = User.objects.create_user(
        username=REVIEWER_USERNAME,
        password=PASSWORD,
        first_name="Phase 11",
        last_name="Certification Reviewer",
        email="phase11-reviewer@example.test",
    )
    tenant = Tenant.objects.create(
        name="Phase 11 Browser Certification Main",
        slug=TENANT_SLUG,
        owner=owner,
        status=Tenant.STATUS_ACTIVE,
        is_active=True,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=owner,
        role=TenantMembership.ROLE_OWNER,
        is_active_in_tenant=True,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=viewer,
        role=TenantMembership.ROLE_MANAGER,
        is_active_in_tenant=True,
    )
    TenantMembership.objects.create(
        tenant=tenant,
        user=reviewer,
        role=TenantMembership.ROLE_MANAGER,
        is_active_in_tenant=True,
    )

    owner_role = Role.objects.create(
        key=OWNER_ROLE_KEY,
        label="Phase 11 Certification Owner",
        description="Disposable browser-acceptance role with all existing permissions.",
    )
    owner_role.permissions.set(Permission.objects.all())
    UserRole.objects.create(user=owner, role=owner_role)

    viewer_role = Role.objects.create(
        key=VIEWER_ROLE_KEY,
        label="Phase 11 Certification Viewer",
        description="Disposable read-only browser-acceptance role.",
    )
    viewer_role.permissions.add(
        permission_for("operations.view"),
        permission_for("audit.view"),
    )
    UserRole.objects.create(user=viewer, role=viewer_role)

    reviewer_role = Role.objects.create(
        key=REVIEWER_ROLE_KEY,
        label="Phase 11 Certification Reviewer",
        description="Disposable browser-acceptance role with approval rights.",
    )
    reviewer_role.permissions.add(
        permission_for("operations.view"),
        permission_for("operations.approve"),
        permission_for("audit.view"),
        permission_for("settings.manage"),
    )
    UserRole.objects.create(user=reviewer, role=reviewer_role)

    warehouse = Warehouse.objects.create(
        tenant=tenant,
        code="P10CERT",
        name="Phase 11 Certification Warehouse",
    )
    category = Category.objects.create(tenant=tenant, name="Phase 11 Certification Category")
    product = Product.objects.create(
        tenant=tenant,
        category=category,
        name="Phase 11 Certification Product",
        sku="P11-CERT-PRODUCT",
        sales_price=Decimal("9.00"),
        cost_price=Decimal("5.00"),
        stock_quantity=Decimal("0.00"),
        is_active=True,
    )
    supplier = Supplier.objects.create(
        tenant=tenant,
        name="Phase 11 Certification Supplier",
        phone="0000000000",
    )
    order = PurchaseOrder.objects.create(
        tenant=tenant,
        supplier=supplier,
        warehouse=warehouse,
        order_number="P11-CERT-PO-001",
        status="draft",
        subtotal=Decimal("10.00"),
        tax=Decimal("0.00"),
        total=Decimal("10.00"),
        note="Disposable Phase 11 approval-gate acceptance fixture.",
    )
    PurchaseOrderItem.objects.create(
        tenant=tenant,
        purchase_order=order,
        product=product,
        quantity=Decimal("2.00"),
        unit_cost=Decimal("5.00"),
        subtotal=Decimal("10.00"),
    )
    ApprovalRule.objects.create(
        tenant=tenant,
        module="purchase_order",
        action="confirm",
        min_amount=Decimal("1.00"),
        requires_approval=True,
        is_active=True,
    )

    webhook = Webhook.objects.create(
        tenant=tenant,
        name="Phase 11 Certification Webhook",
        target_url="https://example.test/phase11-webhook",
        events=["order.created"],
        secret="phase11-secret-must-not-be-serialized",
    )
    WebhookDelivery.objects.create(
        tenant=tenant,
        webhook=webhook,
        event="order.created",
        payload={"token": "phase11-payload-token-must-not-be-serialized"},
        status_code=202,
        success=True,
        response_body="phase11-response-must-not-be-serialized",
    )
    ErrorLog.objects.create(
        tenant=tenant,
        log_type="error",
        severity="medium",
        source="phase11-browser-cert",
        message="Disposable Phase 11 serializer-redaction acceptance record.",
        stack_trace="phase11-stack-trace-must-not-be-serialized",
        context={"api_key": "phase11-context-secret-must-not-be-serialized"},
        user=owner,
    )

    print(
        "Phase 11 acceptance fixtures ready:\n"
        f"  tenant={tenant.slug} id={tenant.id}\n"
        f"  owner={OWNER_USERNAME} password={PASSWORD}\n"
        f"  viewer={VIEWER_USERNAME} password={PASSWORD}\n"
        f"  reviewer={REVIEWER_USERNAME} password={PASSWORD}\n"
        f"  purchase_order={order.id} ({order.order_number})"
    )


if __name__ == "__main__":
    command = sys.argv[1] if len(sys.argv) == 2 else ""
    if command == "setup":
        setup()
    elif command == "cleanup":
        cleanup()
    else:
        raise SystemExit("Usage: py -3.14 scripts/phase11_acceptance_fixture.py [setup|cleanup]")

