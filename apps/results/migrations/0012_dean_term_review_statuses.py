from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0011_result_publication_approval_flow"),
    ]

    operations = [
        migrations.AlterField(
            model_name="classresultcompilation",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
                    ("SUBMITTED_TO_DEAN_FINAL", "Submitted To Dean Term Review"),
                    ("APPROVED_BY_DEAN_FINAL", "Approved By Dean Term Review"),
                    ("REJECTED_BY_DEAN_FINAL", "Rejected By Dean Term Review"),
                    ("SUBMITTED_TO_VP", "Submitted To VP"),
                    ("APPROVED_BY_VP", "Approved By VP - Ready For IT"),
                    ("REJECTED_BY_VP", "Rejected By VP"),
                    ("PUBLISHED", "Published"),
                ],
                default="DRAFT",
                max_length=30,
            ),
        ),
    ]
