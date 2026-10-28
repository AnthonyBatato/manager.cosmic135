import secrets
from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone

slug_validator = RegexValidator(r"^[a-z0-9][a-z0-9-]*$", "Use lowercase letters, numbers and hyphens.")

def domain_token():
    return secrets.token_urlsafe(32)

class LandingPage(models.Model):
    SOURCE_BUILDER = "builder"
    SOURCE_UPLOAD = "upload"
    SOURCE_CHOICES = [(SOURCE_BUILDER, "Section builder"), (SOURCE_UPLOAD, "Code upload")]
    name = models.CharField(max_length=160)
    slug = models.SlugField(max_length=80, unique=True, validators=[slug_validator])
    source_type = models.CharField(max_length=12, choices=SOURCE_CHOICES, default=SOURCE_BUILDER)
    current_version = models.ForeignKey("PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="current_for")
    published_version = models.ForeignKey("PageVersion", null=True, blank=True, on_delete=models.SET_NULL, related_name="published_for")
    is_published = models.BooleanField(default=False)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.name

class PageVersion(models.Model):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="versions")
    number = models.PositiveIntegerField()
    blocks = models.JSONField(default=list, blank=True)
    artifact_path = models.CharField(max_length=500, blank=True)
    detected_actions = models.JSONField(default=list, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["page", "number"], name="unique_page_version")]
        ordering = ["-number"]

class Domain(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PROVISIONING = "provisioning"
    STATUS_VERIFIED = "verified"
    STATUS_FAILED = "failed"
    hostname = models.CharField(max_length=253, unique=True)
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="domains")
    status = models.CharField(max_length=16, default=STATUS_PENDING)
    verification_token = models.CharField(max_length=64, default=domain_token)
    provisioning_attempts = models.PositiveIntegerField(default=0)
    provisioning_error = models.TextField(blank=True)
    next_provision_at = models.DateTimeField(null=True, blank=True)
    provisioned_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.hostname

class DomainRoute(models.Model):
    domain = models.ForeignKey(Domain, on_delete=models.CASCADE, related_name="routes")
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="domain_routes")
    path = models.SlugField(max_length=100, validators=[slug_validator])
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["domain", "path"], name="unique_domain_route_path")]
        ordering = ["path"]

    def __str__(self):
        return f"{self.domain.hostname}/{self.path}/"

class ActionMapping(models.Model):
    ACTION_CHECKOUT = "checkout"
    ACTION_BOOKING = "booking"
    ACTION_FORM = "form"
    ACTION_EXTERNAL = "external-checkout"
    ACTION_CHOICES = [(x, x) for x in [ACTION_CHECKOUT, ACTION_BOOKING, ACTION_FORM, ACTION_EXTERNAL]]
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="actions")
    key = models.SlugField(max_length=80)
    action_type = models.CharField(max_length=24, choices=ACTION_CHOICES)
    label = models.CharField(max_length=120)
    target_id = models.PositiveBigIntegerField(null=True, blank=True)
    target_url = models.URLField(blank=True)
    enabled = models.BooleanField(default=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=["page", "key"], name="unique_page_action")]

class Visit(models.Model):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="visits")
    version = models.ForeignKey(PageVersion, null=True, on_delete=models.SET_NULL)
    session_key = models.CharField(max_length=64, blank=True)
    referrer = models.URLField(max_length=1000, blank=True)
    user_agent = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class ActionClick(models.Model):
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="clicks")
    action = models.ForeignKey(ActionMapping, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=64, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

class AdTrackingSettings(models.Model):
    """Per-page tracking identifiers; API secrets stay in the environment."""
    page = models.OneToOneField(LandingPage, on_delete=models.CASCADE, related_name="tracking_settings")
    meta_enabled = models.BooleanField(default=False)
    meta_pixel_id = models.CharField(max_length=120, blank=True)
    google_ads_enabled = models.BooleanField(default=False)
    google_ads_id = models.CharField(max_length=120, blank=True)
    google_ads_conversion_label = models.CharField(max_length=160, blank=True)
    openai_enabled = models.BooleanField(default=False)
    openai_pixel_id = models.CharField(max_length=120, blank=True)
    require_consent = models.BooleanField(default=True)
    updated_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "ads tracking settings"
        verbose_name_plural = "ads tracking settings"

    def clean(self):
        errors = {}
        for enabled_field, id_field, label in [
            ("meta_enabled", "meta_pixel_id", "Meta Pixel ID"),
            ("google_ads_enabled", "google_ads_id", "Google Ads ID"),
            ("openai_enabled", "openai_pixel_id", "OpenAI Pixel ID"),
        ]:
            if getattr(self, enabled_field) and not getattr(self, id_field).strip():
                errors[id_field] = f"Enter a {label} before enabling this integration."
        if errors:
            raise ValidationError(errors)

    def __str__(self):
        return f"Ads tracking for {self.page.name}"

