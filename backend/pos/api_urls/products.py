from django.urls import path
from ..views.products import *

urlpatterns = [
    path("product/barcode/<str:barcode>/", product_by_barcode),
]