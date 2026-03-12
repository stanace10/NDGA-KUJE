from django.conf import settings
from django.db import models

from apps.academics.models import AcademicSession, Term
from core.models import TimeStampedModel


class SetupStateCode(models.TextChoices):
    BOOT_EMPTY = "BOOT_EMPTY", "Boot Empty"
    SESSION_CREATED = "SESSION_CREATED", "Session Created"
    TERM_CREATED = "TERM_CREATED", "Term Created"
    CALENDAR_CONFIGURED = "CALENDAR_CONFIGURED", "Calendar Configured"
    CLASSES_CREATED = "CLASSES_CREATED", "Classes Created"
    SUBJECTS_CREATED = "SUBJECTS_CREATED", "Subjects Created"
    CLASS_SUBJECTS_MAPPED = "CLASS_SUBJECTS_MAPPED", "Class Subjects Mapped"
    GRADE_SCALE_CONFIGURED = "GRADE_SCALE_CONFIGURED", "Grade Scale Configured"
    IT_READY = "IT_READY", "IT Ready"


class SystemSetupState(TimeStampedModel):
    singleton_id = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    state = models.CharField(
        max_length=32,
        choices=SetupStateCode.choices,
        default=SetupStateCode.BOOT_EMPTY,
    )
    current_session = models.ForeignKey(
        AcademicSession,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    current_term = models.ForeignKey(
        Term,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    finalized_at = models.DateTimeField(null=True, blank=True)
    finalized_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="setup_finalizations",
    )
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="setup_updates",
    )

    class Meta:
        verbose_name = "System Setup State"
        verbose_name_plural = "System Setup State"

    def __str__(self):
        return self.state

    @property
    def is_ready(self):
        return self.state == SetupStateCode.IT_READY

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(
            singleton_id=1,
            defaults={"state": SetupStateCode.BOOT_EMPTY},
        )
        return obj


class RuntimeFeatureFlags(TimeStampedModel):
    singleton_id = models.PositiveSmallIntegerField(default=1, unique=True, editable=False)
    cbt_enabled = models.BooleanField(default=False)
    election_enabled = models.BooleanField(default=False)
    offline_mode_enabled = models.BooleanField(default=True)
    lockdown_enabled = models.BooleanField(default=True)
    last_updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="runtime_feature_flag_updates",
    )

    class Meta:
        verbose_name = "Runtime Feature Flags"
        verbose_name_plural = "Runtime Feature Flags"

    def __str__(self):
        return (
            f"CBT={'ON' if self.cbt_enabled else 'OFF'}, "
            f"Election={'ON' if self.election_enabled else 'OFF'}"
        )

    @classmethod
    def get_solo(cls):
        defaults = {
            "cbt_enabled": bool(settings.FEATURE_FLAGS.get("CBT_ENABLED", False)),
            "election_enabled": bool(settings.FEATURE_FLAGS.get("ELECTION_ENABLED", False)),
            "offline_mode_enabled": bool(settings.FEATURE_FLAGS.get("OFFLINE_MODE_ENABLED", True)),
            "lockdown_enabled": bool(settings.FEATURE_FLAGS.get("LOCKDOWN_ENABLED", True)),
        }
        obj, created = cls.objects.get_or_create(singleton_id=1, defaults=defaults)
        if created or obj.last_updated_by_id is not None:
            return obj

        updated_fields = []
        for field_name, value in defaults.items():
            if getattr(obj, field_name) != value:
                setattr(obj, field_name, value)
                updated_fields.append(field_name)
        if updated_fields:
            obj.save(update_fields=[*updated_fields, "updated_at"])
        return obj
