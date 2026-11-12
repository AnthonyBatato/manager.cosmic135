from django.db import migrations


SUBJECT_ZH = "付款已確認｜台北特別場入場券登記"
SUBJECT_EN = "Payment confirmed | Taipei workshop entry ticket registration"

BODY_ZH = """您好！🥰

🎉 感謝您報名參加 TatKee 大師兄《數字解碼 × 數靈啟示牌｜台北特別場》！

我們已成功收到並確認您的付款！❤️

📍 活動資訊

📅 日期：2026年12月19日（星期六）
⏰ 時間：上午10:00 – 下午4:00
🏢 地點：Red Space 多元商務空間・台北

🎟️ 重要提醒｜請完成入場券登記

為了確保您能順利入場，請點擊以下連結，填寫您的個人資料以獲取活動入場券。

🔗 入場券登記連結：
{% for registration in registration_links %}{% if registration_links|length > 1 %}參加者 {{ forloop.counter }}：{% endif %}{{ registration.registration_url }}
{% empty %}{{ action_url }}
{% endfor %}
⚠️ 完成付款後，仍需填寫以上表格以獲取入場券。

請妥善保存您的入場券，並於活動當天出示給現場工作人員，以便順利入場。

期待12月19日與您在台北相見！🇹🇼✨

感謝您的支持與信任！❤️

Cosmic135 團隊"""

BODY_EN = """Dear Participant,

🎉 Thank you for registering for Master TatKee’s “Numerology Decoding × Numerology Oracle Cards | Taipei Special Workshop”!

We are pleased to confirm that your payment has been successfully received! ❤️

📍 Event Details

📅 Date: Saturday, 19 December 2026
⏰ Time: 10:00 AM – 4:00 PM
🏢 Venue: Red Space, Taipei

🎟️ Important Reminder | Claim Your Entry Ticket

To ensure a smooth check-in experience, please click the link below and complete the registration form to obtain your event entry ticket.

🔗 Entry Ticket Registration Link:
{% for registration in registration_links %}{% if registration_links|length > 1 %}Participant {{ forloop.counter }}: {% endif %}{{ registration.registration_url }}
{% empty %}{{ action_url }}
{% endfor %}
⚠️ Even after payment has been confirmed, you are required to complete the above form to obtain your entry ticket.

Please keep your entry ticket and present it to our staff upon arrival.

We look forward to welcoming you in Taipei on 19 December! 🇹🇼✨

Thank you for your support!

Best regards,
Cosmic135 Team
www.cosmic135.com"""


def configure_tw_offers(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    shared = {
        "post_payment_email": "both",
        "email_subject_zh": SUBJECT_ZH,
        "email_subject_en": SUBJECT_EN,
        "email_body_zh": BODY_ZH,
        "email_body_en": BODY_EN,
    }
    Offer.objects.filter(stripe_test_price_id="price_1UN7pKG7cwotxqBtXgjBWDvO").update(
        registration_quantity=1,
        **shared,
    )
    Offer.objects.filter(stripe_test_price_id="price_1UMrsxG7cwotxqBtXjA9c6ol").update(
        registration_quantity=2,
        **shared,
    )


def reset_tw_offers(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    Offer.objects.filter(
        stripe_test_price_id__in=[
            "price_1UN7pKG7cwotxqBtXgjBWDvO",
            "price_1UMrsxG7cwotxqBtXjA9c6ol",
        ],
    ).update(
        registration_quantity=1,
        email_subject_zh="",
        email_subject_en="",
        email_body_zh="",
        email_body_en="",
    )


class Migration(migrations.Migration):
    dependencies = [("commerce", "0007_alter_offer_post_payment_email")]

    operations = [migrations.RunPython(configure_tw_offers, reset_tw_offers)]
