from django import forms
from django.core.exceptions import ValidationError

from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            "name", "currency", "stripe_test_price_id", "stripe_live_price_id",
            "destination_type", "destination_id", "destination_url",
            "post_payment_email", "active",
        ]
        labels = {
            "stripe_test_price_id": "Stripe sandbox Price ID",
            "stripe_live_price_id": "Stripe live Price ID",
            "destination_id": "Booking type ID",
            "destination_url": "Registration form URL",
            "post_payment_email": "Email after payment",
        }
        help_texts = {
            "stripe_test_price_id": "Starts with price_. Use the price from the Stripe sandbox.",
            "stripe_live_price_id": "Starts with price_. Add this only when the live product is ready.",
            "destination_url": "The customer receives this link with a secure journey_token after payment.",
        }

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("stripe_test_price_id") or cleaned.get("stripe_live_price_id")):
            raise ValidationError("Add at least one Stripe Price ID.")
        needs_next_step = cleaned.get("post_payment_email") in {
            Offer.EMAIL_REGISTRATION, Offer.EMAIL_BOTH,
        }
        if needs_next_step and cleaned.get("destination_type") == "form" and not cleaned.get("destination_url"):
            self.add_error("destination_url", "Enter the registration form URL.")
        if needs_next_step and cleaned.get("destination_type") == "booking" and not cleaned.get("destination_id"):
            self.add_error("destination_id", "Enter the booking type ID.")
        return cleaned
