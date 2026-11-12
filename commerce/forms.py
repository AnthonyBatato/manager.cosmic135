from django import forms
from django.core.exceptions import ValidationError

from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            "name", "currency", "stripe_test_price_id", "stripe_live_price_id",
            "destination_type", "destination_id", "cosmic_tools_course_id", "destination_url",
            "registration_quantity", "post_payment_email",
            "email_subject_zh", "email_body_zh", "email_subject_en", "email_body_en",
            "active",
        ]
        labels = {
            "stripe_test_price_id": "Stripe sandbox Price ID",
            "stripe_live_price_id": "Stripe live Price ID",
            "destination_id": "Booking type ID",
            "cosmic_tools_course_id": "Cosmic Tools course / form ID",
            "registration_quantity": "Participant registration links",
            "destination_url": "Registration form URL",
            "post_payment_email": "Email after payment",
            "email_subject_zh": "Chinese email subject (optional override)",
            "email_body_zh": "Chinese email body (optional override)",
            "email_subject_en": "English email subject (optional override)",
            "email_body_en": "English email body (optional override)",
        }
        help_texts = {
            "stripe_test_price_id": "Starts with price_. Use the price from the Stripe sandbox.",
            "stripe_live_price_id": "Starts with price_. Add this only when the live product is ready.",
            "cosmic_tools_course_id": "Recommended for Cosmic Tools. A unique customer registration link is generated after Stripe confirms payment.",
            "registration_quantity": "Use 1 for a single ticket and 2 for a duo ticket.",
            "email_body_zh": "Leave blank to use the default template. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
            "email_body_en": "Leave blank to use the default template. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
            "destination_url": "Fallback: use an existing registration form URL when Cosmic Tools automation is not selected.",
        }

    def clean(self):
        cleaned = super().clean()
        if not (cleaned.get("stripe_test_price_id") or cleaned.get("stripe_live_price_id")):
            raise ValidationError("Add at least one Stripe Price ID.")
        needs_next_step = cleaned.get("post_payment_email") in {
            Offer.EMAIL_REGISTRATION, Offer.EMAIL_BOTH,
        }
        if (
            needs_next_step
            and cleaned.get("destination_type") == "form"
            and not cleaned.get("cosmic_tools_course_id")
            and not cleaned.get("destination_url")
        ):
            self.add_error("destination_url", "Select a Cosmic Tools course / form ID or enter a registration form URL.")
        if needs_next_step and cleaned.get("destination_type") == "booking" and not cleaned.get("destination_id"):
            self.add_error("destination_id", "Enter the booking type ID.")
        if (cleaned.get("registration_quantity") or 0) < 1:
            self.add_error("registration_quantity", "Create at least one participant registration link.")
        return cleaned
