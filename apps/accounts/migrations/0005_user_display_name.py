from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0004_studentprofile_graduated_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="user",
            name="display_name",
            field=models.CharField(blank=True, max_length=80),
        ),
    ]
