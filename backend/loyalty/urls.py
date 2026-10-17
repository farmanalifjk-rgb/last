from django.urls import path, include
from rest_framework.routers import DefaultRouter
from loyalty.views import (
    LoyaltyProgramView, MembershipTierViewSet, LoyaltyTransactionViewSet,
    CouponViewSet, PromotionViewSet,
)

router = DefaultRouter()
router.register(r"loyalty/tiers",        MembershipTierViewSet,     basename="loyalty-tiers")
router.register(r"loyalty/transactions", LoyaltyTransactionViewSet, basename="loyalty-transactions")
router.register(r"loyalty/coupons",      CouponViewSet,             basename="loyalty-coupons")
router.register(r"loyalty/promotions",   PromotionViewSet,          basename="loyalty-promotions")

urlpatterns = [
    path("", include(router.urls)),
    path("loyalty/program/", LoyaltyProgramView.as_view(), name="loyalty-program"),
]


