from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cbt", "0010_exam_student_catalog_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["status", "is_time_based", "schedule_end"],
                name="cbt_exam_auto_close_idx",
            ),
        ),
    ]
