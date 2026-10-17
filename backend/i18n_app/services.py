from decimal import Decimal, ROUND_HALF_UP
from .models import Currency, TranslationKey, UserLocale


def convert(amount, from_currency_code, to_currency_code):
    if from_currency_code == to_currency_code:
        return Decimal(amount)
    src = Currency.objects.get(code=from_currency_code)
    dst = Currency.objects.get(code=to_currency_code)
    # convert through base
    base_amount = Decimal(amount) / src.exchange_rate
    converted = base_amount * dst.exchange_rate
    return converted.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def format_money(amount, currency_code):
    c = Currency.objects.get(code=currency_code)
    val = Decimal(amount)
    if c.decimals:
        val = val.quantize(Decimal("0.1") ** c.decimals, rounding=ROUND_HALF_UP)
    return f"{c.symbol}{val:,.{c.decimals}f}"


def translate(key, language_code, namespace="common", default=None):
    try:
        t = TranslationKey.objects.get(namespace=namespace, key=key, language__code=language_code)
        return t.value
    except TranslationKey.DoesNotExist:
        return default or key


def translate_batch(keys, language_code, namespace="common"):
    """Fetch many keys at once → {key: value} dict."""
    qs = TranslationKey.objects.filter(namespace=namespace, language__code=language_code, key__in=keys)
    out = {k: k for k in keys}
    for t in qs:
        out[t.key] = t.value
    return out


def user_locale(user):
    if not user or not user.is_authenticated:
        return None
    return UserLocale.objects.filter(user=user).select_related("language", "currency").first()


def user_currency_code(user, fallback="USD"):
    loc = user_locale(user)
    return loc.currency.code if loc and loc.currency else fallback


def user_language_code(user, fallback="en"):
    loc = user_locale(user)
    return loc.language.code if loc and loc.language else fallback