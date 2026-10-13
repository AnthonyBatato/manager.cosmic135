from django.contrib import admin
from .models import AdTrackingSettings, LandingPage, PageVersion, Domain, DomainRoute, ActionMapping, Visit, ActionClick

admin.site.register([LandingPage, PageVersion, Domain, DomainRoute, ActionMapping, Visit, ActionClick, AdTrackingSettings])

