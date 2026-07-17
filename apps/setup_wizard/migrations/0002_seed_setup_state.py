from django.db import migrations


def seed_setup_state(apps, schema_editor):
    SystemSetupState = apps.get_model("setup_wizard", "SystemSetupState")
    SystemSetupState.objects.get_or_create(singleton_id=1, defaults={"state": "BOOT_EMPTY"})


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("setup_wizard", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_setup_state, noop),
    ]
