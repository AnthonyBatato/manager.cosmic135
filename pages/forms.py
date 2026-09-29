import json
from django import forms
from .models import ActionMapping, Domain, LandingPage

class PageForm(forms.ModelForm):
    class Meta:
        model = LandingPage
        fields = ["name", "slug", "source_type"]

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
    archive = forms.FileField(help_text="ZIP containing index.html and relative assets")

class ActionMappingForm(forms.ModelForm):
    class Meta:
        model = ActionMapping
        fields = ["key", "label", "action_type", "target_id", "target_url", "enabled"]
        help_texts = {"target_id": "Offer ID for checkout or booking type ID for booking.", "target_url": "Required for form and external checkout actions."}

class DomainForm(forms.ModelForm):
    class Meta:
        model = Domain
        fields = ["hostname"]


