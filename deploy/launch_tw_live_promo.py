from datetime import datetime
from zoneinfo import ZoneInfo

import stripe
from django.conf import settings
from django.core.files import File
from django.urls import reverse

from commerce.models import Offer
from pages.models import ActionMapping, Domain, DomainRoute, LandingPage
from pages.services import save_uploaded_version


PROMO_KEY = "tw-live-bogo-2026"
PAGE_ZIP = "/tmp/workshop-tw-live-upload.zip"
STARTS_AT = datetime(2026, 11, 26, 20, 30, tzinfo=ZoneInfo("Asia/Taipei"))


def find_product(api_key):
    for product in stripe.Product.list(limit=100, api_key=api_key).auto_paging_iter():
        if (product.metadata or {}).get("cosmic_manager_key") == PROMO_KEY:
            return product
    return None


def find_payment_link(api_key):
    for link in stripe.PaymentLink.list(limit=100, api_key=api_key).auto_paging_iter():
        if (link.metadata or {}).get("cosmic_manager_key") == PROMO_KEY:
            return link
    return None


def ensure_stripe_objects(mode, api_key, source_price_id, offer, page, action):
    source_price = stripe.Price.retrieve(source_price_id, api_key=api_key)
    product = find_product(api_key)
    if product is None:
        product = stripe.Product.create(
            api_key=api_key,
            name="Workshop (TW) 2026 - Livestream Buy 1 Free 1",
            description="Two participant seats for the 19 December 2026 Taipei workshop. First five completed payments only.",
            metadata={"cosmic_manager_key": PROMO_KEY, "seat_count": "2"},
        )
    price = None
    for candidate in stripe.Price.list(product=product.id, active=True, limit=100, api_key=api_key).auto_paging_iter():
        if candidate.currency == source_price.currency and candidate.unit_amount == source_price.unit_amount:
            price = candidate
            break
    if price is None:
        price = stripe.Price.create(
            api_key=api_key,
            product=product.id,
            currency=source_price.currency,
            unit_amount=source_price.unit_amount,
            metadata={"cosmic_manager_key": PROMO_KEY, "package_seats": "2"},
        )
    link = find_payment_link(api_key)
    if link is None:
        success_url = (
            f"{settings.STRIPE_PUBLIC_BASE_URL}{reverse('checkout_success')}"
            "?session_id={CHECKOUT_SESSION_ID}"
        )
        link = stripe.PaymentLink.create(
            api_key=api_key,
            line_items=[{"price": price.id, "quantity": 1}],
            restrictions={"completed_sessions": {"limit": 5}},
            customer_creation="always",
            name_collection={"individual": {"enabled": True, "optional": False}},
            phone_number_collection={"enabled": True},
            consent_collection={"terms_of_service": "required"},
            after_completion={"type": "redirect", "redirect": {"url": success_url}},
            inactive_message="首5組直播買一送一名額已售罄。The first five livestream promotion packages are sold out.",
            metadata={
                "cosmic_manager_key": PROMO_KEY,
                "offer_id": str(offer.pk),
                "page_id": str(page.pk),
                "page_version_id": str(page.current_version_id or ""),
                "action_id": str(action.pk),
                "stripe_mode": mode,
            },
            payment_intent_data={"metadata": {"offer_id": str(offer.pk), "promo": PROMO_KEY}},
        )
    return price, link


source_page = LandingPage.objects.get(pk=2)
single_offer = Offer.objects.get(pk=2)
if single_offer.registration_quantity != 1:
    raise RuntimeError("Offer 2 is no longer the expected TW single-seat offer.")

page, _ = LandingPage.objects.get_or_create(
    slug="workshop-tw-live",
    defaults={
        "name": "Workshop (TW) Livestream Promo",
        "source_type": LandingPage.SOURCE_UPLOAD,
        "created_by": source_page.created_by,
    },
)
if page.current_version_id is None:
    with open(PAGE_ZIP, "rb") as source:
        save_uploaded_version(page, File(source, name="workshop-tw-live-upload.zip"), source_page.created_by)
    page.refresh_from_db()

offer, _ = Offer.objects.get_or_create(name="Workshop (TW) Livestream Buy 1 Free 1")
for field in (
    "currency", "thank_you_page", "destination_type", "destination_id", "destination_url",
    "cosmic_tools_course_id", "post_payment_email", "email_subject_zh", "email_subject_en",
    "email_body_zh", "email_body_en",
):
    setattr(offer, field, getattr(single_offer, field))
offer.registration_quantity = 2
offer.sales_start_at = STARTS_AT
offer.sales_end_at = None
offer.max_completed_orders = 5
offer.active = True
offer.save()

promo_action, _ = ActionMapping.objects.update_or_create(
    page=page,
    key="tw-live-bogo",
    defaults={
        "label": "Livestream Buy 1 Free 1",
        "action_type": ActionMapping.ACTION_CHECKOUT,
        "target_id": offer.pk,
        "target_url": "",
        "enabled": True,
    },
)
for key in ("tw-single", "tw-duo"):
    source_action = ActionMapping.objects.get(page=source_page, key=key)
    ActionMapping.objects.update_or_create(
        page=page,
        key=key,
        defaults={
            "label": source_action.label,
            "action_type": source_action.action_type,
            "target_id": source_action.target_id,
            "target_url": source_action.target_url,
            "enabled": source_action.enabled,
        },
    )

modes = {
    "test": (settings.STRIPE_TEST_SECRET_KEY, single_offer.stripe_test_price_id),
    "live": (settings.STRIPE_LIVE_SECRET_KEY, single_offer.stripe_live_price_id),
}
for mode, (api_key, source_price_id) in modes.items():
    if not api_key or not source_price_id:
        raise RuntimeError(f"Stripe {mode} key or source Price ID is missing.")
    price, link = ensure_stripe_objects(mode, api_key, source_price_id, offer, page, promo_action)
    setattr(offer, f"stripe_{mode}_price_id", price.id)
    setattr(offer, f"stripe_{mode}_payment_link_id", link.id)
    setattr(offer, f"stripe_{mode}_payment_link_url", link.url)
offer.save()

page.published_version = page.current_version
page.is_published = True
page.save(update_fields=["published_version", "is_published", "updated_at"])

domain = Domain.objects.get(hostname="workshop.cosmic135.com", status=Domain.STATUS_VERIFIED)
DomainRoute.objects.update_or_create(domain=domain, path="tw-live", defaults={"page": page})

print(f"Page {page.pk} published at /tw-live/ with offer {offer.pk}.")
print(f"Test Payment Link: {offer.stripe_test_payment_link_id}")
print(f"Live Payment Link: {offer.stripe_live_payment_link_id}")
