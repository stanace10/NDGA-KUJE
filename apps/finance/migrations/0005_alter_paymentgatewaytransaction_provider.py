from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0004_alter_paymentgatewaytransaction_provider"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentgatewaytransaction",
            name="provider",
            field=models.CharField(
                choices=[
                    ("PAYSTACK", "Paystack"),
                    ("REMITTA", "Remitta"),
                    ("FLUTTERWAVE", "Flutterwave"),
                ],
                default="PAYSTACK",
                max_length=16,
            ),
        ),
    ]
