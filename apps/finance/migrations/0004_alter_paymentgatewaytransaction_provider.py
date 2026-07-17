from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0003_financeinstitutionprofile"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentgatewaytransaction",
            name="provider",
            field=models.CharField(
                choices=[("PAYSTACK", "Paystack"), ("REMITTA", "Remitta")],
                default="PAYSTACK",
                max_length=16,
            ),
        ),
    ]
