import html
import json
import mimetypes
import re
import secrets
import shutil
import zipfile
from pathlib import Path, PurePosixPath
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils.text import slugify
from PIL import Image, UnidentifiedImageError
from .models import LandingPage, PageVersion

MAX_ARCHIVE_BYTES = 25 * 1024 * 1024
MAX_EXPANDED_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES = 500
DENIED_SUFFIXES = {".py", ".php", ".rb", ".pl", ".sh", ".bash", ".ps1", ".bat", ".cmd", ".exe", ".dll", ".so", ".jar", ".zip", ".tar", ".gz", ".7z"}
ALLOWED_SUFFIXES = {".html", ".htm", ".css", ".js", ".json", ".txt", ".xml", ".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".woff", ".woff2", ".ttf", ".otf", ".pdf"}
ACTION_RE = re.compile(r'data-lpm-action=["\'](?P<kind>checkout|booking|form|external-checkout)(?::(?P<key>[a-z0-9-]+))?["\']', re.I)

def validate_archive(upload):
    if upload.size > MAX_ARCHIVE_BYTES:
        raise ValidationError("Archive exceeds 25 MB.")
    try:
        archive = zipfile.ZipFile(upload)
    except zipfile.BadZipFile as exc:
        raise ValidationError("The uploaded file is not a valid ZIP archive.") from exc
    members = [m for m in archive.infolist() if not m.is_dir()]
    if len(members) > MAX_FILES:
        raise ValidationError("Archive contains too many files.")
    if sum(member.file_size for member in members) > MAX_EXPANDED_BYTES:
        raise ValidationError("Archive expands beyond 100 MB.")
    if len({member.filename.replace("\\", "/").lower() for member in members}) != len(members):
        raise ValidationError("Archive contains duplicate file paths.")
    indexes = []
    for member in members:
        if member.flag_bits & 0x1:
            raise ValidationError("Encrypted archive entries are not accepted.")
        path = PurePosixPath(member.filename.replace("\\", "/"))
        if path.is_absolute() or ".." in path.parts or not path.parts:
            raise ValidationError(f"Unsafe archive path: {member.filename}")
        if member.external_attr >> 16 & 0o170000 == 0o120000:
            raise ValidationError("Symbolic links are not accepted.")
        suffix = path.suffix.lower()
        if suffix in DENIED_SUFFIXES or suffix not in ALLOWED_SUFFIXES:
            raise ValidationError(f"Unsupported file type: {suffix or member.filename}")
        if member.file_size > MAX_FILE_BYTES:
            raise ValidationError(f"File is too large: {member.filename}")
        if path.name.lower() == "index.html":
            indexes.append(path)
    if len(indexes) != 1 or len(indexes[0].parts) != 1:
        raise ValidationError("The ZIP must contain exactly one index.html at its root.")
    index_text = archive.read("index.html").decode("utf-8", errors="strict")
    lowered = index_text.lower()
    if re.search(r"(?:src|href)\s*=\s*[\"'](?:/|file:|[a-z]:)", lowered):
        raise ValidationError("Use relative asset paths; absolute local paths are not accepted.")
    actions = []
    for match in ACTION_RE.finditer(index_text):
        item = {"type": match.group("kind").lower(), "key": (match.group("key") or match.group("kind")).lower()}
        if item not in actions:
            actions.append(item)
    return archive, members, actions

def save_archive_version(page, upload, user):
    archive, members, actions = validate_archive(upload)
    with transaction.atomic():
        number = (page.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
        # The database version number is human-readable; the random storage suffix
        # prevents collisions after test runs or a database-only restore.
        rel = Path(str(page.pk)) / f"{number}-{secrets.token_hex(6)}"
        destination = settings.PUBLISHED_ROOT / rel
        destination.mkdir(parents=True, exist_ok=False)
        try:
            for member in members:
                target = destination / PurePosixPath(member.filename)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(member) as src, target.open("wb") as dst:
                    shutil.copyfileobj(src, dst)
                if target.suffix.lower() in {".png", ".jpg", ".jpeg", ".gif", ".webp"}:
                    try:
                        with Image.open(target) as image:
                            image.verify()
                    except (UnidentifiedImageError, OSError) as exc:
                        raise ValidationError(f"Invalid image: {member.filename}") from exc
            version = PageVersion.objects.create(page=page, number=number, artifact_path=rel.as_posix(), detected_actions=actions, created_by=user)
            page.current_version = version
            page.source_type = LandingPage.SOURCE_UPLOAD
            page.save(update_fields=["current_version", "source_type", "updated_at"])
            return version
        except Exception:
            shutil.rmtree(destination, ignore_errors=True)
            raise

def save_builder_version(page, blocks, user):
    with transaction.atomic():
        number = (page.versions.order_by("-number").values_list("number", flat=True).first() or 0) + 1
        version = PageVersion.objects.create(page=page, number=number, blocks=blocks, created_by=user)
        page.current_version = version
        page.source_type = LandingPage.SOURCE_BUILDER
        page.save(update_fields=["current_version", "source_type", "updated_at"])
        return version

def render_builder(blocks, page):
    output = []
    for block in blocks:
        kind = block.get("type")
        title = html.escape(str(block.get("title", "")))
        body = html.escape(str(block.get("body", ""))).replace("\n", "<br>")
        label = html.escape(str(block.get("button", "Continue")))
        action = html.escape(str(block.get("action", "")))
        action_attr = f' data-lpm-action="{action}" href="#"' if action else ""
        if kind == "hero":
            output.append(f'<section class="hero"><span class="eyebrow">{html.escape(str(block.get("eyebrow", "")))}</span><h1>{title}</h1><p>{body}</p>{f"<a class=\"button\"{action_attr}>{label}</a>" if action else ""}</section>')
        elif kind in {"content", "benefits", "testimonials", "faq"}:
            output.append(f'<section class="section"><h2>{title}</h2><div class="copy">{body}</div></section>')
        elif kind == "pricing":
            price = html.escape(str(block.get("price", "")))
            output.append(f'<section class="section pricing"><h2>{title}</h2><strong class="price">{price}</strong><div class="copy">{body}</div><a class="button"{action_attr}>{label}</a></section>')
        elif kind == "cta":
            output.append(f'<section class="section cta"><h2>{title}</h2><div class="copy">{body}</div><a class="button"{action_attr}>{label}</a></section>')
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>{html.escape(page.name)}</title><style>
:root{{--ink:#101828;--muted:#667085;--brand:#5b3df5;--accent:#ffcf5c;--paper:#f5f7fb}}*{{box-sizing:border-box}}body{{margin:0;font:17px/1.65 system-ui,sans-serif;color:var(--ink);background:var(--paper)}}section{{max-width:1080px;margin:auto;padding:72px 28px}}.hero{{min-height:72vh;display:grid;align-content:center;background:radial-gradient(circle at 85% 20%,#dcd5ff,transparent 34%)}}h1{{font-size:clamp(2.7rem,7vw,6.5rem);line-height:.94;max-width:850px;margin:.3em 0}}h2{{font-size:clamp(2rem,4vw,3.5rem);line-height:1.05}}p,.copy{{max-width:720px;color:var(--muted)}}.eyebrow{{font-weight:800;text-transform:uppercase;letter-spacing:.16em;color:var(--brand)}}.section{{margin-top:24px;background:white;border-radius:28px;box-shadow:0 20px 60px #14213d12}}.pricing,.cta{{border:2px solid var(--ink)}}.price{{font-size:3rem;display:block;margin:18px 0}}.button{{display:inline-block;margin-top:24px;padding:15px 24px;border-radius:999px;background:var(--ink);color:white;text-decoration:none;font-weight:800}}.button:hover{{background:var(--brand)}}@media(max-width:600px){{section{{padding:48px 20px}}.hero{{min-height:60vh}}}}
</style></head><body>{''.join(output)}</body></html>'''

def serve_file_path(version, relative="index.html"):
    root = (settings.PUBLISHED_ROOT / version.artifact_path).resolve()
    target = (root / relative).resolve()
    if root not in target.parents and target != root:
        raise FileNotFoundError
    return target

