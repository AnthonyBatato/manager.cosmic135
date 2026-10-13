from django.contrib import admin
from .models import AdTrackingSettings, LandingPage, PageVersion, Domain, ActionMapping, Visit, ActionClick

admin.site.register([LandingPage, PageVersion, Domain, ActionMapping, Visit, ActionClick, AdTrackingSettings])

