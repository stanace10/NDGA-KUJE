from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("finance", "0008_financeinstitutionprofile_transcript_fee_amount_and_more"),
    ]

    operations = [
        migrations.AlterField(
            model_name="payment",
            name="payment_method",
            field=models.CharField(
                choices=[
                    ("PIXPAY", "PixPay"),
                    ("CASH", "Cash"),
                    ("TRANSFER", "Bank Transfer"),
                    ("POS", "POS"),
                    ("GATEWAY", "Gateway / Legacy"),
                    ("OTHER", "Other"),
                ],
                default="CASH",
                max_length=16,
            ),
        ),
    ]
