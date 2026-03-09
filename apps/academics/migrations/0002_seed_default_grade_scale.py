from django.db import migrations


def seed_default_grade_scale(apps, schema_editor):
    GradeScale = apps.get_model("academics", "GradeScale")
    defaults = [
        {"grade": "A", "min_score": 70, "max_score": 100, "sort_order": 1},
        {"grade": "B", "min_score": 60, "max_score": 69, "sort_order": 2},
        {"grade": "C", "min_score": 50, "max_score": 59, "sort_order": 3},
        {"grade": "D", "min_score": 40, "max_score": 49, "sort_order": 4},
        {"grade": "F", "min_score": 0, "max_score": 39, "sort_order": 5},
    ]
    for row in defaults:
        GradeScale.objects.update_or_create(
            grade=row["grade"],
            defaults={**row, "is_default": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_default_grade_scale, noop),
    ]
