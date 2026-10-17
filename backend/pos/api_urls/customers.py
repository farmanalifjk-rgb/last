from django.urls import path
from ..views.customers import *

urlpatterns = [
    path("draft-order/customer/",AssignCustomerView.as_view()),
]