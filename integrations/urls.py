from django.urls import path
from .views import form_completed, manual_payments

urlpatterns = [
    path("forms/completed/", form_completed, name="form_completed"),
    path("manual-payments/", manual_payments, name="integration_manual_payments"),
]

