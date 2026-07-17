from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0012_dean_term_review_statuses"),
    ]

    operations = [
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="hostel_supervisor_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="parent_comment",
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name="classresultstudentrecord",
            name="term_weight_kg",
            field=models.DecimalField(blank=True, decimal_places=1, max_digits=5, null=True),
        ),
    ]
