"""
Loyalty & Promotions models.

Handles loyalty programs, point transactions, membership tiers,
gift cards, coupons, and flexible promotions.
"""
import secrets
from django.db import models
from django.utils import timezone


class LoyaltyProgram(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Singleton-ish config for the store loyalty program."""
    name                = models.CharField(max_length=100, default="Loyalty Program")
    points_per_currency = models.DecimalField(max_digits=8, decimal_places=2, default=1,
                            help_text="Points earned per 1 unit of currency spent")
    redemption_rate     = models.DecimalField(max_digits=8, decimal_places=4, default=0.01,
                            help_text="Currency value of 1 point when redeeming")
    min_points_redeem   = models.PositiveIntegerField(default=100, help_text="Minimum points needed to redeem")
    is_active           = models.BooleanField(default=True)
    updated_at          = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Loyalty Program"

    def __str__(self):
        return self.name


class MembershipTier(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Tiered membership levels (Bronze, Silver, Gold, Platinum)."""
    name          = models.CharField(max_length=50)
    min_points    = models.PositiveIntegerField(default=0, help_text="Points needed to reach this tier")
    bonus_percent = models.DecimalField(max_digits=5, decimal_places=2, default=0,
                      help_text="Extra % points earned on purchases at this tier")
    color         = models.CharField(max_length=20, blank=True, help_text="CSS color for UI badge")

    class Meta:
        ordering = ["min_points"]
        constraints = [
            models.UniqueConstraint(fields=["tenant", "name"], name="loyalty_unique_tier_name_per_tenant"),
        ]

    def __str__(self):
        return self.name


class LoyaltyTransaction(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    """Record of every points earn or redeem event."""
    TYPE_EARN    = "earn"
    TYPE_REDEEM  = "redeem"
    TYPE_ADJUST  = "adjust"
    TYPE_EXPIRE  = "expire"
    TYPE_CHOICES = [
        (TYPE_EARN,   "Earned"),
        (TYPE_REDEEM, "Redeemed"),
        (TYPE_ADJUST, "Manual Adjustment"),
        (TYPE_EXPIRE, "Expired"),
    ]

    customer      = models.ForeignKey("pos.Customer", on_delete=models.CASCADE, related_name="loyalty_transactions")
    type          = models.CharField(max_length=10, choices=TYPE_CHOICES)
    points        = models.IntegerField(help_text="Positive to add, negative to deduct")
    reference     = models.CharField(max_length=100, blank=True, help_text="Order number, coupon code, etc.")
    reason        = models.CharField(max_length=255, blank=True)
    created_at    = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer} | {self.type} {self.points} pts"


def generate_gift_card_code():
    return secrets.token_hex(8).upper()


class Coupon(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TYPE_PERCENT = "percent"
    TYPE_FIXED   = "fixed"
    TYPE_CHOICES = [("percent","Percentage Off"),("fixed","Fixed Amount Off")]

    code           = models.CharField(max_length=30, unique=True)
    discount_type  = models.CharField(max_length=10, choices=TYPE_CHOICES)
    discount_value = models.DecimalField(max_digits=10, decimal_places=2)
    min_order      = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    max_discount   = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    uses_total     = models.PositiveIntegerField(default=0, help_text="0 = unlimited")
    uses_left      = models.PositiveIntegerField(default=0)
    expiry         = models.DateField(null=True, blank=True)
    is_active      = models.BooleanField(default=True)
    created_at     = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"COUPON-{self.code} ({self.discount_type}: {self.discount_value})"

    @property
    def is_valid(self):
        if not self.is_active:
            return False
        if self.expiry and self.expiry < timezone.now().date():
            return False
        if self.uses_total > 0 and self.uses_left <= 0:
            return False
        return True


class Promotion(models.Model):
    tenant = models.ForeignKey("saas.Tenant", on_delete=models.CASCADE, related_name="%(app_label)s_%(class)s_records")
    TYPE_BUY_X_GET_Y = "buy_x_get_y"
    TYPE_PERCENT_OFF = "percent_off"
    TYPE_FIXED_OFF   = "fixed_off"
    TYPE_BUNDLE      = "bundle"
    TYPE_CHOICES = [
        (TYPE_BUY_X_GET_Y, "Buy X Get Y"),
        (TYPE_PERCENT_OFF, "Percentage Off"),
        (TYPE_FIXED_OFF,   "Fixed Amount Off"),
        (TYPE_BUNDLE,      "Bundle Deal"),
    ]

    name        = models.CharField(max_length=150)
    type        = models.CharField(max_length=20, choices=TYPE_CHOICES)
    description = models.TextField(blank=True)
    conditions  = models.JSONField(default=dict, help_text='{"min_qty": 2, "product_ids": [1,2]}')
    discount    = models.JSONField(default=dict, help_text='{"type":"percent","value":10}')
    start_date  = models.DateField()
    end_date    = models.DateField(null=True, blank=True)
    is_active   = models.BooleanField(default=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-start_date"]

    def __str__(self):
        return self.name

    @property
    def is_running(self):
        today = timezone.now().date()
        if self.start_date > today:
            return False
        if self.end_date and self.end_date < today:
            return False
        return self.is_active


