# Generated for HIGH-007 / HIGH-002: composite indexes for dashboard, reports, inventory and POS hot paths
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("pos", "0022_fix_purchase_order_tenant_scoping"),
    ]

    operations = [
        # Order: tenant+status+created_at for dashboard overview, sales trend, order list filtering
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["tenant", "status", "created_at"], name="pos_order_tenant_status_created_idx"),
        ),
        # Order: tenant+created_at for date_range scans
        migrations.AddIndex(
            model_name="order",
            index=models.Index(fields=["tenant", "created_at"], name="pos_order_tenant_created_idx"),
        ),
        # OrderItem: tenant+product for sales_by_product / top products
        migrations.AddIndex(
            model_name="orderitem",
            index=models.Index(fields=["tenant", "product"], name="pos_orderitem_tenant_product_idx"),
        ),
        # OrderItem: order+product for join aggregation
        migrations.AddIndex(
            model_name="orderitem",
            index=models.Index(fields=["order", "product"], name="pos_orderitem_order_product_idx"),
        ),
        # StockMovement: tenant+created_at+product for inventory analytics
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["tenant", "created_at"], name="pos_stockmov_tenant_created_idx"),
        ),
        migrations.AddIndex(
            model_name="stockmovement",
            index=models.Index(fields=["tenant", "product", "created_at"], name="pos_stockmov_tenant_product_created_idx"),
        ),
        # CashSession: tenant+is_open+opened_by+opened_at for active session lookup and exports
        migrations.AddIndex(
            model_name="cashsession",
            index=models.Index(fields=["tenant", "is_open", "opened_by"], name="pos_cashsession_tenant_open_user_idx"),
        ),
        migrations.AddIndex(
            model_name="cashsession",
            index=models.Index(fields=["tenant", "opened_at"], name="pos_cashsession_tenant_opened_idx"),
        ),
        # Product: tenant+is_active+category for catalog search
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["tenant", "is_active", "category"], name="pos_product_tenant_active_cat_idx"),
        ),
        migrations.AddIndex(
            model_name="product",
            index=models.Index(fields=["tenant", "is_active"], name="pos_product_tenant_active_idx"),
        ),
        # Customer: tenant+is_active for typeahead
        migrations.AddIndex(
            model_name="customer",
            index=models.Index(fields=["tenant", "is_active"], name="pos_customer_tenant_active_idx"),
        ),
        # DraftOrder: tenant+session+status for draft list
        migrations.AddIndex(
            model_name="draftorder",
            index=models.Index(fields=["tenant", "session", "status"], name="pos_draftorder_tenant_session_idx"),
        ),
        # Refund: tenant+created_at for refund aggregates (if model has tenant)
    ]
