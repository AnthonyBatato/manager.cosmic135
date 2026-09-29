import secrets
from django.conf import settings
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
    STATUS_VERIFIED = "verified"
    hostname = models.CharField(max_length=253, unique=True)
    page = models.ForeignKey(LandingPage, on_delete=models.CASCADE, related_name="domains")
    status = models.CharField(max_length=16, default=STATUS_PENDING)
    verification_token = models.CharField(max_length=64, default=domain_token)
    created_at = models.DateTimeField(auto_now_add=True)

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

