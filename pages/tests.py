import io
import json
import tempfile
import zipfile
from pathlib import Path
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.urls import reverse
from users.models import ApprovedEmail
from .models import ActionMapping, AdTrackingSettings, LandingPage
from .services import save_archive_version, save_builder_version, save_uploaded_version, validate_archive, validate_html_upload
from .forms import PageForm

def zip_upload(files):
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return SimpleUploadedFile("page.zip", buffer.getvalue(), content_type="application/zip")

class PageWorkflowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_user("owner@example.com", "owner@example.com", "testpass123")
        ApprovedEmail.objects.create(email=self.user.email, role="owner")
        self.client.force_login(self.user)

    def test_publish_requires_action_mapping(self):
        page = LandingPage.objects.create(name="Offer", slug="offer", created_by=self.user)
        save_builder_version(page, [{"type": "hero", "title": "Offer", "body": "Body", "action": "checkout"}], self.user)
        response = self.client.post(reverse("page_publish", args=[page.pk]))
        page.refresh_from_db()
        self.assertFalse(page.is_published)
        ActionMapping.objects.create(page=page, key="checkout", label="Buy", action_type="external-checkout", target_url="https://example.com")
        self.client.post(reverse("page_publish", args=[page.pk]))
        page.refresh_from_db()
        self.assertTrue(page.is_published)

    def test_starting_method_is_radio_and_upload_redirects_to_uploader(self):
        self.assertEqual(PageForm().fields["source_type"].widget.__class__.__name__, "RadioSelect")
        response = self.client.post(reverse("page_create"), {
            "name": "Uploaded offer", "slug": "uploaded-offer", "source_type": LandingPage.SOURCE_UPLOAD,
        })
        page = LandingPage.objects.get(slug="uploaded-offer")
        self.assertRedirects(response, reverse("page_upload", args=[page.pk]))

    def test_archive_validation_and_action_detection(self):
        upload = zip_upload({"index.html": '<a data-lpm-action="checkout">Buy</a>', "style.css": "body{}"})
        _, _, actions = validate_archive(upload)
        self.assertEqual(actions, [{"type": "checkout", "key": "checkout"}])

    def test_self_contained_txt_html_is_accepted(self):
        upload = SimpleUploadedFile(
            "ai-page.txt",
            b'<!doctype html><html><body><a data-lpm-action="external-checkout">Buy</a></body></html>',
            content_type="text/plain",
        )
        _, actions = validate_html_upload(upload)
        self.assertEqual(actions, [{"type": "external-checkout", "key": "external-checkout"}])

    @override_settings(PUBLISHED_ROOT=Path(tempfile.gettempdir()) / "cosmic-launch-html-tests")
    def test_self_contained_txt_creates_version(self):
        page = LandingPage.objects.create(name="Single file", slug="single-file", created_by=self.user)
        upload = SimpleUploadedFile(
            "page.txt", b"<!doctype html><html><body><h1>Hello</h1></body></html>", content_type="text/plain",
        )
        version = save_uploaded_version(page, upload, self.user)
        self.assertTrue((Path(tempfile.gettempdir()) / "cosmic-launch-html-tests" / version.artifact_path / "index.html").exists())
        editor = self.client.get(reverse("page_edit", args=[page.pk]))
        self.assertContains(editor, "Uploaded code")
        self.assertContains(editor, "&lt;h1&gt;Hello&lt;/h1&gt;", html=False)
        download = self.client.get(reverse("page_source_download", args=[page.pk]))
        self.assertEqual(download.status_code, 200)
        self.assertIn(b"<h1>Hello</h1>", b"".join(download.streaming_content))

    def test_archive_rejects_path_traversal(self):
        upload = zip_upload({"index.html": "ok", "../escape.js": "bad"})
        with self.assertRaises(ValidationError):
            validate_archive(upload)

    def test_archive_rejects_server_code(self):
        upload = zip_upload({"index.html": "ok", "run.py": "print('bad')"})
        with self.assertRaises(ValidationError):
            validate_archive(upload)

    @override_settings(PUBLISHED_ROOT=Path(tempfile.gettempdir()) / "cosmic-launch-tests")
    def test_archive_creates_immutable_version(self):
        page = LandingPage.objects.create(name="AI Page", slug="ai-page", created_by=self.user)
        version = save_archive_version(page, zip_upload({"index.html": "<h1>Hello</h1>"}), self.user)
        self.assertEqual(version.number, 1)
        self.assertTrue((Path(tempfile.gettempdir()) / "cosmic-launch-tests" / version.artifact_path / "index.html").exists())

    @override_settings(OPENAI_CONVERSIONS_API_KEY="server-only-secret")
    def test_owner_saves_page_specific_tracking_settings(self):
        first = LandingPage.objects.create(name="First", slug="first", created_by=self.user)
        second = LandingPage.objects.create(name="Second", slug="second", created_by=self.user)
        response = self.client.post(reverse("tracking_settings", args=[first.pk]), {
            "meta_enabled": "on",
            "meta_pixel_id": "123456789",
            "google_ads_enabled": "on",
            "google_ads_id": "AW-987654321",
            "google_ads_conversion_label": "PurchaseLabel",
            "openai_enabled": "on",
            "openai_pixel_id": "134534",
            "require_consent": "on",
        })
        self.assertRedirects(response, reverse("tracking_settings", args=[first.pk]))
        tracking = AdTrackingSettings.objects.get(page=first)
        self.assertEqual(tracking.openai_pixel_id, "134534")
        self.assertTrue(tracking.require_consent)
        self.assertFalse(AdTrackingSettings.objects.filter(page=second).exists())
        page = self.client.get(reverse("tracking_settings", args=[first.pk]))
        self.assertContains(page, "Conversions API key configured")
        self.assertNotContains(page, "server-only-secret")

    def test_tracking_requires_id_when_enabled(self):
        page = LandingPage.objects.create(name="Offer", slug="tracked-offer", created_by=self.user)
        response = self.client.post(reverse("tracking_settings", args=[page.pk]), {"openai_enabled": "on"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Enter a OpenAI Pixel ID")
        self.assertFalse(AdTrackingSettings.objects.filter(page=page).exists())

    def test_team_member_cannot_change_tracking_settings(self):
        page = LandingPage.objects.create(name="Offer", slug="owner-only", created_by=self.user)
        team = get_user_model().objects.create_user("team@example.com", "team@example.com", "testpass123")
        ApprovedEmail.objects.create(email=team.email, role="team")
        self.client.force_login(team)
        response = self.client.get(reverse("tracking_settings", args=[page.pk]))
        self.assertEqual(response.status_code, 302)

    @override_settings(DEBUG=True)
    def test_published_page_injects_page_specific_pixels_but_preview_does_not(self):
        page = LandingPage.objects.create(name="Tracked", slug="tracked", created_by=self.user)
        version = save_builder_version(page, [{"type": "hero", "title": "Tracked", "body": "Body", "action": "checkout"}], self.user)
        page.published_version = version
        page.is_published = True
        page.save(update_fields=["published_version", "is_published"])
        AdTrackingSettings.objects.create(
            page=page, meta_enabled=True, meta_pixel_id="111222333",
            google_ads_enabled=True, google_ads_id="AW-123456", google_ads_conversion_label="SaleLabel",
            openai_enabled=True, openai_pixel_id="987654", require_consent=True,
        )
        public = self.client.get(reverse("local_public_page", args=[page.slug]) + "?oppref=opaque-reference")
        self.assertContains(public, "cosmic-ads-runtime")
        self.assertContains(public, "111222333")
        self.assertContains(public, "AW-123456")
        self.assertContains(public, "987654")
        self.assertContains(public, "page_viewed")
        self.assertContains(public, "checkout_started")
        self.assertContains(public, "opaque-reference")
        preview = self.client.get(reverse("page_preview", args=[page.pk]))
        self.assertNotContains(preview, "cosmic-ads-runtime")

    def test_tracking_configuration_is_script_safe(self):
        page = LandingPage.objects.create(name="Safe", slug="safe", created_by=self.user)
        version = save_builder_version(page, [{"type": "content", "title": "Safe", "body": "Body"}], self.user)
        page.published_version = version
        page.is_published = True
        page.save(update_fields=["published_version", "is_published"])
        AdTrackingSettings.objects.create(page=page, openai_enabled=True, openai_pixel_id="</script><script>alert(1)</script>", require_consent=False)
        response = self.client.get(reverse("local_public_page", args=[page.slug]))
        self.assertNotContains(response, "</script><script>alert(1)</script>")
        self.assertContains(response, "\\u003c/script\\u003e")

