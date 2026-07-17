from django.db import migrations


def seed_roles(apps, schema_editor):
    Role = apps.get_model("accounts", "Role")
    default_roles = [
        ("IT_MANAGER", "IT Manager"),
        ("DEAN", "Dean"),
        ("FORM_TEACHER", "Form Teacher"),
        ("SUBJECT_TEACHER", "Subject Teacher"),
        ("BURSAR", "Bursar"),
        ("VP", "Vice Principal"),
        ("PRINCIPAL", "Principal"),
        ("STUDENT", "Student"),
    ]
    for code, name in default_roles:
        Role.objects.update_or_create(
            code=code,
            defaults={"name": name, "description": "", "is_system": True},
        )


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_roles, noop),
    ]

