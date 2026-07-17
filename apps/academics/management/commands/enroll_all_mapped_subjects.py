from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.academics.models import (
    AcademicSession,
    ClassSubject,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
)
from apps.setup_wizard.services import get_setup_state


def _normalize_levels(raw_levels):
    levels = []
    seen = set()
    for value in raw_levels or []:
        cleaned = (value or "").strip().upper()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        levels.append(cleaned)
    return levels


class Command(BaseCommand):
    help = (
        "Enroll active students in the selected class levels into all active "
        "subjects mapped to their instructional class."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--session",
            default="",
            help="Academic session name. Defaults to the current setup session.",
        )
        parser.add_argument(
            "--levels",
            nargs="+",
            default=["SS1", "SS2"],
            help="Instructional class levels to process (default: SS1 SS2).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview the changes without writing subject enrollments.",
        )

    def handle(self, *args, **options):
        session = self._resolve_session(options["session"])
        levels = _normalize_levels(options["levels"])
        if not levels:
            raise CommandError("Provide at least one class level with --levels.")

        mapped_subject_ids = self._mapped_subject_ids_by_level(levels)
        missing_levels = [level for level in levels if not mapped_subject_ids.get(level)]
        if missing_levels:
            raise CommandError(
                "No active class-subject mappings found for: "
                + ", ".join(sorted(missing_levels))
            )

        class_enrollments = [
            row
            for row in StudentClassEnrollment.objects.filter(
                session=session,
                is_active=True,
                student__is_active=True,
            ).select_related("student", "academic_class", "academic_class__base_class")
            if row.academic_class.instructional_class.code in mapped_subject_ids
        ]
        if not class_enrollments:
            self.stdout.write(
                self.style.WARNING(
                    f"No active student class enrollments found for {', '.join(levels)} in {session.name}."
                )
            )
            return

        existing_rows = defaultdict(dict)
        for row in StudentSubjectEnrollment.objects.filter(
            session=session,
            student_id__in=[enrollment.student_id for enrollment in class_enrollments],
        ):
            existing_rows[row.student_id][row.subject_id] = row

        summary = {
            "students": len(class_enrollments),
            "created": 0,
            "reactivated": 0,
            "unchanged": 0,
        }

        operation = self._preview if options["dry_run"] else self._apply
        operation(
            class_enrollments=class_enrollments,
            session=session,
            mapped_subject_ids=mapped_subject_ids,
            existing_rows=existing_rows,
            summary=summary,
        )

        self.stdout.write(
            self.style.SUCCESS(
                (
                    f"Processed {summary['students']} students for {session.name} "
                    f"({', '.join(levels)}). Created={summary['created']}, "
                    f"reactivated={summary['reactivated']}, unchanged={summary['unchanged']}."
                )
            )
        )

    def _resolve_session(self, session_name):
        if session_name:
            session = AcademicSession.objects.filter(name=session_name).first()
            if session is None:
                raise CommandError(f"Academic session '{session_name}' does not exist.")
            return session

        setup_state = get_setup_state()
        if setup_state.current_session_id:
            return setup_state.current_session

        session = AcademicSession.objects.order_by("-created_at").first()
        if session is None:
            raise CommandError("No academic session exists yet.")
        return session

    def _mapped_subject_ids_by_level(self, levels):
        mapped = defaultdict(list)
        for row in ClassSubject.objects.filter(
            academic_class__base_class__isnull=True,
            academic_class__code__in=levels,
            is_active=True,
            subject__is_active=True,
        ).order_by("academic_class__code", "subject__name"):
            mapped[row.academic_class.code].append(row.subject_id)
        return mapped

    def _preview(self, **kwargs):
        self._process_changes(commit=False, **kwargs)

    @transaction.atomic
    def _apply(self, **kwargs):
        self._process_changes(commit=True, **kwargs)

    def _process_changes(
        self,
        *,
        class_enrollments,
        session,
        mapped_subject_ids,
        existing_rows,
        summary,
        commit,
    ):
        for enrollment in class_enrollments:
            subject_ids = mapped_subject_ids[enrollment.academic_class.instructional_class.code]
            student_rows = existing_rows[enrollment.student_id]
            for subject_id in subject_ids:
                row = student_rows.get(subject_id)
                if row is None:
                    summary["created"] += 1
                    if commit:
                        row = StudentSubjectEnrollment.objects.create(
                            student=enrollment.student,
                            subject_id=subject_id,
                            session=session,
                            is_active=True,
                        )
                        student_rows[subject_id] = row
                elif not row.is_active:
                    summary["reactivated"] += 1
                    if commit:
                        row.is_active = True
                        row.save(update_fields=["is_active", "updated_at"])
                else:
                    summary["unchanged"] += 1
