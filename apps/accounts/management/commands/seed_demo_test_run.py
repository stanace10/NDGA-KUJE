from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.core.files.base import ContentFile
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    FormTeacherAssignment,
    StudentClassEnrollment,
    StudentSubjectEnrollment,
    Subject,
    SubjectCategory,
    TeacherSubjectAssignment,
    Term,
    TermName,
)
from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.accounts.models import Role, StaffProfile, StudentProfile, User
from apps.attendance.models import AttendanceRecord, AttendanceStatus, SchoolCalendar
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTSimulationCallbackType,
    CBTSimulationScoreMode,
    CBTSimulationSourceProvider,
    CBTSimulationToolCategory,
    CBTSimulationWrapperStatus,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    ExamReviewAction,
    ExamSimulation,
    Option,
    Question,
    QuestionBank,
    SimulationWrapper,
)
from apps.elections.models import Candidate, Election, ElectionStatus, Position, VoterGroup
from apps.elections.services import open_election, submit_vote_bundle
from apps.finance.models import (
    ChargeTargetType,
    Expense,
    ExpenseCategory,
    PaymentMethod,
    SalaryRecord,
    SalaryStatus,
    StudentCharge,
)
from apps.finance.services import record_manual_payment
from apps.results.models import (
    ClassCompilationStatus,
    ClassResultCompilation,
    ClassResultStudentRecord,
    ResultSheet,
    ResultSheetStatus,
    StudentSubjectScore,
)
from apps.setup_wizard.models import RuntimeFeatureFlags, SetupStateCode, SystemSetupState


PNG_1X1_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\rIDATx\x9cc``\xf8\x0f"
    b"\x00\x01\x01\x01\x00\x18\xdd\x8d\xb1\x00\x00\x00\x00IEND\xaeB`\x82"
)


