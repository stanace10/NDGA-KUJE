import logging

from django.db.utils import OperationalError, ProgrammingError
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.cbt.models import (
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    ExamSimulation,
    Option,
    Question,
    QuestionBank,
    SimulationWrapper,
)
from apps.sync.content_sync import register_cbt_content_change
from apps.sync.models import SyncContentOperation

logger = logging.getLogger(__name__)


def _safe_register_cbt_content_change(*, instance, operation):
    try:
        register_cbt_content_change(instance=instance, operation=operation)
    except (ProgrammingError, OperationalError) as exc:
        # Keep CBT workflows operational even when sync tables are not yet present.
        logger.warning("Skipped CBT sync content change capture: %s", exc)


@receiver(post_save, sender=QuestionBank)
@receiver(post_save, sender=Question)
@receiver(post_save, sender=Option)
@receiver(post_save, sender=CorrectAnswer)
@receiver(post_save, sender=Exam)
@receiver(post_save, sender=ExamBlueprint)
@receiver(post_save, sender=ExamQuestion)
@receiver(post_save, sender=SimulationWrapper)
@receiver(post_save, sender=ExamSimulation)
def capture_cbt_content_upsert(sender, instance, **kwargs):
    _safe_register_cbt_content_change(
        instance=instance,
        operation=SyncContentOperation.UPSERT,
    )


@receiver(post_delete, sender=QuestionBank)
@receiver(post_delete, sender=Question)
@receiver(post_delete, sender=Option)
@receiver(post_delete, sender=CorrectAnswer)
@receiver(post_delete, sender=Exam)
@receiver(post_delete, sender=ExamBlueprint)
@receiver(post_delete, sender=ExamQuestion)
@receiver(post_delete, sender=SimulationWrapper)
@receiver(post_delete, sender=ExamSimulation)
def capture_cbt_content_delete(sender, instance, **kwargs):
    _safe_register_cbt_content_change(
        instance=instance,
        operation=SyncContentOperation.DELETE,
    )
