import html
import mimetypes
import re

import stripe
from django.conf import settings
from django.contrib import messages
from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pages.models import ActionMapping
from pages.services import render_builder, serve_file_path
from pages.tracking import purchase_tracking_markup
from users.auth import owner_required
from .forms import OfferForm
from .models import CheckoutAttempt, Journey, Offer, StripeEvent
from .tasks import process_stripe_event


def _registration_actions(journey):
    seats = list(journey.registration_seats.filter(link_status="ready").order_by("seat_number"))
    if seats:
        links = []
        multiple = len(seats) > 1
        for seat in seats:
            label = (
                f"參加者 {seat.seat_number} 登記 · Participant {seat.seat_number}"
                if multiple else "填寫入場券資料 · Complete registration"
            )
            links.append(
                f'<a class="btn btn-primary lpm-registration-action" href="{html.escape(seat.registration_url, quote=True)}">'
                f"{html.escape(label)}</a>"
            )
        prompt = "請完成每位參加者的入場券登記。<br>Complete the entry-ticket registration for each participant."
        return f'<p class="next lpm-registration-note" style="margin:0 0 8px">{prompt}</p>' + "".join(links)
    continue_url = reverse("continue_journey", kwargs={"token": journey.token})
    if journey.destination_url or journey.destination_id or journey.registration_link_status == "ready":
        return (
            '<p class="next lpm-registration-note" style="margin:0 0 8px">'
            "請完成您的入場券登記。<br>Complete your entry-ticket registration.</p>"
            f'<a class="btn btn-primary lpm-registration-action" href="{html.escape(continue_url, quote=True)}">'
            "填寫入場券資料 · Complete registration</a>"
        )
    return (
        '<p class="next lpm-registration-note" style="margin:0 0 8px">'
        "正在準備您的專屬登記連結。<br>We are preparing your personal registration link.</p>"
        f'<a class="btn btn-primary lpm-registration-action" href="{html.escape(continue_url, quote=True)}">'
        "再次檢查 · Check again</a>"
    )


def _custom_success_response(request, attempt, journey, payment, page):
    version = page.published_version or page.current_version
    if not version:
        return None
    if version.blocks:
        source = render_builder(version.blocks, page)
    else:
        try:
            path = serve_file_path(version)
        except FileNotFoundError:
            return None
        if not path.is_file():
            return None
        source = path.read_text(encoding="utf-8")
        asset_url = reverse(
            "checkout_success_asset",
            kwargs={"session_id": attempt.stripe_session_id, "path": "__asset__"},
        ).replace("__asset__", "")
        source = re.sub(
            r"<head(\s[^>]*)?>",
            lambda match: match.group(0) + f'<base href="{asset_url}">',
            source,
            count=1,
            flags=re.I,
        )
    actions = _registration_actions(journey)
    slot = re.compile(
        r'(<(?:div|section|nav)\b[^>]*data-lpm-slot=["\']registration-actions["\'][^>]*>)',
        re.I,
    )
    if slot.search(source):
        source = slot.sub(lambda match: match.group(1) + actions, source, count=1)
    else:
        legacy_actions = re.compile(r'(<div\b[^>]*class=["\'][^"\']*\bactions\b[^"\']*["\'][^>]*>)', re.I)
        if legacy_actions.search(source):
            source = legacy_actions.sub(lambda match: match.group(1) + actions, source, count=1)
        else:
            source = re.sub(r"</main>", actions + "</main>", source, count=1, flags=re.I)
    tracking = purchase_tracking_markup(payment, request)
    if tracking:
        source = re.sub(r"</head>", tracking + "</head>", source, count=1, flags=re.I)
    return HttpResponse(
        source,
        content_type="text/html; charset=utf-8",
        headers={"Content-Security-Policy": "frame-ancestors 'self' https://manager.cosmic135.com"},
    )


