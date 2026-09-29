from django.contrib import admin
from django.urls import include, path
from django.views.i18n import set_language

urlpatterns = [
    path("admin/", admin.site.urls),
    path("accounts/", include("allauth.urls")),
    path("i18n/setlang/", set_language, name="set_language"),
    path("payments/", include("commerce.urls")),
    path("book/", include("bookings.urls")),
    path("api/integrations/", include("integrations.urls")),
    path("", include("pages.urls")),
]

