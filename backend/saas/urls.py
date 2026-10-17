from django.urls import path
from .billing_facade import (BillingOverviewView, BillingPlansView, BillingSubscriptionView, BillingUsageView, BillingInvoicesView, BillingProviderStatusView)
from .views import (
    PlanListView, TenantMeView, CreateTenantView, SwitchTenantView,
    TenantMembersView, SubscriptionCheckoutView, CancelSubscriptionView,
    InvoicesView, LimitCheckView, StripeWebhookView,
)
from .manual_billing_views import (
    ManualPaymentMethodsView,
    SubscriptionRequestListCreateView,
    ManualPaymentSubmissionView,
    TenantManualPaymentListView,
    PlatformManualPaymentListView,
    PlatformManualPaymentVerifyView,
    PlatformManualPaymentRejectView,
)

urlpatterns = [
    path("plans/", PlanListView.as_view()),
    path("tenant/", TenantMeView.as_view()),
    path("tenants/", CreateTenantView.as_view()),
    path("tenants/switch/", SwitchTenantView.as_view()),
    path("tenants/members/", TenantMembersView.as_view()),
    path("subscription/checkout/", SubscriptionCheckoutView.as_view()),
    path("subscription/cancel/", CancelSubscriptionView.as_view()),
    path("invoices/", InvoicesView.as_view()),
    path("limits/", LimitCheckView.as_view()),
    path("stripe/webhook/", StripeWebhookView.as_view()),
    path("billing/overview/", BillingOverviewView.as_view()),
    path("billing/plans/", BillingPlansView.as_view()),
    path("billing/subscription/", BillingSubscriptionView.as_view()),
    path("billing/usage/", BillingUsageView.as_view()),
    path("billing/invoices/", BillingInvoicesView.as_view()),
    path("billing/provider-status/", BillingProviderStatusView.as_view()),
    path("billing/manual-methods/", ManualPaymentMethodsView.as_view()),
    path("billing/requests/", SubscriptionRequestListCreateView.as_view()),
    path("billing/requests/<int:request_id>/submit-payment/", ManualPaymentSubmissionView.as_view()),
    path("billing/payments/", TenantManualPaymentListView.as_view()),
    path("billing/admin/payments/", PlatformManualPaymentListView.as_view()),
    path("billing/admin/payments/<int:payment_id>/verify/", PlatformManualPaymentVerifyView.as_view()),
    path("billing/admin/payments/<int:payment_id>/reject/", PlatformManualPaymentRejectView.as_view()),
]

