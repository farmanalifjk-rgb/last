from django.urls import path
from .views import (
    StockTransferListCreateView, StockTransferDetailView, ReceiveTransferView,
    PutAwayRuleListCreateView, SuggestPutAwayView, PutAwayTaskListView,
    CompletePutAwayView, ReplenishmentGenerateView, ReplenishmentListView,
)

urlpatterns = [
    path("transfers/", StockTransferListCreateView.as_view()),
    path("transfers/<int:pk>/", StockTransferDetailView.as_view()),
    path("transfers/<int:pk>/receive/", ReceiveTransferView.as_view()),
    path("putaway-rules/", PutAwayRuleListCreateView.as_view()),
    path("putaway/suggest/", SuggestPutAwayView.as_view()),
    path("putaway-tasks/", PutAwayTaskListView.as_view()),
    path("putaway-tasks/<int:pk>/complete/", CompletePutAwayView.as_view()),
    path("warehouses/<int:pk>/replenishment/generate/", ReplenishmentGenerateView.as_view()),
    path("replenishment/", ReplenishmentListView.as_view()),
]