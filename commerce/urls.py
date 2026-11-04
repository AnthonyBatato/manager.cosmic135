from django.urls import path
from . import views

urlpatterns = [
    path("settings/", views.payment_settings, name="payment_settings"),
    path("offers/new/", views.offer_create, name="offer_create"),
    path("offers/<int:pk>/", views.offer_edit, name="offer_edit"),
    path("start/<int:action_id>/", views.checkout_start, name="checkout_start"),
    path("success/", views.checkout_success, name="checkout_success"),
    path("status/", views.checkout_status, name="checkout_status"),
    path("continue/<str:token>/", views.continue_journey, name="continue_journey"),
    path("webhook/stripe/", views.stripe_webhook, name="stripe_webhook"),
]

