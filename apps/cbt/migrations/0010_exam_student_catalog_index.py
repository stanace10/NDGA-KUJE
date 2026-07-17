from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("cbt", "0009_alter_option_label"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="exam",
            index=models.Index(
                fields=["session", "term", "academic_class", "status", "subject"],
                name="cbt_exam_student_catalog_idx",
            ),
        ),
    ]
