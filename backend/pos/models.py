from django.db import models, transaction

from django.conf import settings

class Category(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=100)
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        constraints = [
            models.CheckConstraint(condition=~models.Q(pk=models.F("parent")), name="category_cannot_be_own_parent"),
        ]

    def __str__(self):
        return self.name


# ─── NEW: Brand ───────────────────────────────────────────────────────────────
class Brand(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    logo = models.ImageField(upload_to="brands/", blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class Product(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True)
    # ─── NEW: brand FK ─────────────────────────────────────────────────────────
    brand = models.ForeignKey(Brand, on_delete=models.SET_NULL, null=True, blank=True)
    name = models.CharField(max_length=255)
    sku = models.CharField(max_length=100)
    barcode = models.CharField(max_length=100, blank=True, null=True)
    description = models.CharField(max_length=500,blank=True, null=True)

    sales_price = models.DecimalField(max_digits=10, decimal_places=2)
    cost_price = models.DecimalField(max_digits=10, decimal_places=2)

    stock_quantity = models.DecimalField(max_digits=14, decimal_places=3, default=0)

    min_stock = models.PositiveIntegerField(default=0)

    max_stock = models.PositiveIntegerField(null=True,blank=True)

    unit = models.CharField(max_length=20,default="Piece")

    image = models.ImageField(upload_to="products/", blank=True, null=True)

    is_active = models.BooleanField(default=True)

    # ─── NEW: optional, gated behind ProductSettings.enable_expiry / enable_batch_number ──
    expiry_date = models.DateField(null=True, blank=True)
    batch_number = models.CharField(max_length=100, blank=True, default="")

    def __str__(self):
        return self.name

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["tenant", "sku"], name="unique_product_sku_per_tenant"),
            models.UniqueConstraint(
                fields=["tenant", "barcode"],
                condition=models.Q(barcode__isnull=False) & ~models.Q(barcode=""),
                name="unique_product_barcode_per_tenant",
            ),
        ]




class Customer(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    name = models.CharField(max_length=255)
    phone = models.CharField(max_length=20, blank=True)
    email = models.EmailField(blank=True)
    address = models.TextField(blank=True)
    customer_code = models.CharField(max_length=30, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # ─── NEW: loyalty + grouping (Customer settings tab) ───────────────────
    group = models.ForeignKey(
        'system.CustomerGroup', on_delete=models.SET_NULL, null=True, blank=True, related_name="customers"
    )
    loyalty_points = models.PositiveIntegerField(default=0)
    date_of_birth = models.DateField(null=True, blank=True)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "customer_code"], condition=models.Q(customer_code__gt=""), name="unique_customer_code_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "email"], condition=models.Q(email__gt=""), name="unique_customer_email_per_tenant"),
            models.UniqueConstraint(fields=["tenant", "phone"], condition=models.Q(phone__gt=""), name="unique_customer_phone_per_tenant"),
        ]

    def save(self, *args, **kwargs):
        needs_code = self.pk is None and not self.customer_code
        super().save(*args, **kwargs)
        if needs_code:
            # Use the database-assigned PK as a unique, deterministic code.
            # The UniqueConstraint on (tenant, customer_code) will reject any
            # collision caused by a concurrent insert that assigned the same PK
            # before this save — which is effectively impossible with PostgreSQL
            # serial/bigserial PKs but we handle the IntegrityError defensively.
            self.customer_code = f"CU-{self.tenant_id}-{self.pk:06d}"
            try:
                super().save(update_fields=["customer_code", "updated_at"])
            except Exception:
                # If the code collides (near-impossible), append a suffix.
                self.customer_code = f"CU-{self.tenant_id}-{self.pk:06d}-{self.pk}"
                super().save(update_fields=["customer_code", "updated_at"])

    def __str__(self):
        return self.name


class CashSession(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    warehouse = models.ForeignKey("enterprise.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="pos_cash_sessions")
    opened_at = models.DateTimeField(auto_now_add=True)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="opened_cash_sessions")
    closed_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True, related_name="closed_cash_sessions")

    closed_at = models.DateTimeField(null=True, blank=True)
    opening_balance = models.DecimalField(max_digits=12, decimal_places=2)
    closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    actual_closing_balance = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    is_open = models.BooleanField(default=True)
    next_draft_number = models.IntegerField(default=1)
    employee_name = models.CharField(max_length=150,blank=True,default="")
    notes = models.TextField(blank=True, default="")

    def __str__(self):
        return f"Session #{self.id}"

