from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0004_checkoutattempt_openai_obref_and_more")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="stripe_test_price_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="offer",
            name="stripe_live_price_id",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="offer",
            name="post_payment_email",
            field=models.CharField(
                choices=[
                    ("confirmation", "Confirmation email"),
                    ("registration", "Registration / next-step email"),
                    ("both", "Both emails"),
                ],
                default="registration",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="checkoutattempt",
            name="stripe_mode",
            field=models.CharField(default="test", max_length=8),
        ),
        migrations.AddField(
            model_name="stripeevent",
            name="livemode",
            field=models.BooleanField(default=False),
        ),
    ]
