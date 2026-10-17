from django.urls import path
from .views import (CurrencyListCreateView, CurrencyDetailView, LanguageListCreateView,
                    TranslationKeyListCreateView, TranslationBatchView, ConvertView,
                    MyLocaleView, FormatView)

urlpatterns = [
    path("currencies/", CurrencyListCreateView.as_view()),
    path("currencies/<int:pk>/", CurrencyDetailView.as_view()),
    path("languages/", LanguageListCreateView.as_view()),
    path("translations/", TranslationKeyListCreateView.as_view()),
    path("translations/batch/", TranslationBatchView.as_view()),
    path("convert/", ConvertView.as_view()),
    path("format/", FormatView.as_view()),
    path("me/locale/", MyLocaleView.as_view()),
]