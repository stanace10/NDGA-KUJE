from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.cbt.exam_runtime import warm_exam_manifest
from apps.cbt.models import CBTExamStatus, Exam


class Command(BaseCommand):
    help = "Preload active/upcoming CBT manifests into the durable Redis state service."

    def add_arguments(self, parser):
        parser.add_argument("--hours", type=int, default=24)

    def handle(self, *args, **options):
        now = timezone.now()
        hours = max(int(options["hours"]), 1)
        cutoff = now + timedelta(hours=hours)
        exams = (
            Exam.objects.filter(status__in=[CBTExamStatus.ACTIVE, CBTExamStatus.APPROVED])
            .filter(schedule_end__gte=now, schedule_start__lte=cutoff)
            .select_related("subject", "academic_class")
            .order_by("schedule_start", "id")
        )
        exam_count = 0
        question_count = 0
        for exam in exams.iterator():
            loaded = warm_exam_manifest(exam)
            exam_count += 1
            question_count += loaded
            self.stdout.write(f"Warmed {exam.id}: {exam.title} ({loaded} questions)")
        self.stdout.write(
            self.style.SUCCESS(
                f"Warm cache complete: {exam_count} exams, {question_count} questions."
            )
        )
