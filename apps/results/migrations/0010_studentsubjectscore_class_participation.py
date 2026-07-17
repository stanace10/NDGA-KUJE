from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("results", "0009_alter_classresultstudentrecord_options_and_more")]

    operations = [
        migrations.AddField(
            model_name="studentsubjectscore",
            name="class_participation",
            field=models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=5),
        ),
    ]
