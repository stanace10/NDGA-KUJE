from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0007_resultsheet_cbt_component_policies_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="management_actor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.SET_NULL,
                related_name="managed_class_result_records",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="management_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="management_status",
            field=models.CharField(
                choices=[
                    ("PENDING", "Pending Review"),
                    ("REVIEWED", "Reviewed"),
                    ("REJECTED", "Rejected For Correction"),
                ],
                default="PENDING",
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="principal_comment",
            field=models.TextField(blank=True),
        ),
    ]