@owner_required
def payment_settings(request):
    return render(request, "commerce/payment_settings.html", {
        "offers": Offer.objects.order_by("name"),
        "stripe_mode": settings.STRIPE_MODE,
        "secret_configured": bool(settings.STRIPE_SECRET_KEY),
        "webhook_configured": bool(settings.STRIPE_WEBHOOK_SECRET),
        "webhook_url": request.build_absolute_uri(reverse("stripe_webhook")),
    })


@owner_required
def offer_create(request):
    form = OfferForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        offer = form.save()
        messages.success(request, "Stripe offer created.")
        return redirect("offer_edit", pk=offer.pk)
    return render(request, "commerce/offer_form.html", {"form": form, "offer": None})


@owner_required
def offer_edit(request, pk):
    offer = get_object_or_404(Offer, pk=pk)
    form = OfferForm(request.POST or None, instance=offer)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Stripe offer saved.")
        return redirect("offer_edit", pk=offer.pk)
    return render(request, "commerce/offer_form.html", {"form": form, "offer": offer})

def checkout_start(request, action_id):
    action = get_object_or_404(ActionMapping.objects.select_related("page"), pk=action_id, action_type=ActionMapping.ACTION_CHECKOUT, enabled=True)
    offer = get_object_or_404(Offer, pk=action.target_id, active=True)
    if not settings.STRIPE_SECRET_KEY:
        return render(request, "commerce/integration_required.html", {"service": "Stripe", "detail": f"Add the Stripe {settings.STRIPE_MODE} secret key and webhook secret to enable checkout."}, status=503)
    price_id = offer.stripe_price_for_mode(settings.STRIPE_MODE)
    if not price_id:
        return render(request, "commerce/integration_required.html", {"service": "Stripe", "detail": f"This offer has no Stripe {settings.STRIPE_MODE} Price ID."}, status=503)
    attribution_matches_page = request.session.get("openai_attribution_page_id") == action.page_id
    attempt = CheckoutAttempt.objects.create(
        page=action.page, page_version=action.page.published_version, action=action, offer=offer,
        stripe_mode=settings.STRIPE_MODE,
        openai_oppref=request.session.get("openai_oppref", "")[:2048] if attribution_matches_page else "",
        openai_obref=request.session.get("openai_obref", "")[:2048] if attribution_matches_page else "",
    )
    stripe.api_key = settings.STRIPE_SECRET_KEY
    root = settings.STRIPE_PUBLIC_BASE_URL
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": price_id, "quantity": 1}],
        customer_creation="always",
        name_collection={"individual": {"enabled": True, "optional": False}},
        phone_number_collection={"enabled": True},
        locale="auto",
        client_reference_id=str(attempt.pk),
        metadata={
            "attempt_id": str(attempt.pk),
            "campaign": action.page.slug,
            "page_id": str(action.page_id),
            "page_version_id": str(attempt.page_version_id or ""),
            "offer_id": str(offer.pk),
            "stripe_mode": settings.STRIPE_MODE,
        },
        payment_intent_data={"metadata": {"attempt_id": str(attempt.pk), "offer_id": str(offer.pk)}},
        success_url=f"{root}{reverse('checkout_success')}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"https://{action.page.slug}.{settings.PUBLIC_ROOT_HOST}/?checkout=cancelled",
    )
    attempt.stripe_session_id = session.id
    attempt.save(update_fields=["stripe_session_id", "updated_at"])
    return redirect(session.url)

def checkout_success(request):
    session_id = request.GET.get("session_id", "")
    attempt = CheckoutAttempt.objects.filter(stripe_session_id=session_id).select_related(
        "payment__journey", "offer__thank_you_page__published_version", "offer__thank_you_page__current_version",
    ).first()
    journey = getattr(getattr(attempt, "payment", None), "journey", None) if attempt else None
    payment = getattr(attempt, "payment", None) if attempt else None
    thank_you_page = attempt.offer.thank_you_page if attempt else None
    if journey and payment and thank_you_page:
        custom = _custom_success_response(request, attempt, journey, payment, thank_you_page)
        if custom is not None:
            return custom
    return render(request, "commerce/success.html", {
        "attempt": attempt, "journey": journey,
        "status_url": f"{reverse('checkout_status')}?session_id={session_id}",
        "purchase_tracking_markup": purchase_tracking_markup(payment, request) if payment else "",
    })


