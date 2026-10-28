from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("pages", "0003_domainroute")]

    operations = [
        migrations.AddField(
            model_name="domain",
            name="next_provision_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domain",
            name="provisioned_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="domain",
            name="provisioning_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="domain",
            name="provisioning_error",
            field=models.TextField(blank=True),
        ),
    ]
