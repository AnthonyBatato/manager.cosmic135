import json
import re

from .models import AdTrackingSettings


TRACKING_RUNTIME = r"""
<script id="cosmic-ads-runtime">
(function () {
  "use strict";
  const config = __CONFIG__;
  const consentKey = "cosmic_ads_consent_" + config.pageId;
  const consentCookie = consentKey + "=";
  let started = false;

  function addScript(src) {
    const script = document.createElement("script");
    script.async = true;
    script.src = src;
    document.head.appendChild(script);
  }

  function eventId(prefix) {
    if (window.crypto && crypto.randomUUID) return prefix + "_" + crypto.randomUUID();
    return prefix + "_" + Date.now() + "_" + Math.random().toString(36).slice(2);
  }

  function rememberConsent(value) {
    try { localStorage.setItem(consentKey, value); } catch (error) {}
    document.cookie = consentCookie + value + "; Path=/; Max-Age=31536000; SameSite=Lax";
  }

  function initMeta() {
    if (!config.metaPixelId) return;
    if (!window.fbq) {
      const fbq = window.fbq = function () { fbq.callMethod ? fbq.callMethod.apply(fbq, arguments) : fbq.queue.push(arguments); };
      if (!window._fbq) window._fbq = fbq;
      fbq.push = fbq;
      fbq.loaded = true;
      fbq.version = "2.0";
      fbq.queue = [];
      addScript("https://connect.facebook.net/en_US/fbevents.js");
    }
    window.fbq("init", config.metaPixelId);
    window.fbq("track", "PageView");
  }

  function initGoogle() {
    if (!config.googleAdsId) return;
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    addScript("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(config.googleAdsId));
    window.gtag("js", new Date());
    window.gtag("config", config.googleAdsId);
  }

  function initOpenAI() {
    if (!config.openaiPixelId) return;
    if (!window.oaiq) {
      const queue = function () { queue.q.push(arguments); };
      queue.q = [];
      window.oaiq = queue;
      addScript("https://bzrcdn.openai.com/sdk/oaiq.min.js");
    }
    window.oaiq("consent", true);
    window.oaiq("init", {pixelId: config.openaiPixelId});
    window.oaiq("measure", "page_viewed", {type: "contents"}, {event_id: eventId("page")});
  }

  function trackCheckout() {
    const id = eventId("checkout");
    if (window.fbq && config.metaPixelId) window.fbq("track", "InitiateCheckout", {}, {eventID: id});
    if (window.gtag && config.googleAdsId) window.gtag("event", "begin_checkout");
    if (window.oaiq && config.openaiPixelId) {
      window.oaiq("measure", "checkout_started", {type: "contents"}, {event_id: id});
    }
  }

  function start() {
    if (started) return;
    started = true;
    rememberConsent("granted");
    initMeta();
    initGoogle();
    initOpenAI();
    document.addEventListener("click", function (event) {
      const action = event.target.closest("[data-lpm-action]");
      if (!action) return;
      const actionType = (action.getAttribute("data-lpm-action") || "").split(":", 1)[0];
      if (actionType === "checkout" || actionType === "external-checkout") trackCheckout();
      if (config.openaiPixelId && config.oppref && action.href) {
        try {
          const target = new URL(action.href, window.location.href);
          if (target.origin === window.location.origin) target.searchParams.set("oppref", config.oppref);
          action.href = target.toString();
        } catch (error) {}
      }
    }, true);
  }

  function showConsent() {
    const chinese = (navigator.language || "").toLowerCase().startsWith("zh");
    const bar = document.createElement("div");
    bar.id = "cosmic-ads-consent";
    bar.setAttribute("role", "dialog");
    bar.setAttribute("aria-label", "Advertising measurement consent");
    bar.innerHTML = "<p>" + (chinese ? "我们使用广告衡量工具来了解页面和购买成效。" : "We use advertising measurement tools to understand page and purchase performance.") + "</p><div><button type='button' data-consent='declined'>" + (chinese ? "拒绝" : "Decline") + "</button><button type='button' data-consent='granted'>" + (chinese ? "允许" : "Allow") + "</button></div>";
    const style = document.createElement("style");
    style.textContent = "#cosmic-ads-consent{position:fixed;z-index:2147483647;left:18px;right:18px;bottom:18px;max-width:760px;margin:auto;padding:16px 18px;border-radius:14px;background:#111827;color:#fff;box-shadow:0 16px 50px #0005;font:14px/1.45 system-ui,sans-serif;display:flex;align-items:center;justify-content:space-between;gap:18px}#cosmic-ads-consent p{margin:0;color:#fff}#cosmic-ads-consent div{display:flex;gap:8px;flex:none}#cosmic-ads-consent button{border:1px solid #ffffff55;border-radius:9px;padding:9px 14px;background:#fff;color:#111827;font:inherit;font-weight:700;cursor:pointer}#cosmic-ads-consent button:first-child{background:transparent;color:#fff}@media(max-width:600px){#cosmic-ads-consent{align-items:stretch;flex-direction:column}#cosmic-ads-consent div{justify-content:flex-end}}";
    document.head.appendChild(style);
    document.body.appendChild(bar);
    bar.addEventListener("click", function (event) {
      const choice = event.target.getAttribute("data-consent");
      if (!choice) return;
      rememberConsent(choice);
      bar.remove();
      style.remove();
      if (choice === "granted") start();
    });
  }

  if (!config.requireConsent) start();
  else {
    let choice = "";
    try { choice = localStorage.getItem(consentKey) || ""; } catch (error) {}
    if (choice === "granted") start();
    else if (choice !== "declined") {
      if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", showConsent);
      else showConsent();
    }
  }
})();
</script>
"""


