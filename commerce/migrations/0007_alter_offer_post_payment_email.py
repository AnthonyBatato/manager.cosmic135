from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0006_cosmic_tools_registration")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="email_body_en",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="offer",
            name="email_body_zh",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="offer",
            name="email_subject_en",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="offer",
            name="email_subject_zh",
            field=models.CharField(blank=True, max_length=250),
        ),
        migrations.AddField(
            model_name="offer",
            name="registration_quantity",
            field=models.PositiveSmallIntegerField(
                default=1,
                help_text="Number of separate participant registration links created after payment.",
            ),
        ),
        migrations.AddField(
            model_name="journey",
            name="registration_quantity",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AlterField(
            model_name="offer",
            name="post_payment_email",
            field=models.CharField(
                choices=[
                    ("confirmation", "Confirmation email"),
                    ("registration", "Registration / next-step email"),
                    ("both", "Payment confirmation + registration (one email)"),
                ],
                default="registration",
                max_length=20,
            ),
        ),
    ]
