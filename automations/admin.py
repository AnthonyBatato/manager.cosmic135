from django.contrib import admin
from .models import EmailTemplate, ReminderStep, EmailDelivery
admin.site.register([EmailTemplate, ReminderStep, EmailDelivery])
