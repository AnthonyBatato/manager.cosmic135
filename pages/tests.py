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
from .models import ActionMapping, LandingPage
from .services import save_archive_version, save_builder_version, validate_archive
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

