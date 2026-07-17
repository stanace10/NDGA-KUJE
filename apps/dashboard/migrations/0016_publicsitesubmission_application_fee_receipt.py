from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0015_alter_publicwebsitesettings_hero_subtitle_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="publicsitesubmission",
            name="application_fee_receipt",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to="public_submissions/application_fee_receipts/",
            ),
        ),
    ]
