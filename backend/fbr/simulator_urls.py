"""Test-only endpoints emulating the Tier-1 IMS local component contract."""
from django.urls import path

from .simulator import SandboxIMSSimulatorView

urlpatterns = [
    path("sandbox/api/IMSFiscal/get", SandboxIMSSimulatorView.as_view(), name="fbr-simulator-sandbox-health"),
    path(
        "sandbox/api/IMSFiscal/GetInvoiceNumberByModel",
        SandboxIMSSimulatorView.as_view(),
        name="fbr-simulator-sandbox-fiscalize",
    ),
]
