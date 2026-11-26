from django.db import migrations, models


def set_taiwan_workshop_descriptions(apps, schema_editor):
    offers = apps.get_model("commerce", "Offer").objects.using(schema_editor.connection.alias)
    description = "數字解碼 × 數靈啟示牌工作坊"
    offers.filter(stripe_live_price_id="price_1UM1W2G7cwotxqBtjlzUsDv2").update(
        stripe_payment_description=description,
    )
    offers.filter(stripe_live_price_id="price_1UMrU2G7cwotxqBtcX2IzwDJ").update(
        stripe_payment_description=f"{description} (2人)",
    )


class Migration(migrations.Migration):
    dependencies = [("commerce", "0013_update_tw_registration_email")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="stripe_payment_description",
            field=models.CharField(
                blank=True,
                max_length=250,
                help_text="Optional description for payments created by Manager. Stripe Payment Links use their own settings.",
            ),
        ),
        migrations.RunPython(set_taiwan_workshop_descriptions, migrations.RunPython.noop),
    ]