class Command(BaseCommand):
    help = (
        "Seed NDGA demo data for full UI test run: classes, subjects, staff, students, "
        "attendance, results, CBT (objective/theory/simulation), finance, and election."
    )

    def add_arguments(self, parser):
        parser.add_argument("--password", default="admin")
        parser.add_argument("--session-name", default="2025/2026")
        parser.add_argument(
            "--term",
            default=TermName.FIRST,
            choices=[TermName.FIRST, TermName.SECOND, TermName.THIRD],
        )
        parser.add_argument(
            "--cleanup",
            action="store_true",
            help="Delete demo users (username starts with demo.)",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["cleanup"]:
            deleted, _ = User.objects.filter(username__startswith="demo.").delete()
            self.stdout.write(self.style.SUCCESS(f"Removed demo users and dependent rows: {deleted}"))
            return

        password = options["password"]
        session_name = options["session_name"]
        term_name = options["term"]

        required_roles = [
            ROLE_IT_MANAGER,
            ROLE_DEAN,
            ROLE_FORM_TEACHER,
            ROLE_SUBJECT_TEACHER,
            ROLE_BURSAR,
            ROLE_VP,
            ROLE_PRINCIPAL,
            ROLE_STUDENT,
        ]
        role_map = {r.code: r for r in Role.objects.filter(code__in=required_roles)}
        missing = sorted(set(required_roles) - set(role_map.keys()))
        if missing:
            raise CommandError(f"Missing role rows: {', '.join(missing)}")

        session, _ = AcademicSession.objects.get_or_create(name=session_name)
        terms = {}
        for term_code in (TermName.FIRST, TermName.SECOND, TermName.THIRD):
            term_row, _ = Term.objects.get_or_create(session=session, name=term_code)
            terms[term_code] = term_row
        active_term = terms[term_name]

        class_codes = ["JS1ALPHA", "JS1BETA", "JS2ALPHA", "SS1ALPHA", "SS2ALPHA"]
        classes = []
        for code in class_codes:
            row, _ = AcademicClass.objects.get_or_create(code=code, defaults={"display_name": code})
            if not row.display_name:
                row.display_name = code
                row.save(update_fields=["display_name"])
            classes.append(row)

        subject_specs = [
            ("MTH101", "Mathematics", SubjectCategory.SCIENCE),
            ("ENG101", "English Language", SubjectCategory.ARTS),
            ("BIO101", "Biology", SubjectCategory.SCIENCE),
            ("CHM101", "Chemistry", SubjectCategory.SCIENCE),
            ("PHY101", "Physics", SubjectCategory.SCIENCE),
            ("ICT101", "ICT", SubjectCategory.COMMERCIAL),
            ("GEO101", "Geography", SubjectCategory.ARTS),
        ]
        subjects = {}
        for code, name, category in subject_specs:
            sub, _ = Subject.objects.get_or_create(
                code=code,
                defaults={"name": name, "category": category, "is_active": True},
            )
            if sub.name != name or sub.category != category or not sub.is_active:
                sub.name = name
                sub.category = category
                sub.is_active = True
                sub.save(update_fields=["name", "category", "is_active"])
            subjects[code] = sub

        for academic_class in classes:
            for subject in subjects.values():
                ClassSubject.objects.update_or_create(
                    academic_class=academic_class,
                    subject=subject,
                    defaults={"is_active": True},
                )

        def ensure_user(username: str, role_code: str, first_name: str, last_name: str, *, secondary=()):
            user, _ = User.objects.get_or_create(username=username, defaults={"email": username})
            user.email = username
            user.first_name = first_name
            user.last_name = last_name
            user.primary_role = role_map[role_code]
            user.is_staff = role_code != ROLE_STUDENT
            user.is_superuser = role_code == ROLE_IT_MANAGER
            user.must_change_password = False
            user.set_password(password)
            user.save()
            if secondary:
                user.secondary_roles.set(Role.objects.filter(code__in=list(secondary)))
            else:
                user.secondary_roles.clear()
            return user

        it_user = ensure_user("admin@ndgakuje.org", ROLE_IT_MANAGER, "System", "ITManager")
        dean = ensure_user("demo.dean@ndgakuje.org", ROLE_DEAN, "Demo", "Dean", secondary=(ROLE_SUBJECT_TEACHER,))
        vp = ensure_user("demo.vp@ndgakuje.org", ROLE_VP, "Demo", "VP")
        principal = ensure_user("demo.principal@ndgakuje.org", ROLE_PRINCIPAL, "Demo", "Principal")
        bursar = ensure_user("demo.bursar@ndgakuje.org", ROLE_BURSAR, "Demo", "Bursar")
        subject_teachers = [
            ensure_user("demo.teacher1@ndgakuje.org", ROLE_SUBJECT_TEACHER, "Ada", "Teacher"),
            ensure_user("demo.teacher2@ndgakuje.org", ROLE_SUBJECT_TEACHER, "Ije", "Teacher"),
            ensure_user("demo.teacher3@ndgakuje.org", ROLE_SUBJECT_TEACHER, "Bola", "Teacher"),
            ensure_user("demo.teacher4@ndgakuje.org", ROLE_SUBJECT_TEACHER, "Kemi", "Teacher"),
            ensure_user("demo.teacher5@ndgakuje.org", ROLE_SUBJECT_TEACHER, "Muna", "Teacher"),
            dean,
        ]
        form_teachers = [
            ensure_user("demo.form1@ndgakuje.org", ROLE_FORM_TEACHER, "Form", "TeacherOne", secondary=(ROLE_SUBJECT_TEACHER,)),
            ensure_user("demo.form2@ndgakuje.org", ROLE_FORM_TEACHER, "Form", "TeacherTwo", secondary=(ROLE_SUBJECT_TEACHER,)),
            ensure_user("demo.form3@ndgakuje.org", ROLE_FORM_TEACHER, "Form", "TeacherThree", secondary=(ROLE_SUBJECT_TEACHER,)),
            ensure_user("demo.form4@ndgakuje.org", ROLE_FORM_TEACHER, "Form", "TeacherFour", secondary=(ROLE_SUBJECT_TEACHER,)),
            ensure_user("demo.form5@ndgakuje.org", ROLE_FORM_TEACHER, "Form", "TeacherFive", secondary=(ROLE_SUBJECT_TEACHER,)),
        ]

        for idx, user in enumerate([dean, vp, principal, bursar, *subject_teachers[:-1], *form_teachers], start=1):
            profile, _ = StaffProfile.objects.get_or_create(user=user, defaults={"staff_id": f"DEMO-STF-{idx:03d}"})
            if not profile.profile_photo:
                profile.profile_photo.save(
                    f"demo_staff_{idx}.png",
                    ContentFile(PNG_1X1_BYTES),
                    save=True,
                )

        for academic_class, form_teacher in zip(classes, form_teachers):
            FormTeacherAssignment.objects.update_or_create(
                academic_class=academic_class,
                session=session,
                defaults={"teacher": form_teacher, "is_active": True},
            )

        subject_codes = list(subjects.keys())
        for class_idx, academic_class in enumerate(classes):
            for subject_idx, subject_code in enumerate(subject_codes):
                teacher = subject_teachers[(class_idx + subject_idx) % len(subject_teachers)]
                TeacherSubjectAssignment.objects.update_or_create(
                    subject=subjects[subject_code],
                    academic_class=academic_class,
                    session=session,
                    term=active_term,
                    defaults={"teacher": teacher, "is_active": True},
                )

        students = []
        serial = 501
        for class_idx, academic_class in enumerate(classes, start=1):
            for offset in range(1, 4):
                username = f"demo.student{class_idx}{offset}@ndgakuje.org"
                student = ensure_user(username, ROLE_STUDENT, f"Student{class_idx}{offset}", f"Demo{class_idx}")
                student_number = f"NDGAK/25/{serial}"
                serial += 1
                profile, _ = StudentProfile.objects.update_or_create(
                    user=student,
                    defaults={
                        "student_number": student_number,
                        "gender": StudentProfile.Gender.FEMALE if offset % 2 else StudentProfile.Gender.MALE,
                        "admission_date": timezone.localdate() - timedelta(days=100),
                        "guardian_name": f"Guardian {class_idx}{offset}",
                        "guardian_phone": f"0801000{class_idx}{offset:02d}",
                        "guardian_email": f"guardian{class_idx}{offset}@example.com",
                        "nationality": "Nigerian",
                    },
                )
                if not profile.profile_photo:
                    profile.profile_photo.save(
                        f"demo_student_{class_idx}_{offset}.png",
                        ContentFile(PNG_1X1_BYTES),
                        save=True,
                    )
                StudentClassEnrollment.objects.update_or_create(
                    student=student,
                    session=session,
                    defaults={"academic_class": academic_class, "is_active": True},
                )
                for subject_id in ClassSubject.objects.filter(academic_class=academic_class, is_active=True).values_list("subject_id", flat=True):
                    StudentSubjectEnrollment.objects.update_or_create(
                        student=student,
                        subject_id=subject_id,
                        session=session,
                        defaults={"is_active": True},
                    )
                students.append(student)

        today = timezone.localdate()
        calendar, _ = SchoolCalendar.objects.get_or_create(
            session=session,
            term=active_term,
            defaults={"start_date": today - timedelta(days=45), "end_date": today + timedelta(days=45)},
        )
        attendance_days = []
        day = today - timedelta(days=7)
        while len(attendance_days) < 5:
            if calendar.is_school_day(day):
                attendance_days.append(day)
            day += timedelta(days=1)
        class_index = {c.code: idx for idx, c in enumerate(classes)}
        for student in students:
            enrollment = StudentClassEnrollment.objects.filter(student=student, session=session, is_active=True).select_related("academic_class").first()
            if not enrollment:
                continue
            marker = form_teachers[class_index[enrollment.academic_class.code]]
            for idx, mark_day in enumerate(attendance_days):
                AttendanceRecord.objects.update_or_create(
                    calendar=calendar,
                    academic_class=enrollment.academic_class,
                    student=student,
                    date=mark_day,
                    defaults={"status": AttendanceStatus.PRESENT if idx != 3 else AttendanceStatus.ABSENT, "marked_by": marker},
                )

        result_subjects = [subjects["MTH101"], subjects["ENG101"], subjects["BIO101"]]
        for class_pos, academic_class in enumerate(classes[:2], start=1):
            class_students = [row.student for row in StudentClassEnrollment.objects.filter(academic_class=academic_class, session=session, is_active=True).select_related("student")]
            for subject in result_subjects:
                sheet, _ = ResultSheet.objects.get_or_create(
                    academic_class=academic_class,
                    subject=subject,
                    session=session,
                    term=active_term,
                    defaults={"status": ResultSheetStatus.APPROVED_BY_DEAN, "created_by": subject_teachers[0]},
                )
                if sheet.status != ResultSheetStatus.APPROVED_BY_DEAN:
                    sheet.status = ResultSheetStatus.APPROVED_BY_DEAN
                    sheet.save(update_fields=["status", "updated_at"])
                for idx, student in enumerate(class_students, start=1):
                    StudentSubjectScore.objects.update_or_create(
                        result_sheet=sheet,
                        student=student,
                        defaults={
                            "ca1": Decimal("7.0"),
                            "ca2": Decimal("8.0"),
                            "ca3": Decimal("7.5"),
                            "ca4": Decimal("8.0"),
                            "objective": Decimal("28.0") + Decimal(idx % 4),
                            "theory": Decimal("12.0") + Decimal((idx + 1) % 3),
                        },
                    )
            comp_status = ClassCompilationStatus.PUBLISHED if class_pos == 1 else ClassCompilationStatus.SUBMITTED_TO_VP
            compilation, _ = ClassResultCompilation.objects.get_or_create(
                academic_class=academic_class,
                session=session,
                term=active_term,
                defaults={"form_teacher": form_teachers[class_pos - 1], "status": comp_status},
            )
            compilation.status = comp_status
            if comp_status == ClassCompilationStatus.PUBLISHED and not compilation.published_at:
                compilation.published_at = timezone.now()
            if comp_status == ClassCompilationStatus.SUBMITTED_TO_VP and not compilation.submitted_to_vp_at:
                compilation.submitted_to_vp_at = timezone.now()
            compilation.save(update_fields=["status", "published_at", "submitted_to_vp_at", "updated_at"])
            for student in class_students:
                ClassResultStudentRecord.objects.update_or_create(
                    compilation=compilation,
                    student=student,
                    defaults={"attendance_percentage": Decimal("88.00"), "behavior_rating": 4, "teacher_comment": "Good progress."},
                )

        for academic_class in classes:
            StudentCharge.objects.update_or_create(
                item_name=f"School Fees - {academic_class.code}",
                session=session,
                term=active_term,
                target_type=ChargeTargetType.CLASS,
                academic_class=academic_class,
                defaults={
                    "amount": Decimal("180000.00"),
                    "description": "Demo school fees",
                    "due_date": today + timedelta(days=14),
                    "created_by": bursar,
                    "is_active": True,
                    "student": None,
                },
            )
        for student in students[:6]:
            record_manual_payment(
                student=student,
                session=session,
                term=active_term,
                amount=Decimal("90000.00"),
                payment_method=PaymentMethod.TRANSFER,
                payment_date=today,
                received_by=bursar,
                note="Demo partial payment",
            )
        Expense.objects.update_or_create(
            title="Laboratory Maintenance",
            expense_date=today,
            defaults={"category": ExpenseCategory.ACADEMICS, "amount": Decimal("50000.00"), "description": "Demo expense", "created_by": bursar, "is_active": True},
        )
        for staff_user in subject_teachers[:2]:
            SalaryRecord.objects.update_or_create(
                staff=staff_user,
                month=today.replace(day=1),
                defaults={"amount": Decimal("120000.00"), "status": SalaryStatus.PAID, "payment_reference": "DEMO-SALARY", "recorded_by": bursar, "is_active": True},
            )

        # CBT setup
        assignment = TeacherSubjectAssignment.objects.filter(
            subject=subjects["MTH101"],
            academic_class=classes[0],
            session=session,
            term=active_term,
            is_active=True,
        ).select_related("teacher").first()
        if not assignment:
            raise CommandError("Could not resolve math assignment for demo CBT seed.")
        bank, _ = QuestionBank.objects.get_or_create(
            name="Demo JS1A Maths Bank",
            owner=assignment.teacher,
            assignment=assignment,
            subject=subjects["MTH101"],
            academic_class=classes[0],
            session=session,
            term=active_term,
            defaults={"description": "Demo test bank"},
        )

        def add_objective(stem: str, opts: list[tuple[str, str]], correct_label: str, ref: str):
            q, _ = Question.objects.get_or_create(
                question_bank=bank,
                created_by=assignment.teacher,
                subject=subjects["MTH101"],
                stem=stem,
                question_type=CBTQuestionType.OBJECTIVE,
                defaults={"marks": Decimal("1.00"), "source_reference": ref},
            )
            option_rows = []
            for idx, (label, text) in enumerate(opts, start=1):
                row, _ = Option.objects.update_or_create(
                    question=q,
                    label=label,
                    defaults={"option_text": text, "sort_order": idx},
                )
                option_rows.append(row)
            ans, _ = CorrectAnswer.objects.get_or_create(question=q)
            ans.correct_options.set([r for r in option_rows if r.label == correct_label])
            ans.is_finalized = True
            ans.note = "Demo answer"
            ans.save(update_fields=["is_finalized", "note", "updated_at"])
            return q

        q1 = add_objective("What is 12 + 8?", [("A", "20"), ("B", "18"), ("C", "24"), ("D", "22")], "A", "DEMO-Q1")
        q2 = add_objective("Solve: 6 x 7", [("A", "36"), ("B", "42"), ("C", "40"), ("D", "44")], "B", "DEMO-Q2")
        q3 = add_objective("3/4 as decimal is?", [("A", "0.5"), ("B", "0.75"), ("C", "0.8"), ("D", "0.9")], "B", "DEMO-Q3")
        q4, _ = Question.objects.get_or_create(
            question_bank=bank,
            created_by=assignment.teacher,
            subject=subjects["MTH101"],
            stem="Explain how to find the area of a rectangle.",
            question_type=CBTQuestionType.SHORT_ANSWER,
            defaults={"marks": Decimal("2.00"), "source_reference": "DEMO-Q4"},
        )

        sim_wrapper, _ = SimulationWrapper.objects.get_or_create(
            tool_name="Demo Motion Lab",
            tool_category=CBTSimulationToolCategory.SCIENCE,
            defaults={
                "tool_type": "HTML5",
                "source_provider": CBTSimulationSourceProvider.OTHER,
                "description": "Demo simulation wrapper",
                "online_url": "https://phet.colorado.edu/sims/html/pendulum-lab/latest/pendulum-lab_en.html",
                "score_mode": CBTSimulationScoreMode.AUTO,
                "max_score": Decimal("10.00"),
                "scoring_callback_type": CBTSimulationCallbackType.POST_MESSAGE,
                "evidence_required": False,
                "status": CBTSimulationWrapperStatus.APPROVED,
                "created_by": it_user,
                "dean_reviewed_by": dean,
                "dean_reviewed_at": timezone.now(),
                "is_active": True,
            },
        )
        sim_wrapper.status = CBTSimulationWrapperStatus.APPROVED
        sim_wrapper.is_active = True
        sim_wrapper.save(update_fields=["status", "is_active", "updated_at"])

        exam_active, _ = Exam.objects.get_or_create(
            title="Demo Maths CA2/CA3 CBT",
            exam_type=CBTExamType.CA,
            created_by=assignment.teacher,
            assignment=assignment,
            subject=subjects["MTH101"],
            academic_class=classes[0],
            session=session,
            term=active_term,
            defaults={"status": CBTExamStatus.ACTIVE, "question_bank": bank, "dean_reviewed_by": dean, "activated_by": it_user, "open_now": True, "is_time_based": False},
        )
        exam_active.status = CBTExamStatus.ACTIVE
        exam_active.question_bank = bank
        exam_active.dean_reviewed_by = dean
        exam_active.dean_reviewed_at = timezone.now()
        exam_active.activated_by = it_user
        exam_active.activated_at = timezone.now()
        exam_active.open_now = True
        exam_active.is_time_based = False
        exam_active.save(update_fields=["status", "question_bank", "dean_reviewed_by", "dean_reviewed_at", "activated_by", "activated_at", "open_now", "is_time_based", "updated_at"])
        ExamBlueprint.objects.update_or_create(
            exam=exam_active,
            defaults={
                "duration_minutes": 45,
                "max_attempts": 1,
                "shuffle_questions": False,
                "shuffle_options": False,
                "instructions": "Objective first then theory section.",
                "objective_writeback_target": CBTWritebackTarget.CA2,
                "theory_enabled": True,
                "theory_writeback_target": CBTWritebackTarget.CA3,
                "auto_show_result_on_submit": True,
                "finalize_on_logout": True,
                "allow_retake": False,
            },
        )
        for idx, q in enumerate([q1, q2, q3, q4], start=1):
            ExamQuestion.objects.update_or_create(exam=exam_active, question=q, defaults={"sort_order": idx, "marks": q.marks})
        ExamSimulation.objects.update_or_create(
            exam=exam_active,
            simulation_wrapper=sim_wrapper,
            defaults={"sort_order": 1, "writeback_target": CBTWritebackTarget.CA4, "is_required": True},
        )
        for from_s, to_s, action, actor in [
            ("DRAFT", "PENDING_DEAN", "SUBMIT_TO_DEAN", assignment.teacher),
            ("PENDING_DEAN", "APPROVED", "DEAN_APPROVE", dean),
            ("APPROVED", "ACTIVE", "IT_ACTIVATE", it_user),
        ]:
            ExamReviewAction.objects.get_or_create(exam=exam_active, from_status=from_s, to_status=to_s, action=action, defaults={"actor": actor, "comment": "Demo workflow"})

        exam_pending_dean, _ = Exam.objects.get_or_create(
            title="Demo English Pending Dean",
            exam_type=CBTExamType.CA,
            created_by=subject_teachers[1],
            assignment=TeacherSubjectAssignment.objects.filter(subject=subjects["ENG101"], academic_class=classes[0], session=session, term=active_term).first(),
            subject=subjects["ENG101"],
            academic_class=classes[0],
            session=session,
            term=active_term,
            defaults={"status": CBTExamStatus.PENDING_DEAN},
        )
        exam_pending_dean.status = CBTExamStatus.PENDING_DEAN
        exam_pending_dean.save(update_fields=["status", "updated_at"])

        exam_pending_it, _ = Exam.objects.get_or_create(
            title="Demo Biology Approved Waiting IT",
            exam_type=CBTExamType.EXAM,
            created_by=subject_teachers[2],
            assignment=TeacherSubjectAssignment.objects.filter(subject=subjects["BIO101"], academic_class=classes[1], session=session, term=active_term).first(),
            subject=subjects["BIO101"],
            academic_class=classes[1],
            session=session,
            term=active_term,
            defaults={"status": CBTExamStatus.APPROVED, "dean_reviewed_by": dean, "dean_reviewed_at": timezone.now()},
        )
        exam_pending_it.status = CBTExamStatus.APPROVED
        exam_pending_it.dean_reviewed_by = dean
        exam_pending_it.dean_reviewed_at = timezone.now()
        exam_pending_it.save(update_fields=["status", "dean_reviewed_by", "dean_reviewed_at", "updated_at"])

        # Election setup
        election, _ = Election.objects.get_or_create(
            title=f"Student Leadership Election {session.name}",
            session=session,
            defaults={
                "description": "Demo election for UI testing",
                "status": ElectionStatus.DRAFT,
                "starts_at": timezone.now() - timedelta(hours=1),
                "ends_at": timezone.now() + timedelta(days=1),
                "created_by": it_user,
                "is_active": True,
            },
        )
        pos1, _ = Position.objects.get_or_create(election=election, name="Head Girl", defaults={"sort_order": 1, "is_active": True})
        pos2, _ = Position.objects.get_or_create(election=election, name="Sports Prefect", defaults={"sort_order": 2, "is_active": True})
        s1 = User.objects.get(username="demo.student11@ndgakuje.org")
        s2 = User.objects.get(username="demo.student12@ndgakuje.org")
        s3 = User.objects.get(username="demo.student21@ndgakuje.org")
        s4 = User.objects.get(username="demo.student22@ndgakuje.org")
        c1, _ = Candidate.objects.get_or_create(position=pos1, user=s1, defaults={"display_name": "Student 11", "manifesto": "Transparency and discipline.", "is_active": True})
        c2, _ = Candidate.objects.get_or_create(position=pos1, user=s2, defaults={"display_name": "Student 12", "manifesto": "Service and unity.", "is_active": True})
        c3, _ = Candidate.objects.get_or_create(position=pos2, user=s3, defaults={"display_name": "Student 21", "manifesto": "More sports activities.", "is_active": True})
        c4, _ = Candidate.objects.get_or_create(position=pos2, user=s4, defaults={"display_name": "Student 22", "manifesto": "Team spirit.", "is_active": True})
        vg, _ = VoterGroup.objects.get_or_create(
            election=election,
            name="All Students",
            defaults={"include_all_students": True, "include_all_staff": False, "is_active": True},
        )
        if not vg.include_all_students or not vg.is_active:
            vg.include_all_students = True
            vg.is_active = True
            vg.save(update_fields=["include_all_students", "is_active", "updated_at"])
        if election.status != ElectionStatus.OPEN:
            open_election(election=election, actor=it_user, request=None)
        voter = User.objects.get(username="demo.student13@ndgakuje.org")
        try:
            submit_vote_bundle(
                election=election,
                voter=voter,
                choices_map={str(pos1.id): str(c1.id), str(pos2.id): str(c3.id)},
                request=None,
                submission_token="demo-seed-vote",
            )
        except Exception:
            pass

        setup_state = SystemSetupState.get_solo()
        setup_state.state = SetupStateCode.IT_READY
        setup_state.current_session = session
        setup_state.current_term = active_term
        if setup_state.finalized_at is None:
            setup_state.finalized_at = timezone.now()
        setup_state.save(update_fields=["state", "current_session", "current_term", "finalized_at", "updated_at"])

        flags = RuntimeFeatureFlags.get_solo()
        flags.cbt_enabled = True
        flags.election_enabled = True
        flags.save(update_fields=["cbt_enabled", "election_enabled", "updated_at"])

        self.stdout.write(self.style.SUCCESS("Demo test-run dataset seeded successfully."))
        self.stdout.write(self.style.WARNING(f"Password for all demo users: {password!r}"))
        self.stdout.write("Key logins:")
        for username in [
            "admin@ndgakuje.org",
            "demo.dean@ndgakuje.org",
            "demo.form1@ndgakuje.org",
            "demo.teacher1@ndgakuje.org",
            "demo.vp@ndgakuje.org",
            "demo.principal@ndgakuje.org",
            "demo.bursar@ndgakuje.org",
            "demo.student11@ndgakuje.org",
            "demo.student12@ndgakuje.org",
        ]:
            self.stdout.write(f"- {username}")
