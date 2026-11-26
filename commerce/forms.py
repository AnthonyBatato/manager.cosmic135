from django import forms
from django.core.exceptions import ValidationError
import uuid

from .models import Offer


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = [
            "name", "currency", "stripe_test_price_id", "stripe_live_price_id",
            "stripe_test_payment_link_id", "stripe_test_payment_link_url",
            "stripe_live_payment_link_id", "stripe_live_payment_link_url",
            "thank_you_page",
            "destination_type", "destination_id", "cosmic_tools_course_id", "destination_url",
            "registration_quantity", "post_payment_email",
            "sales_start_at", "sales_end_at", "max_completed_orders",
            "email_subject_zh", "email_body_zh", "email_subject_en", "email_body_en",
            "reminder_subject_zh", "reminder_body_zh", "reminder_subject_en", "reminder_body_en",
            "active",
        ]
        labels = {
            "stripe_test_price_id": "Stripe sandbox Price ID",
            "stripe_live_price_id": "Stripe live Price ID",
            "destination_id": "Booking type ID",
            "cosmic_tools_course_id": "Cosmic Tools course / form ID",
            "registration_quantity": "Participant registration links",
            "sales_start_at": "Sales start",
            "sales_end_at": "Sales end",
            "max_completed_orders": "Maximum completed orders",
            "thank_you_page": "Thank-you design page",
            "destination_url": "Registration form URL",
            "post_payment_email": "Email after payment",
            "email_subject_zh": "Chinese email subject (optional override)",
            "email_body_zh": "Chinese email body (optional override)",
            "email_subject_en": "English email subject (optional override)",
            "email_body_en": "English email body (optional override)",
            "reminder_subject_zh": "Chinese reminder subject (optional override)",
            "reminder_body_zh": "Chinese reminder body (optional override)",
            "reminder_subject_en": "English reminder subject (optional override)",
            "reminder_body_en": "English reminder body (optional override)",
        }
        help_texts = {
            "stripe_test_price_id": "Starts with price_. Use the price from the Stripe sandbox.",
            "stripe_live_price_id": "Starts with price_. Add this only when the live product is ready.",
            "cosmic_tools_course_id": "Recommended for Cosmic Tools. A unique customer registration link is generated after Stripe confirms payment.",
            "registration_quantity": "Use 1 for a single ticket and 2 for a duo ticket.",
            "max_completed_orders": "For first-come-first-served offers, Stripe must use a limited Payment Link with this same completed-session limit.",
            "thank_you_page": "Create or upload the design under Landing Pages, then select it here. The verified registration buttons are inserted automatically.",
            "email_body_zh": "Leave blank to use the default template. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
            "email_body_en": "Leave blank to use the default template. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
            "reminder_body_zh": "Leave blank to use the default reminder. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
            "reminder_body_en": "Leave blank to use the default reminder. Supports {{ offer.name }}, {{ action_url }}, and registration_links template loops.",
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
        start = cleaned.get("sales_start_at")
        end = cleaned.get("sales_end_at")
        if start and end and end <= start:
            self.add_error("sales_end_at", "Sales end must be later than sales start.")
        if cleaned.get("max_completed_orders") and not (
            cleaned.get("stripe_test_payment_link_id") or cleaned.get("stripe_live_payment_link_id")
        ):
            self.add_error("max_completed_orders", "Limited offers require a Stripe Payment Link ID.")
        return cleaned


class ManualPaymentForm(forms.Form):
    offer = forms.ModelChoiceField(
        queryset=Offer.objects.none(),
        label="Offer / email configuration",
        help_text="Choose Single, Duo, or the applicable event offer. The offer controls how many registration links are created.",
    )
    customer_name = forms.CharField(max_length=160, label="Customer name")
    customer_email = forms.EmailField(label="Customer email")
    customer_phone = forms.CharField(max_length=40, required=False, label="Phone / WhatsApp")
    amount = forms.DecimalField(
        max_digits=10, decimal_places=2, min_value=0.01,
        label="Amount already received",
        help_text="Enter the amount in the selected offer's currency, for example 3980.00.",
    )
    payment_note = forms.CharField(
        max_length=250, required=False, label="Internal payment note",
        help_text="Optional reference such as bank transfer date or receipt number. This is not included in the customer email.",
    )
    payment_confirmed = forms.BooleanField(
        label="I confirm that this payment was already received",
        help_text="Submitting creates a paid customer journey and queues the registration email.",
    )
    submission_token = forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offer"].queryset = Offer.objects.filter(active=True).order_by("name")
        if not self.is_bound:
            self.initial.setdefault("submission_token", uuid.uuid4())
