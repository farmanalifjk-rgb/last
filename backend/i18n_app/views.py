from decimal import Decimal, InvalidOperation
from rest_framework import generics, permissions
from rest_framework.permissions import SAFE_METHODS
from rest_framework.views import APIView
from rest_framework.response import Response

from .models import Currency, Language, TranslationKey, UserLocale
from .serializers import (CurrencySerializer, LanguageSerializer,
                          TranslationKeySerializer, UserLocaleSerializer)
from .services import convert, format_money, translate_batch, user_locale
from saas.permissions import PlatformRBACPermission


class ReadAuthenticatedWritePlatform(PlatformRBACPermission):
    """Currencies, languages and translation keys are global (shared by every
    tenant). Any signed-in user may read them; changing them needs the same
    platform permission as the other global settings (settings.manage)."""

    def has_permission(self, request, view):
        if request.method in SAFE_METHODS:
            return bool(request.user and request.user.is_authenticated)
        return super().has_permission(request, view)


class GlobalI18nMixin:
    permission_classes = [permissions.IsAuthenticated, ReadAuthenticatedWritePlatform]
    rbac_module = "settings"
    rbac_action = "manage"


class CurrencyListCreateView(GlobalI18nMixin, generics.ListCreateAPIView):
    serializer_class = CurrencySerializer
    queryset = Currency.objects.all()


class CurrencyDetailView(GlobalI18nMixin, generics.RetrieveUpdateDestroyAPIView):
    serializer_class = CurrencySerializer
    queryset = Currency.objects.all()


class LanguageListCreateView(GlobalI18nMixin, generics.ListCreateAPIView):
    serializer_class = LanguageSerializer
    queryset = Language.objects.all()


class TranslationKeyListCreateView(GlobalI18nMixin, generics.ListCreateAPIView):
    serializer_class = TranslationKeySerializer
    queryset = TranslationKey.objects.all()


class TranslationBatchView(APIView):
    """POST {language, namespace, keys: [...]} → {key: value}."""
    permission_classes = [permissions.IsAuthenticated]
    def post(self, request):
        return Response(translate_batch(request.data.get("keys", []),
                                        request.data.get("language", "en"),
                                        request.data.get("namespace", "common")))


class ConvertView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        try:
            amount = Decimal(request.query_params["amount"])
        except (KeyError, InvalidOperation):
            return Response({"detail": "amount required"}, status=400)
        src = request.query_params.get("from", "USD")
        dst = request.query_params.get("to", "USD")
        try:
            converted = convert(amount, src, dst)
            formatted = format_money(converted, dst)
        except Currency.DoesNotExist:
            return Response({"detail": "Unknown currency code."}, status=400)
        return Response({"amount": str(converted), "formatted": formatted})


class MyLocaleView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        loc = user_locale(request.user)
        return Response(UserLocaleSerializer(loc).data if loc else {})
    def put(self, request):
        loc, _ = UserLocale.objects.get_or_create(user=request.user)
        serializer = UserLocaleSerializer(loc, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class FormatView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    def get(self, request):
        currency = request.query_params.get("currency", "USD")
        try:
            amount = Decimal(request.query_params.get("amount", "0"))
        except InvalidOperation:
            return Response({"detail": "amount must be a number."}, status=400)
        if not amount.is_finite():
            return Response({"detail": "amount must be a number."}, status=400)
        try:
            return Response({"formatted": format_money(amount, currency)})
        except Currency.DoesNotExist:
            return Response({"detail": "Unknown currency code."}, status=400)