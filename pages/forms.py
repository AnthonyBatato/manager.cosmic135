import json
import re

from django import forms
from django.utils.translation import gettext_lazy as _
from .models import ActionMapping, AdTrackingSettings, Domain, DomainRoute, LandingPage
from commerce.models import Offer

class PageForm(forms.ModelForm):
    class Meta:
        model = LandingPage
        fields = ["name", "slug", "source_type"]
        widgets = {"source_type": forms.RadioSelect}

class BuilderForm(forms.Form):
    blocks_json = forms.CharField(widget=forms.HiddenInput)

    def clean_blocks_json(self):
        try:
            blocks = json.loads(self.cleaned_data["blocks_json"])
        except (TypeError, json.JSONDecodeError) as exc:
            raise forms.ValidationError("Invalid page block data.") from exc
        if not isinstance(blocks, list) or len(blocks) > 100:
            raise forms.ValidationError("A page must contain no more than 100 blocks.")
        allowed = {"hero", "content", "benefits", "testimonials", "pricing", "faq", "cta"}
        for block in blocks:
            if not isinstance(block, dict) or block.get("type") not in allowed:
                raise forms.ValidationError("Unsupported page block.")
        return blocks

class UploadForm(forms.Form):
    archive = forms.FileField(
        label="Page file",
        help_text="ZIP bundle, or a complete self-contained HTML/HTM/TXT file",
        widget=forms.ClearableFileInput(attrs={"accept": ".zip,.html,.htm,.txt"}),
    )

class ActionMappingForm(forms.ModelForm):
    offer = forms.ModelChoiceField(queryset=Offer.objects.none(), required=False, help_text=_("Required for Stripe checkout actions."))
    booking_type_id = forms.IntegerField(required=False, min_value=1, help_text=_("Required for booking actions."))

    class Meta:
        model = ActionMapping
        fields = ["key", "label", "action_type", "target_url", "enabled"]
        help_texts = {"target_url": _("Required for registration form and external checkout actions.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["offer"].queryset = Offer.objects.filter(active=True).order_by("name")
        self.order_fields(["key", "label", "action_type", "offer", "booking_type_id", "target_url", "enabled"])
        if self.instance and self.instance.pk:
            if self.instance.action_type == ActionMapping.ACTION_CHECKOUT:
                self.fields["offer"].initial = self.instance.target_id
            elif self.instance.action_type == ActionMapping.ACTION_BOOKING:
                self.fields["booking_type_id"].initial = self.instance.target_id

    def clean(self):
        cleaned = super().clean()
        action_type = cleaned.get("action_type")
        if action_type == ActionMapping.ACTION_CHECKOUT and not cleaned.get("offer"):
            self.add_error("offer", _("Choose a Stripe offer."))
        if action_type == ActionMapping.ACTION_BOOKING and not cleaned.get("booking_type_id"):
            self.add_error("booking_type_id", _("Enter a booking type ID."))
        if action_type in {ActionMapping.ACTION_FORM, ActionMapping.ACTION_EXTERNAL} and not cleaned.get("target_url"):
            self.add_error("target_url", _("Enter the destination URL."))
        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.action_type == ActionMapping.ACTION_CHECKOUT:
            instance.target_id = self.cleaned_data["offer"].pk
            instance.target_url = ""
        elif instance.action_type == ActionMapping.ACTION_BOOKING:
            instance.target_id = self.cleaned_data["booking_type_id"]
            instance.target_url = ""
        else:
            instance.target_id = None
        if commit:
            instance.save()
        return instance

class DomainForm(forms.ModelForm):
    class Meta:
        model = Domain
        fields = ["hostname"]

    def clean_hostname(self):
        hostname = self.cleaned_data["hostname"].strip().lower().rstrip(".")
        if "://" in hostname or "/" in hostname or ":" in hostname:
            raise forms.ValidationError(_("Enter a hostname only, without https://, a path, or a port."))
        labels = hostname.split(".")
        if len(labels) < 2 or any(
            not label or len(label) > 63 or not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]*[a-z0-9])?", label)
            for label in labels
        ):
            raise forms.ValidationError(_("Enter a valid domain such as promo.example.com."))
        return hostname

class DomainRouteForm(forms.ModelForm):
    RESERVED_PATHS = {
        "admin", "accounts", "api", "book", "i18n", "p", "pages", "payments",
        "preview-assets-public", "preview-public", "r", "static",
    }

    class Meta:
        model = DomainRoute
        fields = ["path", "page"]
        labels = {"path": _("URL path"), "page": _("Landing page")}
        help_texts = {"path": _("Use lowercase letters, numbers, and hyphens, such as thankyou.")}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["page"].queryset = LandingPage.objects.order_by("name")

    def clean_path(self):
        path = self.cleaned_data["path"].strip("/").lower()
        if path in self.RESERVED_PATHS:
            raise forms.ValidationError(_("This path is reserved by the application. Choose another path."))
        return path

class AdTrackingSettingsForm(forms.ModelForm):
    class Meta:
        model = AdTrackingSettings
        fields = [
            "meta_enabled", "meta_pixel_id", "google_ads_enabled", "google_ads_id",
            "google_ads_conversion_label", "openai_enabled", "openai_pixel_id", "require_consent",
        ]
        labels = {
            "meta_enabled": _("Enable Meta Pixel"),
            "meta_pixel_id": _("Meta Pixel ID"),
            "google_ads_enabled": _("Enable Google Ads tracking"),
            "google_ads_id": _("Google Ads ID"),
            "google_ads_conversion_label": _("Default conversion label"),
            "openai_enabled": _("Enable OpenAI / ChatGPT Ads Pixel"),
            "openai_pixel_id": _("OpenAI Pixel ID"),
            "require_consent": _("Wait for visitor consent before browser tracking"),
        }
        help_texts = {
            "meta_pixel_id": _("The numeric ID shown in Meta Events Manager."),
            "google_ads_id": _("Usually starts with AW-."),
            "google_ads_conversion_label": _("Optional default label for Google Ads conversion events."),
            "openai_pixel_id": _("Create this in the Conversions area of OpenAI Ads Manager."),
        }

    def clean(self):
        cleaned = super().clean()
        for field in ["meta_pixel_id", "google_ads_id", "google_ads_conversion_label", "openai_pixel_id"]:
            cleaned[field] = (cleaned.get(field) or "").strip()
        return cleaned


