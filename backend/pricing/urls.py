from django.urls import path

from .views import (
    BuyXGetYDetailView, BuyXGetYListCreateView, CustomerGroupOptionListView, CustomerGroupPriceDetailView, CustomerGroupPriceListCreateView,
    PriceListDetailView, PriceListItemDetailView, PriceListItemListCreateView, PriceListListCreateView,
    ResolvePriceView, TimeBasedPriceDetailView, TimeBasedPriceListCreateView, VolumeTierDetailView, VolumeTierListCreateView,
)

urlpatterns = [
    path("price-lists/", PriceListListCreateView.as_view()),
    path("price-lists/<int:pk>/", PriceListDetailView.as_view()),
    path("price-lists/<int:price_list_id>/items/", PriceListItemListCreateView.as_view()),
    path("price-lists/<int:price_list_id>/items/<int:pk>/", PriceListItemDetailView.as_view()),
    path("customer-groups/", CustomerGroupOptionListView.as_view()),
    path("group-prices/", CustomerGroupPriceListCreateView.as_view()),
    path("group-prices/<int:pk>/", CustomerGroupPriceDetailView.as_view()),
    path("volume-tiers/", VolumeTierListCreateView.as_view()),
    path("volume-tiers/<int:pk>/", VolumeTierDetailView.as_view()),
    path("time-prices/", TimeBasedPriceListCreateView.as_view()),
    path("time-prices/<int:pk>/", TimeBasedPriceDetailView.as_view()),
    path("buyx-gety/", BuyXGetYListCreateView.as_view()),
    path("buyx-gety/<int:pk>/", BuyXGetYDetailView.as_view()),
    path("resolve/", ResolvePriceView.as_view()),
]
