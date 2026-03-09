from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0002_classresultcompilation_classresultstudentrecord_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="behavior_breakdown",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
