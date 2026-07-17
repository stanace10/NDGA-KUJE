from django.db import migrations, models


def update_assignment_label(apps, schema_editor):
    SchoolProfile = apps.get_model("dashboard", "SchoolProfile")
    SchoolProfile.objects.filter(
        assignment_label__in=["", "Project/Assignment", "CA4"]
    ).update(assignment_label="Assignment / Projects / Practical")


class Migration(migrations.Migration):
    dependencies = [("dashboard", "0016_publicsitesubmission_application_fee_receipt")]

    operations = [
        migrations.AlterField(
            model_name="schoolprofile",
            name="assignment_label",
            field=models.CharField(
                default="Assignment / Projects / Practical",
                max_length=40,
            ),
        ),
        migrations.RunPython(update_assignment_label, migrations.RunPython.noop),
    ]
