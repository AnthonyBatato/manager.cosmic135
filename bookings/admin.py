from django.contrib import admin
from .models import CalendarConnection, Host, WorkingHours, TimeOff, BookingType, SlotHold, Booking
admin.site.register([CalendarConnection, Host, WorkingHours, TimeOff, BookingType, SlotHold, Booking])