class CashTransaction(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TRANSACTION_TYPES = [
        ('in', 'Cash In'),
        ('out', 'Cash Out'),
    ]
    session = models.ForeignKey(CashSession, on_delete=models.CASCADE, related_name='transactions')
    transaction_type = models.CharField(max_length=10, choices=TRANSACTION_TYPES)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    reason = models.CharField(max_length=255)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="cash_transactions")
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.transaction_type.upper()} - {self.amount} - {self.reason}"


class Order(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    warehouse = models.ForeignKey("enterprise.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="pos_orders")

    PAYMENT_CHOICES = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("bank", "Bank Transfer"),
        ("split", "Split Payment"),
        ("gift_card", "Gift Card"),
        ("store_credit", "Store Credit"),
        ("loyalty", "Loyalty Points"),
        ("wallet", "Wallet"),
    ]
    STATUS_CHOICES = [
    ('draft', 'Draft'),
    ('paid', 'Paid'),
    ("partially_refunded","Partially Refunded"),
    ("refunded", "Refunded"),
    ('cancelled', 'Cancelled'),
    ]
    # Valid status transitions: from -> set of allowed targets.
    _VALID_TRANSITIONS = {
        'draft': {'paid', 'cancelled'},
        'paid': {'partially_refunded', 'refunded'},
        'partially_refunded': {'refunded'},
    }

    def transition_to(self, new_status):
        """Validate and apply a status transition. Raises ValueError if invalid."""
        allowed = self._VALID_TRANSITIONS.get(self.status, set())
        if new_status not in allowed:
            raise ValueError(
                f"Invalid order status transition: {self.status} -> {new_status}. "
                f"Allowed transitions from '{self.status}': {allowed or 'none'}."
            )
        self.status = new_status
        self.save(update_fields=['status'])

    customer = models.ForeignKey(Customer,on_delete=models.SET_NULL,null=True,blank=True)
    note = models.TextField(blank=True, default="")
    session = models.ForeignKey(CashSession,on_delete=models.SET_NULL,null=True,related_name="orders")
    created_at = models.DateTimeField(auto_now_add=True)
    payment_method = models.CharField(max_length=20,choices=PAYMENT_CHOICES)
    subtotal = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    tax = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    discount = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    total = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    status = models.CharField(max_length=20,choices=STATUS_CHOICES,default='draft')
    # The number is assigned after the database has allocated the order ID.
    # Nullable values prevent concurrent checkouts from colliding on an empty
    # unique value during that first insert.
    order_number = models.CharField(max_length=20, unique=True, null=True, blank=True)
    amount_received = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    change_amount = models.DecimalField(max_digits=12,decimal_places=2,default=0)
    idempotency_key = models.CharField(max_length=128, null=True, blank=True)
    idempotency_request_hash = models.CharField(max_length=64, blank=True, default="")

    def save(self, *args, **kwargs):

        is_new = self.pk is None

        super().save(*args, **kwargs)

        if is_new and not self.order_number:
            self.order_number = f"POS-{self.id:06d}"
            super().save(update_fields=["order_number"])

    def __str__(self):
        return f"Order #{self.id}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "idempotency_key"],
                condition=models.Q(idempotency_key__isnull=False) & ~models.Q(idempotency_key=""),
                name="unique_pos_checkout_idempotency_per_tenant",
            ),
        ]
        


class OrderItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name="items")
    product = models.ForeignKey(Product,on_delete=models.PROTECT)
    quantity = models.DecimalField(max_digits=10,decimal_places=2)
    unit_price = models.DecimalField(max_digits=10,decimal_places=2)
    subtotal = models.DecimalField(max_digits=12,decimal_places=2)
    # Snapshot of cost at time of sale — critical for historically accurate COGS.
    # NULL on legacy rows (pre-migration); dashboard falls back to current
    # Product.cost_price and flags the data as estimated.
    cost_price = models.DecimalField(
        max_digits=10, decimal_places=2, null=True, blank=True,
        help_text="Cost price snapshot at time of sale for accurate COGS",
    )

    def __str__(self):
        return self.product.name


