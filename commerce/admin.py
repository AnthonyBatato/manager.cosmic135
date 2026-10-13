from django.contrib import admin
from .models import AdConversionDelivery, Offer, Customer, CheckoutAttempt, Payment, StripeEvent, Journey
admin.site.register([Offer, Customer, CheckoutAttempt, Payment, StripeEvent, Journey, AdConversionDelivery])

