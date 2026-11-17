from django.db import migrations, models
import django.db.models.deletion


def assign_taipei_thank_you_page(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    LandingPage = apps.get_model("pages", "LandingPage")
    page = LandingPage.objects.filter(pk=3).first() or LandingPage.objects.filter(
        slug="workshop-tw-thank-you"
    ).first()
    if not page:
        return
    Offer.objects.filter(
        stripe_test_price_id__in=[
            "price_1UN7pKG7cwotxqBtXgjBWDvO",
            "price_1UMrsxG7cwotxqBtXjA9c6ol",
        ]
    ).update(thank_you_page_id=page.pk)


def unassign_taipei_thank_you_page(apps, schema_editor):
    Offer = apps.get_model("commerce", "Offer")
    Offer.objects.filter(thank_you_page_id=3).update(thank_you_page_id=None)


class Migration(migrations.Migration):
    dependencies = [
        ("pages", "0004_domain_provisioning"),
        ("commerce", "0008_configure_tw_workshop_offers"),
    ]

    operations = [
        migrations.AddField(
            model_name="offer",
            name="thank_you_page",
            field=models.ForeignKey(
                blank=True,
                help_text="Optional uploaded landing page used as this offer's post-payment design.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="thank_you_offers",
                to="pages.landingpage",
            ),
        ),
        migrations.RunPython(assign_taipei_thank_you_page, unassign_taipei_thank_you_page),
    ]
