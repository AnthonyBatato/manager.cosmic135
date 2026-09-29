from django.urls import path
from .views import form_completed

urlpatterns = [path("forms/completed/", form_completed, name="form_completed")]

