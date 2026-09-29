from django.urls import path
from . import views

urlpatterns = [
    path("google/connect/", views.google_connect, name="google_connect"),
    path("google/callback/", views.google_callback, name="google_callback"),
    path("type/<int:booking_type_id>/", views.booking_start_id, name="booking_start_id"),
    path("type/<int:booking_type_id>/journey/<str:journey_token>/", views.booking_with_journey, name="booking_with_journey"),
    path("confirmed/<str:token>/", views.booking_confirmed, name="booking_confirmed"),
    path("cancel/<str:token>/", views.booking_cancel, name="booking_cancel"),
    path("reschedule/<str:token>/", views.booking_reschedule, name="booking_reschedule"),
    path("<slug:slug>/", views.booking_start, name="booking_start"),
]

