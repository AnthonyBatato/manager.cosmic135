from django.urls import path
from . import views

urlpatterns = [
    path("start/<int:action_id>/", views.checkout_start, name="checkout_start"),
    path("success/", views.checkout_success, name="checkout_success"),
    path("continue/<str:token>/", views.continue_journey, name="continue_journey"),
    path("webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
]

