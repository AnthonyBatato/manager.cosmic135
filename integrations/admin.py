from django.contrib import admin
from .models import FormCompletionEvent, RegistrationSeat
admin.site.register([FormCompletionEvent, RegistrationSeat])
