import json
from django import forms
from django.utils.translation import gettext_lazy as _
from .models import ActionMapping, AdTrackingSettings, Domain, LandingPage

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
    class Meta:
        model = ActionMapping
        fields = ["key", "label", "action_type", "target_id", "target_url", "enabled"]
        help_texts = {"target_id": "Offer ID for checkout or booking type ID for booking.", "target_url": "Required for form and external checkout actions."}

class DomainForm(forms.ModelForm):
    class Meta:
        model = Domain
        fields = ["hostname"]

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


