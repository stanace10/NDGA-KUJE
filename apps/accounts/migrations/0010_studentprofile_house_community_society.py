from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0009_alter_studentprofile_guardian_phone"),
    ]

    operations = [
        migrations.AddField(
            model_name="studentprofile",
            name="community",
            field=models.CharField(blank=True, max_length=120),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="house",
            field=models.CharField(blank=True, max_length=80),
        ),
        migrations.AddField(
            model_name="studentprofile",
            name="society",
            field=models.CharField(blank=True, max_length=120),
        ),
    ]