class Payment(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name="payments")
    amount = models.DecimalField(max_digits=12,decimal_places=2)
    payment_method = models.CharField(max_length=20)
    paid_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Payment {self.id}"
    

class DraftOrder(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    session = models.ForeignKey(CashSession, on_delete=models.CASCADE)
    order_number = models.IntegerField()
    status = models.CharField(max_length=20,default="draft")
    customer = models.ForeignKey(Customer,on_delete=models.SET_NULL,null=True,blank=True)
    note = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    


class DraftOrderItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    draft_order = models.ForeignKey(DraftOrder,on_delete=models.CASCADE,related_name="items")
    product = models.ForeignKey(Product,on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    unit_price = models.DecimalField(max_digits=12,decimal_places=2)        


class StockMovement(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    MOVEMENT_TYPES = [
    
        ("purchase", "Purchase"),
    
        ("sale", "Sale"),
    
        ("refund", "Refund"),
    
        ("purchase_return", "Purchase Return"),
    
        ("adjustment", "Adjustment"),
    
        ("damage", "Damage"),

        ("transfer_out", "Transfer out"),

        ("transfer_in", "Transfer in"),

        ("cycle_count", "Cycle count"),

        ("reservation", "Reservation"),

        ("reservation_release", "Reservation release"),
    
    ]

    product = models.ForeignKey(Product,on_delete=models.CASCADE)

    warehouse = models.ForeignKey("enterprise.Warehouse", null=True, blank=True, on_delete=models.SET_NULL, related_name="stock_movements")

    reference = models.CharField(max_length=50,blank=True)

    quantity = models.DecimalField(max_digits=14, decimal_places=3)

    movement_type = models.CharField(max_length=20,choices=MOVEMENT_TYPES)

    previous_stock = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    new_stock = models.DecimalField(max_digits=14, decimal_places=3, null=True, blank=True)

    note = models.CharField(max_length=255,blank=True)

    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.product.name} - {self.movement_type}"
    
    class Meta:
        ordering = ["-created_at"]



class Company(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    PAPER_CHOICES = [
    ("58mm", "58mm Thermal"),
    ("80mm", "80mm Thermal"),
    ("A5", "A5"),
    ("A4", "A4"),
    ]

    name = models.CharField(max_length=200)
    tagline = models.CharField(max_length=200,blank=True)
    address = models.TextField()
    phone = models.CharField(max_length=50,blank=True)
    email = models.EmailField(blank=True)
    website = models.CharField(max_length=200,blank=True)
    tax_number = models.CharField(max_length=100,blank=True)
    footer_message = models.TextField(blank=True,default="Thank you for your purchase!")
    logo = models.ImageField(upload_to="company/",null=True,blank=True)
    currency = models.CharField(max_length=20,default="Rs")
    receipt_paper = models.CharField(max_length=10,choices=PAPER_CHOICES,default="80mm")
    gst = models.CharField(max_length=50,blank=True,default="")

    # ─── NEW: Business Information ─────────────────────────────────────────
    legal_name = models.CharField(max_length=200, blank=True)
    cover_image = models.ImageField(upload_to="company/covers/", null=True, blank=True)
    business_type = models.CharField(max_length=30, blank=True, default="retail", choices=[
        ("retail", "Retail"), ("restaurant", "Restaurant"), ("grocery", "Grocery"),
        ("pharmacy", "Pharmacy"), ("salon", "Salon / Services"), ("wholesale", "Wholesale"), ("other", "Other"),
    ])
    industry = models.CharField(max_length=100, blank=True)
    business_registration_number = models.CharField(max_length=100, blank=True)

    # ─── NEW: Address (structured) ─────────────────────────────────────────
    country = models.CharField(max_length=100, blank=True)
    state = models.CharField(max_length=100, blank=True)
    city = models.CharField(max_length=100, blank=True)
    postal_code = models.CharField(max_length=20, blank=True)
    full_address = models.TextField(blank=True)

    # ─── NEW: Receipt Information ──────────────────────────────────────────
    receipt_header = models.TextField(blank=True)
    thank_you_message = models.CharField(max_length=255, blank=True, default="Thank you for your purchase!")
    return_policy = models.TextField(blank=True)
    show_qr_code_on_receipt = models.BooleanField(default=True)
    show_logo_on_receipt = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class Refund(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    order = models.ForeignKey(Order,on_delete=models.CASCADE,related_name="refunds")
    reason = models.TextField(blank=True)

    subtotal = models.DecimalField(max_digits=12,decimal_places=2,default=0)

    discount = models.DecimalField(max_digits=12,decimal_places=2,default=0)

    tax = models.DecimalField(max_digits=12,decimal_places=2,default=0)

    total_amount = models.DecimalField(max_digits=12,decimal_places=2)

    created_at = models.DateTimeField(auto_now_add=True)       


class RefundItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    refund = models.ForeignKey(Refund,on_delete=models.CASCADE,related_name="items")
    order_item = models.ForeignKey(OrderItem,on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    subtotal = models.DecimalField(max_digits=12, decimal_places=2,default=0)

    amount = models.DecimalField(max_digits=12,decimal_places=2)
    
   
class StockAdjustment(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    ADJUSTMENT_TYPES = [

        ("increase", "Increase"),

        ("decrease", "Decrease"),

    ]

    adjustment_number = models.CharField(max_length=20)

    adjustment_type = models.CharField(max_length=20,choices=ADJUSTMENT_TYPES,)

    reason = models.CharField(max_length=255,)

    note = models.TextField(blank=True,)

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL,on_delete=models.SET_NULL,null=True,blank=True,)

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["tenant", "adjustment_number"],
                name="pos_unique_stock_adjustment_number_per_tenant",
            ),
        ]

    def __str__(self):
        return self.adjustment_number

    def save(self, *args, **kwargs):
        if self.pk or self.adjustment_number:
            return super().save(*args, **kwargs)
        # Lock the tenant row, which gives every adjustment allocator for this
        # tenant one serialization point without coupling unrelated tenants.
        from saas.models import Tenant

        with transaction.atomic():
            Tenant.objects.select_for_update().get(pk=self.tenant_id)
            last = StockAdjustment.objects.filter(
                tenant_id=self.tenant_id,
                adjustment_number__startswith="SA-",
            ).order_by("-adjustment_number").first()
            try:
                next_number = int(last.adjustment_number.removeprefix("SA-")) + 1 if last else 1
            except ValueError:
                next_number = 1
            self.adjustment_number = f"SA-{next_number:06d}"
            return super().save(*args, **kwargs)


class StockAdjustmentItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    adjustment = models.ForeignKey(StockAdjustment,related_name="items",on_delete=models.CASCADE,)

    product = models.ForeignKey(Product,on_delete=models.CASCADE,)

    adjustment_type = models.CharField(max_length=20, choices=StockAdjustment.ADJUSTMENT_TYPES, default="increase")

    quantity = models.DecimalField(max_digits=14, decimal_places=3)

    previous_stock = models.DecimalField(max_digits=14, decimal_places=3)

    new_stock = models.DecimalField(max_digits=14, decimal_places=3)

    note = models.CharField(max_length=255,blank=True,)

    def __str__(self):

        return self.product.name    


class Supplier(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    name = models.CharField(max_length=255)

    company = models.CharField(
        max_length=255,
        blank=True
    )

    contact_person = models.CharField(
        max_length=255,
        blank=True
    )

    phone = models.CharField(max_length=30)

    email = models.EmailField(
        blank=True
    )

    address = models.TextField(
        blank=True
    )

    tax_number = models.CharField(
        max_length=100,
        blank=True
    )

    is_active = models.BooleanField(
        default=True
    )

    created_at = models.DateTimeField(
        auto_now_add=True
    )

    updated_at = models.DateTimeField(
        auto_now=True
    )

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class PurchaseOrder(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    STATUS_CHOICES = [

        ("draft", "Draft"),

        ("ordered", "Ordered"),

        ("received", "Received"),

        ("cancelled", "Cancelled"),

    ]

    supplier = models.ForeignKey(
        Supplier,
        on_delete=models.PROTECT,
    )

    warehouse = models.ForeignKey(
        "enterprise.Warehouse",
        on_delete=models.PROTECT,
        related_name="purchase_orders",
    )

    order_number = models.CharField(
        max_length=30,
        null=True,
        blank=True,
    )

    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default="draft",
    )

    subtotal = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    tax = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    supplier_invoice_number = models.CharField(max_length=100,blank=True)

    expected_date = models.DateField(null=True, blank=True)

    total = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        default=0,
    )

    note = models.TextField(
        blank=True,
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
    )

    updated_at = models.DateTimeField(
        auto_now=True,
    )

    class Meta:
        ordering = ["-id"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "order_number"], name="unique_purchase_order_number_per_tenant"),
        ]

    def __str__(self):
        return self.order_number


class PurchaseOrderItem(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")

    purchase_order = models.ForeignKey(PurchaseOrder,related_name="items",on_delete=models.CASCADE,)

    product = models.ForeignKey(Product,on_delete=models.PROTECT,)

    quantity = models.DecimalField(max_digits=14, decimal_places=2)

    received_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)

    unit_cost = models.DecimalField(max_digits=10,decimal_places=2,)

    subtotal = models.DecimalField(max_digits=12,decimal_places=2,)

    returned_quantity = models.DecimalField(max_digits=14, decimal_places=2, default=0)


# ═══════════════════════════════════════════════════════════════════════════════
# NEW MODELS — added for Products / Configuration tabs
# ═══════════════════════════════════════════════════════════════════════════════

class Variant(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Variant type, e.g. 'Color', 'Size'."""
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


class VariantValue(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Individual value for a Variant, e.g. 'Red' for 'Color'."""
    variant = models.ForeignKey(Variant, on_delete=models.CASCADE, related_name="values")
    value = models.CharField(max_length=100)

    def __str__(self):
        return f"{self.variant.name}: {self.value}"

    class Meta:
        unique_together = ("variant", "value")


class Tax(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TAX_TYPES = [
        ("percentage", "Percentage"),
        ("fixed", "Fixed Amount"),
    ]

    name = models.CharField(max_length=100)
    rate = models.DecimalField(max_digits=6, decimal_places=2)
    tax_type = models.CharField(max_length=20, choices=TAX_TYPES, default="percentage")
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.rate}%)"

    class Meta:
        ordering = ["-is_default", "name"]


class PaymentMethod(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    METHOD_TYPES = [
        ("cash", "Cash"),
        ("card", "Card"),
        ("bank", "Bank Transfer"),
        ("mobile", "Mobile Payment"),
        ("other", "Other"),
    ]

    name = models.CharField(max_length=100)
    method_type = models.CharField(max_length=20, choices=METHOD_TYPES, default="cash")
    is_active = models.BooleanField(default=True)
    is_default = models.BooleanField(default=False)
    instructions = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ─── NEW: presentation for the POS payment screen ──────────────────────
    icon = models.CharField(max_length=50, blank=True, default="wallet", help_text="Lucide icon name")
    color = models.CharField(max_length=20, blank=True, default="#6366F1")

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["-is_default", "name"]


class UserProfile(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="profile",
    )
    # DEPRECATED: The canonical RBAC system lives in rbac.models.Role / UserRole.
    # This FK is retained only for backward compatibility with legacy profile reads.
    role = models.ForeignKey("rbac.Role", on_delete=models.SET_NULL, null=True, blank=True)
    phone = models.CharField(max_length=20, blank=True)
    avatar = models.ImageField(upload_to="avatars/", blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # ─── NEW: security tab support (password expiry) ──────────────────────
    password_changed_at = models.DateTimeField(null=True, blank=True)

    def __str__(self):
        return self.user.username



# Settings-module models imported explicitly (no wildcard) so the
# Django app registry discovers them without namespace pollution.
from system.models import (
    Store, POSSettings, InventorySettings, TaxSettings, ReceiptSettings,
    NotificationSettings, Notification, HardwareDevice, BarcodeSettings,
    CustomerGroup, CustomerSettings, ProductSettings, CustomField,
    SecuritySettings, LoginAttempt, TrustedDevice, AuditLog,
    BackupSettings, BackupRecord, DataManagementSettings,
    ReportSettings, ScheduledReport, AppearanceSettings, FeatureFlags,
    APIKey, Webhook, WebhookDelivery, EmailTemplate, SMSTemplate,
    ReceiptTemplate, AboutInfo, ErrorLog,
)

# Auth models (expiring tokens, OTPs).
from auth_app.models import AuthToken, OneTimePasscode  # noqa

# Enterprise location and warehouse models.
from enterprise.models import (
    Warehouse, WarehouseStock,
)  # noqa
