from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("notifications", "0002_emailreplythread_emailreplymessage_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="notification",
            name="category",
            field=models.CharField(
                choices=[
                    ("RESULTS", "Results"),
                    ("PAYMENT", "Payment"),
                    ("BIRTHDAY", "Birthday"),
                    ("ELECTION", "Election"),
                    ("SYSTEM", "System"),
                ],
                default="SYSTEM",
                max_length=24,
            ),
            preserve_default=True,
        ),
        migrations.CreateModel(
            name="BirthdayContact",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "contact_type",
                    models.CharField(
                        choices=[("PARENT", "Parent"), ("STAFF", "Staff")],
                        default="PARENT",
                        max_length=12,
                    ),
                ),
                ("full_name", models.CharField(max_length=180)),
                ("birth_month", models.PositiveSmallIntegerField()),
                ("birth_day", models.PositiveSmallIntegerField()),
                ("email", models.EmailField(blank=True, max_length=254)),
                ("phone", models.CharField(blank=True, max_length=80)),
                ("source_label", models.CharField(blank=True, max_length=180)),
                ("is_active", models.BooleanField(default=True)),
                (
                    "linked_user",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="birthday_contacts",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "ordering": ("birth_month", "birth_day", "full_name"),
                "indexes": [
                    models.Index(
                        fields=["contact_type", "birth_month", "birth_day", "is_active"],
                        name="notificatio_contact_927368_idx",
                    ),
                    models.Index(fields=["email"], name="notificatio_email_9d18b4_idx"),
                    models.Index(fields=["phone"], name="notificatio_phone_af7d17_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("contact_type", "full_name", "birth_month", "birth_day"),
                        name="unique_birthday_contact_day",
                    ),
                ],
            },
        ),
        migrations.CreateModel(
            name="BirthdayDispatch",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("birthday_year", models.PositiveSmallIntegerField()),
                (
                    "status",
                    models.CharField(
                        choices=[("SENT", "Sent"), ("SKIPPED", "Skipped"), ("FAILED", "Failed")],
                        default="SENT",
                        max_length=12,
                    ),
                ),
                ("sent_email", models.BooleanField(default=False)),
                ("sent_whatsapp", models.BooleanField(default=False)),
                ("message_subject", models.CharField(blank=True, max_length=180)),
                ("detail", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("dispatched_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "contact",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="dispatches",
                        to="notifications.birthdaycontact",
                    ),
                ),
            ],
            options={
                "ordering": ("-dispatched_at",),
                "indexes": [
                    models.Index(fields=["birthday_year", "status"], name="notificatio_birthda_5bf61e_idx"),
                    models.Index(fields=["dispatched_at"], name="notificatio_dispatc_b2f630_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=("contact", "birthday_year"),
                        name="unique_birthday_dispatch_year",
                    ),
                ],
            },
        ),
    ]
