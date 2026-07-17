from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def seed_runtime_flags(apps, schema_editor):
    RuntimeFeatureFlags = apps.get_model("setup_wizard", "RuntimeFeatureFlags")
    RuntimeFeatureFlags.objects.get_or_create(
        singleton_id=1,
        defaults={
            "cbt_enabled": False,
            "election_enabled": False,
            "offline_mode_enabled": True,
            "lockdown_enabled": True,
        },
    )


class Migration(migrations.Migration):

    dependencies = [
        ("setup_wizard", "0003_alter_systemsetupstate_state"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="RuntimeFeatureFlags",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("singleton_id", models.PositiveSmallIntegerField(default=1, editable=False, unique=True)),
                ("cbt_enabled", models.BooleanField(default=False)),
                ("election_enabled", models.BooleanField(default=False)),
                ("offline_mode_enabled", models.BooleanField(default=True)),
                ("lockdown_enabled", models.BooleanField(default=True)),
                (
                    "last_updated_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="runtime_feature_flag_updates",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Runtime Feature Flags",
                "verbose_name_plural": "Runtime Feature Flags",
            },
        ),
        migrations.RunPython(seed_runtime_flags, migrations.RunPython.noop),
    ]
