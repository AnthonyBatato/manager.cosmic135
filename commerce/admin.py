from django.contrib import admin
from .models import AdConversionDelivery, Offer, Customer, CheckoutAttempt, Payment, StripeEvent, Journey


@admin.register(Offer)
class OfferAdmin(admin.ModelAdmin):
    list_display = ("name", "currency", "max_completed_orders", "sales_start_at", "sales_end_at", "registration_quantity", "active")
    list_filter = ("post_payment_email", "active")
    search_fields = ("name", "stripe_test_price_id", "stripe_live_price_id")


admin.site.register([Customer, CheckoutAttempt, Payment, StripeEvent, Journey, AdConversionDelivery])

