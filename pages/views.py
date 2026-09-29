import json
import mimetypes
import re
import dns.resolver
from pathlib import Path
from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.core import signing
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST
from .forms import ActionMappingForm, BuilderForm, DomainForm, PageForm, UploadForm
from .models import ActionClick, ActionMapping, Domain, LandingPage, Visit
from .services import render_builder, save_archive_version, save_builder_version, serve_file_path
from users.auth import owner_required

def _public_page_for_host(host):
    if host.endswith("." + settings.PUBLIC_ROOT_HOST):
        slug = host[: -(len(settings.PUBLIC_ROOT_HOST) + 1)]
        return LandingPage.objects.filter(slug=slug, is_published=True).select_related("published_version").first()
    domain = Domain.objects.filter(hostname=host, status=Domain.STATUS_VERIFIED).select_related("page__published_version").first()
    return domain.page if domain and domain.page.is_published else None

def home(request):
    if not request.is_manager_host:
        page = _public_page_for_host(request.site_host)
        if not page:
            raise Http404
        return render_public_page(request, page)
    if not request.user.is_authenticated:
        return redirect("account_login")
    stats = {
        "pages": LandingPage.objects.count(),
        "published": LandingPage.objects.filter(is_published=True).count(),
        "visits": Visit.objects.count(),
        "payments": __import__("commerce.models", fromlist=["Payment"]).Payment.objects.count(),
        "pending": __import__("commerce.models", fromlist=["Journey"]).Journey.objects.filter(status="pending").count(),
        "bookings": __import__("bookings.models", fromlist=["Booking"]).Booking.objects.filter(status="confirmed").count(),
    }
    pages = LandingPage.objects.annotate(visit_count=Count("visits"), click_count=Count("clicks", distinct=True)).order_by("-updated_at")[:6]
    return render(request, "dashboard.html", {"stats": stats, "pages": pages})

@login_required
def page_list(request):
    return render(request, "pages/page_list.html", {"pages": LandingPage.objects.order_by("-updated_at")})

@login_required
def page_create(request):
    form = PageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        page = form.save(commit=False)
        page.created_by = request.user
        page.save()
        messages.success(request, "Page created. Add the first version now.")
        return redirect("page_edit", pk=page.pk)
    return render(request, "pages/page_form.html", {"form": form})

