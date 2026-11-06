from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("automations", "0004_emaildelivery_email_delivery_exactly_one_subject")]

    operations = [
        migrations.AlterField(
            model_name="emailtemplate",
            name="subject_zh",
            field=models.CharField(max_length=250),
        ),
        migrations.AlterField(
            model_name="emailtemplate",
            name="body_zh",
            field=models.TextField(),
        ),
    ]
