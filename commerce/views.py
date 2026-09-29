import stripe
from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from pages.models import ActionMapping
from .models import CheckoutAttempt, Journey, Offer, StripeEvent
from .tasks import process_stripe_event

def checkout_start(request, action_id):
    action = get_object_or_404(ActionMapping.objects.select_related("page"), pk=action_id, action_type=ActionMapping.ACTION_CHECKOUT, enabled=True)
    offer = get_object_or_404(Offer, pk=action.target_id, active=True)
    if not settings.STRIPE_SECRET_KEY:
        return render(request, "commerce/integration_required.html", {"service": "Stripe", "detail": "Add STRIPE_SECRET_KEY and STRIPE_WEBHOOK_SECRET to enable checkout."}, status=503)
    attempt = CheckoutAttempt.objects.create(page=action.page, page_version=action.page.published_version, action=action, offer=offer)
    stripe.api_key = settings.STRIPE_SECRET_KEY
    root = request.build_absolute_uri("/").rstrip("/")
    session = stripe.checkout.Session.create(
        mode="payment",
        line_items=[{"price": offer.stripe_price_id, "quantity": 1}],
        customer_creation="always",
        client_reference_id=str(attempt.pk),
        metadata={
            "attempt_id": str(attempt.pk),
            "campaign": action.page.slug,
            "page_id": str(action.page_id),
            "page_version_id": str(attempt.page_version_id or ""),
            "offer_id": str(offer.pk),
        },
        success_url=f"{root}{reverse('checkout_success')}?session_id={{CHECKOUT_SESSION_ID}}",
        cancel_url=f"{root}{reverse('local_public_page', kwargs={'slug': action.page.slug})}?checkout=cancelled",
    )
    attempt.stripe_session_id = session.id
    attempt.save(update_fields=["stripe_session_id", "updated_at"])
    return redirect(session.url)

def checkout_success(request):
    session_id = request.GET.get("session_id", "")
    attempt = CheckoutAttempt.objects.filter(stripe_session_id=session_id).select_related("payment__journey").first()
    journey = getattr(getattr(attempt, "payment", None), "journey", None) if attempt else None
    return render(request, "commerce/success.html", {"attempt": attempt, "journey": journey})

def continue_journey(request, token):
    journey = get_object_or_404(Journey.objects.select_related("customer"), token=token)
    if journey.status == Journey.STATUS_COMPLETED:
        return render(request, "commerce/complete.html", {"journey": journey})
    if journey.destination_type == "booking" and journey.destination_id:
        return redirect("booking_with_journey", booking_type_id=journey.destination_id, journey_token=journey.token)
    if journey.destination_url:
        joiner = "&" if "?" in journey.destination_url else "?"
        return redirect(f"{journey.destination_url}{joiner}journey_token={journey.token}")
    return render(request, "commerce/integration_required.html", {"service": "Next step", "detail": "This offer does not yet have a registration form or booking type assigned."}, status=503)

@csrf_exempt
@require_POST
def stripe_webhook(request):
    try:
        event = stripe.Webhook.construct_event(request.body, request.META.get("HTTP_STRIPE_SIGNATURE", ""), settings.STRIPE_WEBHOOK_SECRET)
    except (ValueError, stripe.error.SignatureVerificationError):
        return HttpResponse(status=400)
    record, created = StripeEvent.objects.get_or_create(event_id=event["id"], defaults={"event_type": event["type"], "payload": dict(event)})
    if created:
        process_stripe_event.delay(record.pk)
    return JsonResponse({"received": True, "duplicate": not created})