def checkout_success_asset(request, session_id, path):
    attempt = get_object_or_404(
        CheckoutAttempt.objects.select_related(
            "offer__thank_you_page__published_version", "offer__thank_you_page__current_version",
        ),
        stripe_session_id=session_id,
        status=CheckoutAttempt.STATUS_PAID,
    )
    page = attempt.offer.thank_you_page
    if not page:
        raise Http404
    version = page.published_version or page.current_version
    if not version or not version.artifact_path:
        raise Http404
    try:
        target = serve_file_path(version, path)
    except FileNotFoundError:
        raise Http404
    if not target.is_file():
        raise Http404
    return FileResponse(target.open("rb"), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")


def checkout_status(request):
    session_id = request.GET.get("session_id", "")
    if not session_id:
        return JsonResponse({"status": "unknown"}, status=400)
    attempt = CheckoutAttempt.objects.filter(stripe_session_id=session_id).select_related("payment__journey").first()
    if not attempt:
        return JsonResponse({"status": "unknown"}, status=404)
    payment = getattr(attempt, "payment", None)
    journey = getattr(payment, "journey", None) if payment else None
    result = {"status": attempt.status}
    if journey:
        result["continue_url"] = reverse("continue_journey", kwargs={"token": journey.token})
        result["has_next_step"] = bool(
            journey.destination_id or journey.destination_url or journey.cosmic_tools_course_id
        )
    return JsonResponse(result)

def continue_journey(request, token):
    journey = get_object_or_404(Journey.objects.select_related("customer"), token=token)
    if journey.status == Journey.STATUS_COMPLETED:
        return render(request, "commerce/complete.html", {"journey": journey})
    if journey.destination_type == "booking" and journey.destination_id:
        return redirect("booking_with_journey", booking_type_id=journey.destination_id, journey_token=journey.token)
    registration_seats = list(journey.registration_seats.filter(link_status="ready").order_by("seat_number"))
    if len(registration_seats) > 1:
        return render(request, "commerce/registration_links.html", {
            "journey": journey,
            "registration_seats": registration_seats,
        })
    if registration_seats:
        return redirect(registration_seats[0].registration_url)
    if journey.destination_url:
        joiner = "&" if "?" in journey.destination_url else "?"
        return redirect(f"{journey.destination_url}{joiner}journey_token={journey.token}")
    if journey.cosmic_tools_course_id and journey.registration_link_status == "pending":
        return render(request, "commerce/integration_required.html", {
            "service": "Registration link",
            "detail": "Your payment is confirmed. We are preparing your personal registration link and will email it shortly.",
        }, status=202)
    return render(request, "commerce/integration_required.html", {"service": "Next step", "detail": "This offer does not yet have a registration form or booking type assigned."}, status=503)

@csrf_exempt
@require_POST
def stripe_webhook(request):
    event = None
    signature = request.META.get("HTTP_STRIPE_SIGNATURE", "")
    for secret in settings.STRIPE_WEBHOOK_SECRETS:
        try:
            event = stripe.Webhook.construct_event(request.body, signature, secret)
            break
        except (ValueError, stripe.SignatureVerificationError):
            continue
    if event is None:
        return HttpResponse(status=400)
    record, created = StripeEvent.objects.get_or_create(event_id=event["id"], defaults={
        "event_type": event["type"], "livemode": bool(event.get("livemode")), "payload": dict(event),
    })
    if created:
        process_stripe_event.delay(record.pk)
    return JsonResponse({"received": True, "duplicate": not created})

