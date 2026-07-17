from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("setup_wizard", "0006_alter_academicoperationwindow_window_type")]

    operations = [
        migrations.AlterField(
            model_name="academicoperationwindow",
            name="window_type",
            field=models.CharField(
                choices=[
                    ("RESULTS", "Result Window"),
                    ("RESULT_CA1", "CA1 Result Window"),
                    ("RESULT_CA23", "CA2/CA3 Result Window"),
                    ("RESULT_CA4", "Assignment / Projects / Practical Result Window"),
                    ("RESULT_EXAM", "Exam Result Window"),
                    ("CBT", "CBT Window"),
                ],
                max_length=16,
                unique=True,
            ),
        ),
    ]