def _script_safe_json(value):
    return (json.dumps(value, separators=(",", ":"))
            .replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
            .replace("\u2028", "\\u2028").replace("\u2029", "\\u2029"))


def tracking_markup(page, request):
    tracking = AdTrackingSettings.objects.filter(page=page).first()
    if not tracking:
        return ""
    config = {
        "pageId": page.pk,
        "requireConsent": tracking.require_consent,
        "metaPixelId": tracking.meta_pixel_id if tracking.meta_enabled else "",
        "googleAdsId": tracking.google_ads_id if tracking.google_ads_enabled else "",
        "googleConversionLabel": tracking.google_ads_conversion_label if tracking.google_ads_enabled else "",
        "openaiPixelId": tracking.openai_pixel_id if tracking.openai_enabled else "",
        "oppref": request.GET.get("oppref", "")[:2048] if tracking.openai_enabled else "",
    }
    if not any(config[key] for key in ("metaPixelId", "googleAdsId", "openaiPixelId")):
        return ""
    return TRACKING_RUNTIME.replace("__CONFIG__", _script_safe_json(config))


def inject_tracking(source, page, request):
    markup = tracking_markup(page, request)
    if not markup:
        return source
    if re.search(r"</head\s*>", source, flags=re.I):
        return re.sub(r"</head\s*>", lambda _: markup + "</head>", source, count=1, flags=re.I)
    if re.search(r"</body\s*>", source, flags=re.I):
        return re.sub(r"</body\s*>", lambda _: markup + "</body>", source, count=1, flags=re.I)
    return source + markup


def purchase_tracking_markup(payment, request):
    tracking = AdTrackingSettings.objects.filter(page=payment.attempt.page).first()
    if not tracking:
        return ""
    if tracking.require_consent and request.COOKIES.get(f"cosmic_ads_consent_{payment.attempt.page_id}") != "granted":
        return ""
    from commerce.tracking import payment_event_id
    config = {
        "metaPixelId": tracking.meta_pixel_id if tracking.meta_enabled else "",
        "googleAdsId": tracking.google_ads_id if tracking.google_ads_enabled else "",
        "googleConversionLabel": tracking.google_ads_conversion_label if tracking.google_ads_enabled else "",
        "openaiPixelId": tracking.openai_pixel_id if tracking.openai_enabled else "",
        "eventId": payment_event_id(payment),
        "amountMinor": payment.amount_total,
        "value": payment.amount_total / 100,
        "currency": payment.currency.upper(),
        "transactionId": payment.stripe_payment_intent_id or str(payment.pk),
    }
    if not any(config[key] for key in ("metaPixelId", "googleAdsId", "openaiPixelId")):
        return ""
    return r"""
<script id="cosmic-purchase-tracking">
(function () {
  "use strict";
  const c = __CONFIG__;
  function addScript(src) { const script = document.createElement("script"); script.async = true; script.src = src; document.head.appendChild(script); }
  if (c.metaPixelId) {
    if (!window.fbq) { const fbq = window.fbq = function () { fbq.callMethod ? fbq.callMethod.apply(fbq, arguments) : fbq.queue.push(arguments); }; window._fbq = fbq; fbq.push = fbq; fbq.loaded = true; fbq.version = "2.0"; fbq.queue = []; addScript("https://connect.facebook.net/en_US/fbevents.js"); }
    window.fbq("init", c.metaPixelId);
    window.fbq("track", "Purchase", {value: c.value, currency: c.currency}, {eventID: c.eventId});
  }
  if (c.googleAdsId && c.googleConversionLabel) {
    window.dataLayer = window.dataLayer || [];
    window.gtag = window.gtag || function () { window.dataLayer.push(arguments); };
    addScript("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(c.googleAdsId));
    window.gtag("js", new Date());
    window.gtag("config", c.googleAdsId);
    window.gtag("event", "conversion", {send_to: c.googleAdsId + "/" + c.googleConversionLabel, value: c.value, currency: c.currency, transaction_id: c.transactionId});
  }
  if (c.openaiPixelId) {
    if (!window.oaiq) { const queue = function () { queue.q.push(arguments); }; queue.q = []; window.oaiq = queue; addScript("https://bzrcdn.openai.com/sdk/oaiq.min.js"); }
    window.oaiq("consent", true);
    window.oaiq("init", {pixelId: c.openaiPixelId});
    window.oaiq("measure", "order_created", {type: "contents", amount: c.amountMinor, currency: c.currency}, {event_id: c.eventId});
  }
})();
</script>
""".replace("__CONFIG__", _script_safe_json(config))
