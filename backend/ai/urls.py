from django.urls import path
from .views import (AskView, DailySummaryView, AIQueryHistoryView,
                    GenerateReorderSuggestionsView, ReorderSuggestionListView,
                    ReorderSuggestionDetailView, PromptTemplateListCreateView)

urlpatterns = [
    path("ask/", AskView.as_view()),
    path("daily-summary/", DailySummaryView.as_view()),
    path("history/", AIQueryHistoryView.as_view()),
    path("reorder/generate/", GenerateReorderSuggestionsView.as_view()),
    path("reorder/", ReorderSuggestionListView.as_view()),
    path("reorder/<int:pk>/", ReorderSuggestionDetailView.as_view()),
    path("templates/", PromptTemplateListCreateView.as_view()),
]