from django.urls import path
from ..views.company import *

urlpatterns = [ 
    path("company/",CompanyView.as_view()),
]