@login_required
def page_edit(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    initial_blocks = page.current_version.blocks if page.current_version and page.current_version.blocks else [{"type":"hero","eyebrow":"NEW OFFER","title":page.name,"body":"Add your sales message here.","button":"Continue","action":"checkout"}]
    form = BuilderForm(request.POST or None, initial={"blocks_json": json.dumps(initial_blocks)})
    if request.method == "POST" and form.is_valid():
        save_builder_version(page, form.cleaned_data["blocks_json"], request.user)
        messages.success(request, "A new immutable page version was saved.")
        return redirect("page_edit", pk=page.pk)
    return render(request, "pages/page_edit.html", {"page": page, "form": form, "blocks_json": json.dumps(initial_blocks), "actions": page.actions.all()})

@login_required
def page_upload(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    form = UploadForm(request.POST or None, request.FILES or None)
    if request.method == "POST" and form.is_valid():
        try:
            version = save_archive_version(page, form.cleaned_data["archive"], request.user)
        except Exception as exc:
            form.add_error("archive", str(exc))
        else:
            messages.success(request, f"Version {version.number} uploaded and validated.")
            return redirect("page_edit", pk=page.pk)
    return render(request, "pages/page_upload.html", {"page": page, "form": form})

@login_required
@require_POST
def page_publish(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    if not page.current_version:
        messages.error(request, "Save or upload a version before publishing.")
    else:
        required = {item.get("key") for item in page.current_version.detected_actions}
        required |= {block.get("action") for block in page.current_version.blocks if block.get("action")}
        mapped = set(page.actions.filter(enabled=True).values_list("key", flat=True))
        missing = sorted(required - mapped)
        if missing:
            messages.error(request, "Map these page actions before publishing: " + ", ".join(missing))
            return redirect("page_edit", pk=pk)
        page.published_version = page.current_version
        page.is_published = True
        page.save(update_fields=["published_version", "is_published", "updated_at"])
        messages.success(request, f"Published version {page.current_version.number}.")
    return redirect("page_edit", pk=pk)

@login_required
@require_POST
def page_rollback(request, pk, version):
    page = get_object_or_404(LandingPage, pk=pk)
    selected = get_object_or_404(page.versions, number=version)
    page.current_version = selected
    page.published_version = selected
    page.is_published = True
    page.save(update_fields=["current_version", "published_version", "is_published", "updated_at"])
    messages.success(request, f"Rolled back to version {version}.")
    return redirect("page_edit", pk=pk)

def render_public_page(request, page, preview=False, local=False, preview_token=None):
    version = page.current_version if preview else page.published_version
    if not version:
        raise Http404
    if not preview:
        if not request.session.session_key:
            request.session.create()
        Visit.objects.create(page=page, version=version, session_key=request.session.session_key or "", referrer=request.META.get("HTTP_REFERER", "")[:1000], user_agent=request.META.get("HTTP_USER_AGENT", "")[:500])
    if version.blocks:
        source = render_builder(version.blocks, page)
    else:
        path = serve_file_path(version)
        if not path.exists(): raise Http404
        source = path.read_text(encoding="utf-8")
        if preview_token:
            base_url = reverse("public_preview_asset", kwargs={"pk": page.pk, "token": preview_token, "path": "__asset__"}).replace("__asset__", "")
        elif preview:
            base_url = reverse("preview_asset", kwargs={"pk": page.pk, "path": "__asset__"}).replace("__asset__", "")
        elif local:
            base_url = reverse("public_asset", kwargs={"page_slug": page.slug, "path": "__asset__"}).replace("__asset__", "")
        else:
            base_url = "/"
        base_tag = f'<base href="{base_url}">'
        source = re.sub(r"<head(\s[^>]*)?>", lambda match: match.group(0) + base_tag, source, count=1, flags=re.I)
    def rewrite(match):
        kind = match.group(1).lower()
        key = (match.group(2) or kind).lower()
        href = reverse("action_redirect", kwargs={"page_slug": page.slug, "action_key": key})
        return f'data-lpm-action="{kind}:{key}" href="{href}"'
    source = re.sub(r'data-lpm-action=["\'](checkout|booking|form|external-checkout)(?::([a-z0-9-]+))?["\'](?:\s+href=["\'][^"\']*["\'])?', rewrite, source, flags=re.I)
    return HttpResponse(source, content_type="text/html; charset=utf-8", headers={"Content-Security-Policy": "frame-ancestors 'self' https://manager.cosmic135.com"})

@login_required
def page_preview(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    if settings.DEBUG:
        return render_public_page(request, page, preview=True)
    token = signing.TimestampSigner(salt="page-preview").sign(str(page.pk))
    path = reverse("public_preview", kwargs={"pk": page.pk, "token": token})
    return redirect(f"https://{settings.PREVIEW_HOST}{path}")

def public_preview(request, pk, token):
    if request.site_host != settings.PREVIEW_HOST:
        raise Http404
    try:
        value = signing.TimestampSigner(salt="page-preview").unsign(token, max_age=600)
    except signing.BadSignature:
        raise Http404
    if value != str(pk):
        raise Http404
    return render_public_page(request, get_object_or_404(LandingPage, pk=pk), preview=True, preview_token=token)

def public_preview_asset(request, pk, token, path):
    if request.site_host != settings.PREVIEW_HOST:
        raise Http404
    try:
        value = signing.TimestampSigner(salt="page-preview").unsign(token, max_age=600)
    except signing.BadSignature:
        raise Http404
    if value != str(pk):
        raise Http404
    page = get_object_or_404(LandingPage, pk=pk)
    version = page.current_version
    if not version or not version.artifact_path:
        raise Http404
    try: target = serve_file_path(version, path)
    except FileNotFoundError: raise Http404
    if not target.is_file(): raise Http404
    return FileResponse(target.open("rb"), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

@login_required
def preview_asset(request, pk, path):
    page = get_object_or_404(LandingPage, pk=pk)
    version = page.current_version
    if not version or not version.artifact_path:
        raise Http404
    try: target = serve_file_path(version, path)
    except FileNotFoundError: raise Http404
    if not target.is_file(): raise Http404
    return FileResponse(target.open("rb"), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

@login_required
def action_create(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    form = ActionMappingForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        action = form.save(commit=False)
        action.page = page
        action.save()
        messages.success(request, "Action mapping saved.")
        return redirect("page_edit", pk=page.pk)
    return render(request, "pages/action_form.html", {"page": page, "form": form})

@owner_required
def domain_create(request, pk):
    page = get_object_or_404(LandingPage, pk=pk)
    form = DomainForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        domain = form.save(commit=False)
        domain.page = page
        domain.hostname = domain.hostname.lower().rstrip(".")
        domain.save()
        messages.success(request, "Domain added. Create the shown DNS record, then verify it in Django admin.")
        return redirect("page_edit", pk=page.pk)
    return render(request, "pages/domain_form.html", {"page": page, "form": form})

@owner_required
@require_POST
def domain_verify(request, pk, domain_pk):
    page = get_object_or_404(LandingPage, pk=pk)
    domain = get_object_or_404(Domain, pk=domain_pk, page=page)
    try:
        answers = dns.resolver.resolve(f"_cosmic-verify.{domain.hostname}", "TXT")
        values = {part.decode() for answer in answers for part in answer.strings}
    except Exception:
        values = set()
    if domain.verification_token in values:
        domain.status = Domain.STATUS_VERIFIED
        domain.save(update_fields=["status"])
        messages.success(request, "Domain verified and ready for HTTPS.")
    else:
        messages.error(request, "Verification TXT record was not found yet.")
    return redirect("page_edit", pk=pk)

def public_asset(request, page_slug, path):
    page = get_object_or_404(LandingPage, slug=page_slug, is_published=True)
    if not page.published_version or not page.published_version.artifact_path: raise Http404
    try: target = serve_file_path(page.published_version, path)
    except FileNotFoundError: raise Http404
    if not target.is_file(): raise Http404
    return FileResponse(target.open("rb"), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

def public_host_asset(request, path):
    if request.is_manager_host:
        raise Http404
    page = _public_page_for_host(request.site_host)
    if not page or not page.published_version or not page.published_version.artifact_path:
        raise Http404
    try: target = serve_file_path(page.published_version, path)
    except FileNotFoundError: raise Http404
    if not target.is_file(): raise Http404
    return FileResponse(target.open("rb"), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")

def local_public_page(request, slug):
    return render_public_page(request, get_object_or_404(LandingPage, slug=slug, is_published=True), local=True)

def action_redirect(request, page_slug, action_key):
    page = get_object_or_404(LandingPage, slug=page_slug, is_published=True)
    action = get_object_or_404(ActionMapping, page=page, key=action_key, enabled=True)
    if not request.session.session_key: request.session.create()
    ActionClick.objects.create(page=page, action=action, session_key=request.session.session_key or "")
    if action.action_type == ActionMapping.ACTION_CHECKOUT:
        return redirect("checkout_start", action_id=action.pk)
    if action.action_type == ActionMapping.ACTION_BOOKING:
        if action.target_id:
            return redirect("booking_start_id", booking_type_id=action.target_id)
        return redirect("booking_start", slug=action.target_url or action.key)
    if action.action_type in {ActionMapping.ACTION_FORM, ActionMapping.ACTION_EXTERNAL}:
        return redirect(action.target_url)
    raise Http404

def allow_certificate(request):
    domain = request.GET.get("domain", "").lower().rstrip(".")
    allowed = domain in {settings.MANAGER_HOST, settings.PUBLIC_ROOT_HOST, settings.PREVIEW_HOST} or domain.endswith("." + settings.PUBLIC_ROOT_HOST) or Domain.objects.filter(hostname=domain, status=Domain.STATUS_VERIFIED).exists()
    return HttpResponse("allowed" if allowed else "denied", status=200 if allowed else 403)

