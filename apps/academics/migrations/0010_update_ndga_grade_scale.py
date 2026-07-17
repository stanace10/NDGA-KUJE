from django.db import migrations


NDGA_GRADE_SCALE = (
    {"grade": "A1", "min_score": 90, "max_score": 100, "sort_order": 1},
    {"grade": "B2", "min_score": 80, "max_score": 89, "sort_order": 2},
    {"grade": "B3", "min_score": 75, "max_score": 79, "sort_order": 3},
    {"grade": "C4", "min_score": 70, "max_score": 74, "sort_order": 4},
    {"grade": "C5", "min_score": 65, "max_score": 69, "sort_order": 5},
    {"grade": "C6", "min_score": 60, "max_score": 64, "sort_order": 6},
    {"grade": "D7", "min_score": 55, "max_score": 59, "sort_order": 7},
    {"grade": "E8", "min_score": 50, "max_score": 54, "sort_order": 8},
    {"grade": "F9", "min_score": 0, "max_score": 49, "sort_order": 9},
)


def update_grade_scale(apps, schema_editor):
    GradeScale = apps.get_model("academics", "GradeScale")
    GradeScale.objects.filter(is_default=True).exclude(
        grade__in=[row["grade"] for row in NDGA_GRADE_SCALE]
    ).delete()
    for row in NDGA_GRADE_SCALE:
        GradeScale.objects.update_or_create(
            grade=row["grade"],
            defaults={**row, "is_default": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("academics", "0009_alter_sessionpromotionrecord_options_and_more"),
    ]

    operations = [
        migrations.RunPython(update_grade_scale, noop),
    ]
