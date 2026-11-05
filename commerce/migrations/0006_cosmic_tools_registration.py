from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0005_stripe_environments_and_email_mode")]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="cosmic_tools_course_id",
            field=models.PositiveBigIntegerField(
                blank=True,
                help_text="Course / form ID in Cosmic Tools. A customer-specific registration link is created after payment.",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="journey",
            name="cosmic_tools_course_id",
            field=models.PositiveBigIntegerField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="journey",
            name="registration_link_status",
            field=models.CharField(
                choices=[("not_required", "Not required"), ("pending", "Pending"), ("ready", "Ready"), ("failed", "Failed")],
                default="not_required",
                max_length=16,
            ),
        ),
        migrations.AddField(
            model_name="journey",
            name="registration_link_error",
            field=models.TextField(blank=True),
        ),
    ]
