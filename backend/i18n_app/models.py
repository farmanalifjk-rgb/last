from decimal import Decimal
from django.conf import settings
from django.db import models


class Currency(models.Model):
    code = models.CharField(max_length=3, unique=True)        # USD, PKR, EUR
    name = models.CharField(max_length=80)
    symbol = models.CharField(max_length=10)
    decimals = models.PositiveIntegerField(default=2)
    is_base = models.BooleanField(default=False, help_text="The currency all amounts are stored in")
    exchange_rate = models.DecimalField(max_digits=12, decimal_places=6, default=Decimal("1"),
                                        help_text="Rate from base → this currency (1 base = rate * this)")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name_plural = "Currencies"


class Language(models.Model):
    code = models.CharField(max_length=8, unique=True)         # en, ur, en-US
    name = models.CharField(max_length=80)
    direction = models.CharField(max_length=3, choices=[("ltr", "LTR"), ("rtl", "RTL")], default="ltr")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]


class TranslationKey(models.Model):
    """Namespace + key + language → translated string."""
    namespace = models.CharField(max_length=60, default="common")
    key = models.CharField(max_length=200)
    language = models.ForeignKey(Language, on_delete=models.CASCADE, related_name="translations")
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        unique_together = [("namespace", "key", "language")]
        indexes = [models.Index(fields=["namespace", "language"])]


class UserLocale(models.Model):
    """Per-user language + display currency preference."""
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="locale")
    language = models.ForeignKey(Language, null=True, blank=True, on_delete=models.SET_NULL)
    currency = models.ForeignKey(Currency, null=True, blank=True, on_delete=models.SET_NULL)
    date_format = models.CharField(max_length=40, default="YYYY-MM-DD")
    time_format = models.CharField(max_length=40, default="HH:mm")
    timezone = models.CharField(max_length=60, default="UTC")
    updated_at = models.DateTimeField(auto_now=True)