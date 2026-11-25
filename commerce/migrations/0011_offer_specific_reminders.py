from django.db import migrations, models


REMINDER_SUBJECT_ZH = "溫馨提醒｜請完成台北特別場入場券登記"
REMINDER_SUBJECT_EN = "Friendly reminder | Complete your Taipei workshop entry ticket registration"

REMINDER_BODY_ZH = """您好！🥰

🎉 感謝您報名參加 TatKee 大師兄《數字解碼 × 數靈啟示牌｜台北特別場》！

我們已成功收到並確認您的付款。❤️

系統顯示您的入場券登記尚未完成，因此特別發送這封溫馨提醒。

📍 活動資訊

📅 日期：2026年12月19日（星期六）
⏰ 時間：上午10:00 – 下午4:00
🏢 地點：Red Space 多元商務空間・台北

🎟️ 溫馨提醒｜請完成入場券登記

為了確保您能順利入場，請點擊以下連結，填寫個人資料以獲取活動入場券。

🔗 入場券登記連結：
{% for registration in registration_links %}{% if registration_links|length > 1 %}參加者 {{ forloop.counter }}：{% endif %}{{ registration.registration_url }}
{% empty %}{{ action_url }}
{% endfor %}
⚠️ 每位參加者都需要完成自己的登記表格，才能獲取入場券。

如果您已經完成登記，請忽略此郵件；系統可能需要一些時間更新狀態。

請妥善保存您的入場券，並於活動當天出示給現場工作人員，以便順利入場。

期待12月19日與您在台北相見！🇹🇼✨

感謝您的支持與信任！❤️

Cosmic135 團隊"""

REMINDER_BODY_EN = """Dear Participant,

🎉 Thank you for registering for Master TatKee’s “Numerology Decoding × Numerology Oracle Cards | Taipei Special Workshop”!

We have successfully received and confirmed your payment. ❤️

Our system shows that your entry ticket registration has not yet been completed, so we are sending you this friendly reminder.

📍 Event Details

📅 Date: Saturday, 19 December 2026
⏰ Time: 10:00 AM – 4:00 PM
🏢 Venue: Red Space, Taipei

🎟️ Friendly Reminder | Claim Your Entry Ticket

To ensure a smooth check-in experience, please click the link below and complete the registration form to obtain your event entry ticket.

🔗 Entry Ticket Registration Link:
{% for registration in registration_links %}{% if registration_links|length > 1 %}Participant {{ forloop.counter }}: {% endif %}{{ registration.registration_url }}
{% empty %}{{ action_url }}
{% endfor %}
⚠️ Each participant must complete their own registration form to obtain an entry ticket.

If you have already completed the registration, please disregard this email; the system may need a short time to update your status.

Please keep your entry ticket and present it to our staff upon arrival.

We look forward to welcoming you in Taipei on 19 December! 🇹🇼✨

Thank you for your support!

Best regards,
Cosmic135 Team
www.cosmic135.com"""


def configure_tw_reminders(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    Offer.objects.filter(name__in=[
        "Workshop (TW) Single",
        "Workshop (TW) Duo",
        "Workshop (TW) Livestream Buy 1 Free 1",
    ]).update(
        reminder_subject_zh=REMINDER_SUBJECT_ZH,
        reminder_subject_en=REMINDER_SUBJECT_EN,
        reminder_body_zh=REMINDER_BODY_ZH,
        reminder_body_en=REMINDER_BODY_EN,
    )


class Migration(migrations.Migration):
    dependencies = [("commerce", "0010_offer_limited_payment_links")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="reminder_subject_zh",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="offer",
            name="reminder_subject_en",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="offer",
            name="reminder_body_zh",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="offer",
            name="reminder_body_en",
            field=models.TextField(blank=True),
        ),
        migrations.RunPython(configure_tw_reminders, migrations.RunPython.noop),
    ]
