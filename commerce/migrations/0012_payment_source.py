from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0011_offer_specific_reminders")]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="manual_note",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="payment",
            name="source",
            field=models.CharField(
                choices=[("stripe", "Stripe"), ("manual", "Manual payment")],
                default="stripe",
                max_length=16,
            ),
        ),
    ]
