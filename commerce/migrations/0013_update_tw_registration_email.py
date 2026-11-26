from django.db import migrations


TW_OFFER_NAMES = [
    "Workshop (TW) Single",
    "Workshop (TW) Duo",
    "Workshop (TW) Livestream Buy 1 Free 1",
]

SUBJECT_ZH = "報名確認成功｜請完成參加者資料填寫｜台北工作坊"

BODY_ZH = """{{ customer.name|default:"參加者" }} 您好，

感謝您報名參加 TatKee 大師兄《數字解碼 × 數靈啟示牌》台北工作坊，您的報名已確認成功！🎉

為確保活動當天順利報到，請您先完成參加者資料填寫，並詳閱活動參加須知。

📝 參加者資料填寫＆活動須知

{% for registration in registration_links %}{% if registration_links|length > 1 %}參加者 {{ forloop.counter }}：
{% endif %}{{ registration.registration_url }}
{% empty %}{{ action_url }}
{% endfor %}
📌 重要提醒：請使用與支付報名款項時相同的電子郵件地址填寫表格，以便系統核對您的報名紀錄。

成功提交表格後，您將透過電子郵件收到專屬 QR Code 入場憑證。

請提前下載並妥善保存，活動當天出示予現場工作人員掃描，即可完成報到及入場。

📍 活動資訊

• 活動名稱：《數字解碼 × 數靈啟示牌》
• 活動日期：2026 年 12 月 19 日（星期六）
• 報到時間：上午 9:31
• 活動時間：上午 10:00 至下午 4:00
• 活動地點：Red Space 多元商務空間－Space C
• 活動地址：台北市松山區復興北路 15-2 號 B1

🎟️ 報到與入場提醒

1. 請務必於活動前完成參加者資料填寫，並仔細閱讀活動參加須知。

2. 請使用與報名付款時相同的電子郵件地址，以確保系統能順利核對您的報名資料。

3. 現場將於上午 9:31 開始開放報到，建議提前抵達，預留充足時間完成報到手續。

4. 活動當天請備妥專屬 QR Code，可使用手機出示或列印攜帶；使用手機時，建議調高螢幕亮度，方便掃描。

5. 請妥善保管您的入場憑證，避免公開分享，以保障您的入場權益。

👥 雙人報名特別提醒

若您是透過雙人優惠方案報名，請確保兩位參加者皆完成資料填寫。

完成後，請主動透過 LINE 告知小助理第二位參加者所填寫的電子郵件地址，以便我們核對資料，確保兩位都能順利收到專屬入場 QR Code。

🧥 出席服裝與冬季保暖提醒

12 月的台北已進入冬季，早晚氣溫較低，請留意天氣變化，做好保暖準備！❄️

建議以時尚休閒服裝（Smart Casual）出席，穿著整潔、舒適且得體即可，並避免穿著背心、海灘短褲及拖鞋等過於休閒的服裝。

由於室內外溫差可能較大，建議採取洋蔥式穿搭，並攜帶保暖外套或圍巾，方便依照現場溫度適時增減衣物。

💬 聯繫小助理

若您在填寫表格、核對報名資料或接收入場 QR Code 時遇到任何問題，歡迎透過 LINE 聯繫 TatKee 大師兄小助理，我們將竭誠為您協助。

👉 聯繫小助理：https://line.me/ti/p/ry-GMvJ6tk

---

這一天，我們將從生活中常見的門牌、車牌、手機號碼與銀行號碼出發，把數字翻譯成容易理解的語言，陪您建立更清晰的判讀方法與選擇方向。

期待與您在台北相見，一同探索數字與數靈啟示牌帶來的啟發！❤️

Cosmic 135｜TatKee 大師兄團隊 敬上"""


def update_tw_registration_email(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    Offer.objects.filter(name__in=TW_OFFER_NAMES).update(
        email_subject_zh=SUBJECT_ZH,
        email_body_zh=BODY_ZH,
    )


class Migration(migrations.Migration):
    dependencies = [("commerce", "0012_payment_source")]

    operations = [
        migrations.RunPython(update_tw_registration_email, migrations.RunPython.noop),
    ]
