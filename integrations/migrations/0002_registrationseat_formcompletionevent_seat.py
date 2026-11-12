import django.db.models.deletion
import integrations.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("commerce", "0007_alter_offer_post_payment_email"),
        ("integrations", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="RegistrationSeat",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("seat_number", models.PositiveSmallIntegerField()),
                ("token", models.CharField(default=integrations.models.registration_token, max_length=80, unique=True)),
                ("registration_url", models.URLField(blank=True)),
                ("link_status", models.CharField(default="pending", max_length=16)),
                ("error", models.TextField(blank=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("submission_id", models.CharField(blank=True, max_length=160)),
                ("journey", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="registration_seats", to="commerce.journey")),
            ],
            options={"ordering": ["seat_number"]},
        ),
        migrations.AddField(
            model_name="formcompletionevent",
            name="seat",
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="form_events", to="integrations.registrationseat"),
        ),
        migrations.AddConstraint(
            model_name="registrationseat",
            constraint=models.UniqueConstraint(fields=("journey", "seat_number"), name="unique_registration_seat"),
        ),
    ]
