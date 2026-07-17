from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.cbt.models import CBTExamStatus, Exam


EXAM_ID = 166
TITLE = "MON 12:55-2:55 SS3 Mathematics Objective Paper"


@transaction.atomic
def main():
    exam = Exam.objects.select_related("blueprint").get(id=EXAM_ID)
    if exam.attempts.exists():
        raise RuntimeError(f"Objective paper {exam.id} already has attempts. Refusing to mutate a live paper.")

    now = timezone.now()
    end_at = now + timedelta(hours=2)
    it_user = User.objects.get(username="admin@ndgakuje.org")

    exam.title = TITLE
    exam.status = CBTExamStatus.ACTIVE
    exam.schedule_start = now
    exam.schedule_end = end_at
    exam.open_now = True
    exam.is_time_based = True
    exam.activated_by = it_user
    exam.activated_at = now
    exam.activation_comment = "Activated immediately after the SS3 Mathematics theory paper on March 23, 2026."
    exam.timer_is_paused = False
    exam.save()

    blueprint = exam.blueprint
    blueprint.duration_minutes = 90
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    section_config = dict(blueprint.section_config or {})
    section_config.update(
        {
            "paper_code": "SS3-MTH-MOCK-OBJECTIVE",
            "flow_type": "OBJECTIVE_ONLY",
            "objective_count": 50,
            "theory_count": 0,
            "objective_target_max": "40.00",
            "theory_target_max": "0.00",
        }
    )
    blueprint.section_config = section_config
    blueprint.save()

    print(
        {
            "exam_id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat(),
            "schedule_end": exam.schedule_end.isoformat(),
            "duration_minutes": blueprint.duration_minutes,
            "attempts": exam.attempts.count(),
        }
    )


main()
