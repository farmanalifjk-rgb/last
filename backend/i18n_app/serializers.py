from rest_framework import serializers
from .models import Currency, Language, TranslationKey, UserLocale


class CurrencySerializer(serializers.ModelSerializer):
    class Meta:
        model = Currency
        fields = ["id","code","name","symbol","decimals","is_base","exchange_rate","is_active","created_at"]


class LanguageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Language
        fields = ["id","code","name","direction","is_active","created_at"]


class TranslationKeySerializer(serializers.ModelSerializer):
    class Meta:
        model = TranslationKey
        fields = ["id","namespace","key","language","value","updated_at"]


class UserLocaleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLocale
        fields = ["id","user","language","currency","date_format","time_format","timezone","updated_at"]