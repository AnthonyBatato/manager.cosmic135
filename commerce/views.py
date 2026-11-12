import stripe
from django.conf import settings
from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pages.models import ActionMapping
from pages.tracking import purchase_tracking_markup
from users.auth import owner_required
from .forms import OfferForm
from .models import CheckoutAttempt, Journey, Offer, StripeEvent
from .tasks import process_stripe_event


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
    attempt = CheckoutAttempt.objects.filter(stripe_session_id=session_id).select_related("payment__journey").first()
    journey = getattr(getattr(attempt, "payment", None), "journey", None) if attempt else None
    payment = getattr(attempt, "payment", None) if attempt else None
    return render(request, "commerce/success.html", {
        "attempt": attempt, "journey": journey,
        "status_url": f"{reverse('checkout_status')}?session_id={session_id}",
        "purchase_tracking_markup": purchase_tracking_markup(payment, request) if payment else "",
    })


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

