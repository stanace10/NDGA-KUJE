from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0010_studentsubjectscore_class_participation"),
    ]

    operations = [
        migrations.AddField(
            model_name="classresultcompilation",
            name="approved_by_vp_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="form_teacher_completed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name="classresultcompilation",
            name="status",
            field=models.CharField(
                choices=[
                    ("DRAFT", "Draft"),
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
