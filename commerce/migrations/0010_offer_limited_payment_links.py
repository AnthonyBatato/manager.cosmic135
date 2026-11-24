from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("commerce", "0009_offer_thank_you_page")]

    operations = [
        migrations.AddField(model_name="offer", name="max_completed_orders", field=models.PositiveSmallIntegerField(blank=True, help_text="Hard completed-payment limit. Limited offers use a Stripe Payment Link with the same limit.", null=True)),
        migrations.AddField(model_name="offer", name="sales_end_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="offer", name="sales_start_at", field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name="offer", name="stripe_live_payment_link_id", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="offer", name="stripe_live_payment_link_url", field=models.URLField(blank=True)),
        migrations.AddField(model_name="offer", name="stripe_test_payment_link_id", field=models.CharField(blank=True, max_length=120)),
        migrations.AddField(model_name="offer", name="stripe_test_payment_link_url", field=models.URLField(blank=True)),
    ]
