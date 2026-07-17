from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.permissions import has_any_role
from apps.academics.models import AcademicClass, StudentClassEnrollment, StudentSubjectEnrollment
from apps.dashboard.ai_tools import answer_student_tutor_prompt, generate_lesson_plan_bundle
from apps.dashboard.forms import (
    AITutorQuestionForm,
    ClubForm,
    DocumentVaultUploadForm,
    LearningResourceForm,
    LessonPlannerForm,
    LMSAssignmentForm,
    LMSAssignmentGradingForm,
    LMSClassroomForm,
    LMSDiscussionCommentForm,
    LMSLessonForm,
    LMSModuleForm,
    LMSSubmissionForm,
    StudentClubMembershipForm,
    WeeklyChallengeForm,
    WeeklyChallengeSubmissionForm,
)
from apps.dashboard.models import (
    Club,
    LearningResource,
    LearningResourceCategory,
    LessonPlanDraft,
    LMSAssignment,
    LMSAssignmentSubmission,
    LMSClassroom,
    LMSDiscussionComment,
    LMSLesson,
    LMSLessonProgress,
    LMSModule,
    LMSSubmissionStatus,
    PortalDocument,
    StudentClubMembership,
    WeeklyChallenge,
    WeeklyChallengeSubmission,
)
from apps.dashboard.views import PortalPageView, StudentPortalBaseView, StaffPortalBaseView, _current_window, _student_dashboard_payload
from apps.notifications.services import notify_assignment_deadline
from apps.pdfs.services import qr_code_data_uri
from apps.tenancy.utils import build_portal_url


def _student_lms_classroom_queryset(*, payload):
    current_session = payload.get("current_session")
    current_term = payload.get("current_term")
    current_enrollment = payload.get("current_enrollment")
    offered_subjects = payload.get("offered_subjects") or []
    subject_ids = [row.subject_id for row in offered_subjects]

    classroom_qs = LMSClassroom.objects.filter(
        is_published=True,
        teacher_assignment__is_active=True,
    ).select_related(
        "teacher_assignment__teacher",
        "teacher_assignment__academic_class",
        "teacher_assignment__subject",
        "teacher_assignment__session",
        "teacher_assignment__term",
    )
    if current_session:
        classroom_qs = classroom_qs.filter(teacher_assignment__session=current_session)
    if current_term:
        classroom_qs = classroom_qs.filter(teacher_assignment__term=current_term)
    if current_enrollment:
        cohort_ids = current_enrollment.academic_class.instructional_class.cohort_class_ids()
        classroom_qs = classroom_qs.filter(teacher_assignment__academic_class_id__in=cohort_ids)
    else:
        classroom_qs = classroom_qs.none()
    if subject_ids:
        classroom_qs = classroom_qs.filter(teacher_assignment__subject_id__in=subject_ids)
    else:
        classroom_qs = classroom_qs.none()
    return classroom_qs.order_by(
        "teacher_assignment__academic_class__code",
        "teacher_assignment__subject__name",
    ).distinct()


def _teacher_lms_classroom_queryset(*, teacher):
    return LMSClassroom.objects.filter(
        teacher_assignment__teacher=teacher,
        teacher_assignment__is_active=True,
    ).select_related(
        "teacher_assignment__academic_class",
        "teacher_assignment__subject",
        "teacher_assignment__session",
        "teacher_assignment__term",
    ).order_by(
        "teacher_assignment__academic_class__code",
        "teacher_assignment__subject__name",
    )


class StudentLearningHubView(StudentPortalBaseView):
    template_name = "dashboard/student_learning_hub.html"
    portal_description = "Practice resources, assignments, past questions, and AI tutor guidance."

    def _tutor_form(self):
        current_session, _ = _current_window()
        return AITutorQuestionForm(student=self.request.user, session=current_session)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_dashboard_payload(self.request, self.request.user)
        context.update(payload)

        current_session = payload.get("current_session")
        current_term = payload.get("current_term")
        current_enrollment = payload.get("current_enrollment")
        offered_subjects = payload.get("offered_subjects") or []
        subject_ids = [row.subject_id for row in offered_subjects]

        resource_qs = LearningResource.objects.filter(is_published=True)
        if current_session:
            resource_qs = resource_qs.filter(Q(session=current_session) | Q(session__isnull=True))
        else:
            resource_qs = resource_qs.filter(session__isnull=True)
        if current_term:
            resource_qs = resource_qs.filter(Q(term=current_term) | Q(term__isnull=True))
        else:
            resource_qs = resource_qs.filter(term__isnull=True)
        if current_enrollment:
            resource_qs = resource_qs.filter(
                Q(academic_class=current_enrollment.academic_class.instructional_class)
                | Q(academic_class=current_enrollment.academic_class)
                | Q(academic_class__isnull=True)
            )
        else:
            resource_qs = resource_qs.filter(academic_class__isnull=True)
        if subject_ids:
            resource_qs = resource_qs.filter(Q(subject_id__in=subject_ids) | Q(subject__isnull=True))
        else:
            resource_qs = resource_qs.filter(subject__isnull=True)

        lesson_qs = LessonPlanDraft.objects.filter(publish_to_learning_hub=True)
        if current_session:
            lesson_qs = lesson_qs.filter(Q(session=current_session) | Q(session__isnull=True))
        else:
            lesson_qs = lesson_qs.filter(session__isnull=True)
        if current_term:
            lesson_qs = lesson_qs.filter(Q(term=current_term) | Q(term__isnull=True))
        else:
            lesson_qs = lesson_qs.filter(term__isnull=True)
        if current_enrollment:
            lesson_qs = lesson_qs.filter(
                academic_class=current_enrollment.academic_class.instructional_class
            )
        else:
            lesson_qs = lesson_qs.none()
        if subject_ids:
            lesson_qs = lesson_qs.filter(subject_id__in=subject_ids)
        else:
            lesson_qs = lesson_qs.none()

        challenge_qs = WeeklyChallenge.objects.filter(is_published=True)
        if current_session:
            challenge_qs = challenge_qs.filter(Q(session=current_session) | Q(session__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(session__isnull=True)
        if current_term:
            challenge_qs = challenge_qs.filter(Q(term=current_term) | Q(term__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(term__isnull=True)
        if current_enrollment:
            cohort_ids = current_enrollment.academic_class.instructional_class.cohort_class_ids()
            challenge_qs = challenge_qs.filter(Q(academic_class_id__in=cohort_ids) | Q(academic_class__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(academic_class__isnull=True)

        context["resource_rows"] = list(resource_qs.select_related("academic_class", "subject", "uploaded_by")[:18])
        context["lesson_rows"] = list(lesson_qs.select_related("teacher", "academic_class", "subject").order_by("-created_at")[:10])
        context["challenge_rows"] = list(challenge_qs.select_related("academic_class")[:5])
        context["weekly_challenge_url"] = reverse("dashboard:student-weekly-challenge")
        context["tutor_form"] = kwargs.get("tutor_form") or self._tutor_form()
        context["tutor_reply"] = kwargs.get("tutor_reply")
        context["practice_exam_url"] = reverse("cbt:student-exam-list")
        return context

    def post(self, request, *args, **kwargs):
        tutor_form = AITutorQuestionForm(
            request.POST,
            student=request.user,
            session=_current_window()[0],
        )
        if not tutor_form.is_valid():
            return self.render_to_response(self.get_context_data(tutor_form=tutor_form))
        payload = _student_dashboard_payload(self.request, self.request.user)
        tutor_reply = answer_student_tutor_prompt(
            subject_name=getattr(tutor_form.cleaned_data.get("subject"), "name", ""),
            question=tutor_form.cleaned_data["question"],
            class_code=payload.get("current_class_code") or "Current Class",
            weak_subjects=[row["subject"] for row in (payload.get("student_analytics", {}).get("weak_subjects") or [])[:3]],
        )
        return self.render_to_response(
            self.get_context_data(
                tutor_form=tutor_form,
                tutor_reply=tutor_reply,
            )
        )


class StudentLMSView(StudentPortalBaseView):
    template_name = "dashboard/student_lms.html"
    portal_description = "Follow classroom modules, complete lessons, submit work, and read teacher feedback."

    def _selected_classroom(self, classroom_qs):
        raw_id = (self.request.GET.get("classroom") or self.request.POST.get("classroom_id") or "").strip()
        if raw_id.isdigit():
            row = classroom_qs.filter(pk=int(raw_id)).first()
            if row is not None:
                return row
        return classroom_qs.first()

    def _selected_assignment(self, assignment_qs):
        raw_id = (self.request.GET.get("assignment") or self.request.POST.get("assignment_id") or "").strip()
        if raw_id.isdigit():
            row = assignment_qs.filter(pk=int(raw_id)).first()
            if row is not None:
                return row
        return assignment_qs.first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_dashboard_payload(self.request, self.request.user)
        context.update(payload)

        classroom_qs = _student_lms_classroom_queryset(payload=payload)
        selected_classroom = kwargs.get("selected_classroom") or self._selected_classroom(classroom_qs)
        assignment_qs = LMSAssignment.objects.none()
        selected_assignment = None
        submission_rows = {}
        progress_rows = {}
        module_rows = []
        comment_rows = []
        completed_lessons = 0
        total_lessons = 0

        if selected_classroom is not None:
            module_qs = LMSModule.objects.filter(
                classroom=selected_classroom,
                is_published=True,
            ).prefetch_related(
                Prefetch(
                    "lessons",
                    queryset=LMSLesson.objects.filter(is_published=True).order_by("sort_order", "created_at"),
                )
            )
            module_rows = list(module_qs.order_by("sort_order", "created_at"))
            lesson_ids = [lesson.id for module in module_rows for lesson in module.lessons.all()]
            progress_rows = {
                row.lesson_id: row
                for row in LMSLessonProgress.objects.filter(
                    lesson_id__in=lesson_ids,
                    student=self.request.user,
                )
            }
            total_lessons = len(lesson_ids)
            completed_lessons = sum(1 for row in progress_rows.values() if row.is_completed)
            assignment_qs = LMSAssignment.objects.filter(
                classroom=selected_classroom,
                is_published=True,
            ).order_by("due_at", "-created_at")
            submission_rows = {
                row.assignment_id: row
                for row in LMSAssignmentSubmission.objects.filter(
                    assignment__in=assignment_qs,
                    student=self.request.user,
                ).select_related("graded_by")
            }
            comment_rows = list(
                LMSDiscussionComment.objects.filter(classroom=selected_classroom)
                .select_related("author", "module", "assignment")
                .order_by("-created_at")[:20]
            )
            selected_assignment = kwargs.get("selected_assignment") or self._selected_assignment(assignment_qs)

        context["classroom_rows"] = list(classroom_qs)
        context["selected_classroom"] = selected_classroom
        context["module_rows"] = module_rows
        context["assignment_rows"] = list(assignment_qs)
        context["selected_assignment"] = selected_assignment
        context["submission_rows"] = submission_rows
        context["progress_rows"] = progress_rows
        context["comment_rows"] = comment_rows
        context["completed_lessons"] = completed_lessons
        context["total_lessons"] = total_lessons
        context["completion_percent"] = int((completed_lessons / total_lessons) * 100) if total_lessons else 0
        context["submission_form"] = kwargs.get("submission_form") or LMSSubmissionForm(
            instance=submission_rows.get(getattr(selected_assignment, "id", None))
        )
        context["comment_form"] = kwargs.get("comment_form") or LMSDiscussionCommentForm(
            student=self.request.user,
            classroom=selected_classroom,
        )
        return context

    def post(self, request, *args, **kwargs):
        payload = _student_dashboard_payload(self.request, self.request.user)
        classroom_qs = _student_lms_classroom_queryset(payload=payload)
        selected_classroom = self._selected_classroom(classroom_qs)
        if selected_classroom is None:
            messages.error(request, "No classroom is available for your current subjects.")
            return redirect("dashboard:student-lms")

        action = (request.POST.get("action") or "").strip().lower()
        redirect_url = f"{reverse('dashboard:student-lms')}?classroom={selected_classroom.id}"

        if action == "mark_lesson_complete":
            lesson = get_object_or_404(
                LMSLesson.objects.filter(module__classroom=selected_classroom, is_published=True),
                pk=request.POST.get("lesson_id"),
            )
            progress_row, _created = LMSLessonProgress.objects.get_or_create(
                lesson=lesson,
                student=request.user,
            )
            progress_row.last_opened_at = timezone.now()
            progress_row.is_completed = True
            if progress_row.completed_at is None:
                progress_row.completed_at = timezone.now()
            progress_row.save()
            messages.success(request, "Lesson marked as completed.")
            return redirect(redirect_url)

        if action == "submit_assignment":
            assignment = get_object_or_404(
                LMSAssignment.objects.filter(classroom=selected_classroom, is_published=True),
                pk=request.POST.get("assignment_id"),
            )
            submission = LMSAssignmentSubmission.objects.filter(
                assignment=assignment,
                student=request.user,
            ).first()
            submission_form = LMSSubmissionForm(request.POST, request.FILES, instance=submission)
            if not submission_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        selected_assignment=assignment,
                        submission_form=submission_form,
                    )
                )
            submission_row = submission_form.save(commit=False)
            submission_row.assignment = assignment
            submission_row.student = request.user
            submission_row.status = LMSSubmissionStatus.SUBMITTED
            submission_row.save()
            messages.success(request, "Assignment submitted successfully.")
            return redirect(f"{redirect_url}&assignment={assignment.id}")

        if action == "post_comment":
            comment_form = LMSDiscussionCommentForm(
                request.POST,
                student=request.user,
                classroom=selected_classroom,
            )
            if not comment_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        comment_form=comment_form,
                    )
                )
            comment_row = comment_form.save(commit=False)
            comment_row.author = request.user
            comment_row.classroom = selected_classroom
            comment_row.is_staff_note = False
            comment_row.save()
            messages.success(request, "Comment posted.")
            return redirect(redirect_url)

        messages.error(request, "Unknown LMS action.")
        return redirect(redirect_url)


class TeacherLMSView(StaffPortalBaseView):
    template_name = "dashboard/staff_lms.html"
    portal_description = "Build classroom modules, publish lessons, set assignments, and grade submissions."

    def _selected_classroom(self, classroom_qs):
        raw_id = (self.request.GET.get("classroom") or self.request.POST.get("classroom_id") or "").strip()
        if raw_id.isdigit():
            row = classroom_qs.filter(pk=int(raw_id)).first()
            if row is not None:
                return row
        return classroom_qs.first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        classroom_qs = _teacher_lms_classroom_queryset(teacher=self.request.user)
        selected_classroom = kwargs.get("selected_classroom") or self._selected_classroom(classroom_qs)

        module_rows = []
        assignment_rows = []
        submission_rows = []
        comment_rows = []
        if selected_classroom is not None:
            module_rows = list(
                LMSModule.objects.filter(classroom=selected_classroom)
                .prefetch_related(Prefetch("lessons", queryset=LMSLesson.objects.order_by("sort_order", "created_at")))
                .order_by("sort_order", "created_at")
            )
            assignment_rows = list(
                LMSAssignment.objects.filter(classroom=selected_classroom)
                .order_by("due_at", "-created_at")
            )
            submission_rows = list(
                LMSAssignmentSubmission.objects.filter(assignment__classroom=selected_classroom)
                .select_related("assignment", "student__student_profile", "graded_by")
                .order_by("status", "-updated_at")[:30]
            )
            comment_rows = list(
                LMSDiscussionComment.objects.filter(classroom=selected_classroom)
                .select_related("author", "module", "assignment")
                .order_by("-created_at")[:20]
            )

        context["classroom_rows"] = list(classroom_qs)
        context["selected_classroom"] = selected_classroom
        context["module_rows"] = module_rows
        context["assignment_rows"] = assignment_rows
        context["submission_rows"] = submission_rows
        context["comment_rows"] = comment_rows
        context["classroom_form"] = kwargs.get("classroom_form") or LMSClassroomForm(teacher=self.request.user)
        context["module_form"] = kwargs.get("module_form") or LMSModuleForm(
            teacher=self.request.user,
            initial={"classroom": getattr(selected_classroom, "pk", None)},
        )
        context["lesson_form"] = kwargs.get("lesson_form") or LMSLessonForm(
            teacher=self.request.user,
            classroom=selected_classroom,
        )
        context["assignment_form"] = kwargs.get("assignment_form") or LMSAssignmentForm(
            teacher=self.request.user,
            classroom=selected_classroom,
        )
        context["comment_form"] = kwargs.get("comment_form") or LMSDiscussionCommentForm(
            teacher=self.request.user,
            classroom=selected_classroom,
        )
        context["grading_form_class"] = LMSAssignmentGradingForm
        return context

    def post(self, request, *args, **kwargs):
        classroom_qs = _teacher_lms_classroom_queryset(teacher=request.user)
        selected_classroom = self._selected_classroom(classroom_qs)
        action = (request.POST.get("action") or "").strip().lower()
        redirect_url = reverse("dashboard:teacher-lms")
        if selected_classroom is not None:
            redirect_url = f"{redirect_url}?classroom={selected_classroom.id}"

        if action == "create_classroom":
            classroom_form = LMSClassroomForm(request.POST, teacher=request.user)
            if not classroom_form.is_valid():
                return self.render_to_response(self.get_context_data(classroom_form=classroom_form))
            classroom_row = classroom_form.save()
            messages.success(request, "Classroom created.")
            return redirect(f"{reverse('dashboard:teacher-lms')}?classroom={classroom_row.id}")

        if selected_classroom is None:
            messages.error(request, "Create a classroom first before adding LMS content.")
            return redirect(reverse("dashboard:teacher-lms"))

        if action == "create_module":
            module_form = LMSModuleForm(request.POST, teacher=request.user)
            if not module_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        module_form=module_form,
                    )
                )
            module_form.save()
            messages.success(request, "Module created.")
            return redirect(redirect_url)

        if action == "create_lesson":
            lesson_form = LMSLessonForm(request.POST, request.FILES, teacher=request.user, classroom=selected_classroom)
            if not lesson_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        lesson_form=lesson_form,
                    )
                )
            lesson_form.save()
            messages.success(request, "Lesson published.")
            return redirect(redirect_url)

        if action == "create_assignment":
            assignment_form = LMSAssignmentForm(request.POST, request.FILES, teacher=request.user, classroom=selected_classroom)
            if not assignment_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        assignment_form=assignment_form,
                    )
                )
            assignment_row = assignment_form.save()
            if assignment_row.is_published and assignment_row.due_at:
                notify_assignment_deadline(
                    academic_class=assignment_row.classroom.teacher_assignment.academic_class,
                    subject=assignment_row.classroom.teacher_assignment.subject,
                    topic=assignment_row.title,
                    due_date=assignment_row.due_at.date(),
                    session=assignment_row.classroom.teacher_assignment.session,
                    actor=request.user,
                    request=request,
                )
            messages.success(request, "Assignment published.")
            return redirect(f"{redirect_url}&assignment={assignment_row.id}")

        if action == "grade_submission":
            submission = get_object_or_404(
                LMSAssignmentSubmission.objects.filter(assignment__classroom=selected_classroom),
                pk=request.POST.get("submission_id"),
            )
            grading_form = LMSAssignmentGradingForm(request.POST, instance=submission, assignment=submission.assignment)
            if not grading_form.is_valid():
                messages.error(request, "Please correct the grading form and try again.")
                return redirect(f"{redirect_url}&assignment={submission.assignment_id}")
            submission_row = grading_form.save(commit=False)
            submission_row.graded_by = request.user
            submission_row.save()
            messages.success(request, "Submission graded.")
            return redirect(f"{redirect_url}&assignment={submission.assignment_id}")

        if action == "post_comment":
            comment_form = LMSDiscussionCommentForm(request.POST, teacher=request.user, classroom=selected_classroom)
            if not comment_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_classroom=selected_classroom,
                        comment_form=comment_form,
                    )
                )
            comment_row = comment_form.save(commit=False)
            comment_row.author = request.user
            comment_row.classroom = selected_classroom
            comment_row.is_staff_note = True
            comment_row.save()
            messages.success(request, "Classroom comment posted.")
            return redirect(redirect_url)

        messages.error(request, "Unknown LMS action.")
        return redirect(redirect_url)


class StudentDigitalIDView(StudentPortalBaseView):
    template_name = "dashboard/student_id_card.html"
    portal_description = "Digital ID card with QR verification for attendance, library, and gate checks."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_dashboard_payload(self.request, self.request.user)
        context.update(payload)
        student_profile = payload.get("student_profile")
        student_number = student_profile.student_number if student_profile else self.request.user.username
        verify_path = reverse("dashboard:student-id-verify", kwargs={"student_number": student_number})
        verify_url = build_portal_url(self.request, "landing", verify_path)
        context["verify_url"] = verify_url
        context["verification_qr_data_uri"] = qr_code_data_uri(verify_url)
        return context


class StudentDocumentVaultView(StudentPortalBaseView):
    template_name = "dashboard/student_document_vault.html"
    portal_description = "Transcript, certificate, and official record storage for your account."

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_student_dashboard_payload(self.request, self.request.user))
        category = (self.request.GET.get("category") or "").strip().upper()
        rows = PortalDocument.objects.filter(student=self.request.user, is_visible_to_student=True)
        if category:
            rows = rows.filter(category=category)
        context["document_rows"] = rows.select_related("academic_class", "session", "term", "uploaded_by")
        context["selected_category"] = category
        return context


class WeeklyChallengeManagementView(PortalPageView):
    template_name = "dashboard/weekly_challenge_manage.html"
    portal_name = "Weekly Challenge"
    portal_description = "Create weekly brain teasers, publish challenge prompts, and monitor participation by class."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_DEAN}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _form(self):
        current_session, current_term = _current_window()
        initial = {}
        if current_session:
            initial["session"] = current_session
        if current_term:
            initial["term"] = current_term
        return WeeklyChallengeForm(initial=initial)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_session, current_term = _current_window()
        challenge_rows = WeeklyChallenge.objects.select_related(
            "academic_class", "academic_class__base_class", "session", "term", "created_by"
        ).annotate(submission_total=Count("submissions"), correct_total=Count("submissions", filter=Q(submissions__is_correct=True)))
        if current_session:
            challenge_rows = challenge_rows.filter(Q(session=current_session) | Q(session__isnull=True))
        if current_term:
            challenge_rows = challenge_rows.filter(Q(term=current_term) | Q(term__isnull=True))
        context["current_session"] = current_session
        context["current_term"] = current_term
        context["challenge_form"] = kwargs.get("challenge_form") or self._form()
        context["challenge_rows"] = challenge_rows.order_by("-created_at")[:30]
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "create").strip().lower()
        if action == "toggle_status":
            challenge = get_object_or_404(WeeklyChallenge, pk=request.POST.get("challenge_id"))
            challenge.is_published = not challenge.is_published
            challenge.save(update_fields=["is_published", "updated_at"])
            messages.success(request, "Weekly challenge status updated.")
            return redirect("dashboard:weekly-challenge-manage")

        challenge_form = WeeklyChallengeForm(request.POST)
        if not challenge_form.is_valid():
            return self.render_to_response(self.get_context_data(challenge_form=challenge_form))
        challenge = challenge_form.save(commit=False)
        if challenge.academic_class_id and challenge.academic_class.base_class_id:
            challenge.academic_class = challenge.academic_class.instructional_class
        if not challenge.session_id or not challenge.term_id:
            current_session, current_term = _current_window()
            if current_session and not challenge.session_id:
                challenge.session = current_session
            if current_term and not challenge.term_id:
                challenge.term = current_term
        challenge.created_by = request.user
        challenge.save()
        messages.success(request, "Weekly challenge saved successfully.")
        return redirect("dashboard:weekly-challenge-manage")


class StudentWeeklyChallengeView(StudentPortalBaseView):
    template_name = "dashboard/student_weekly_challenge.html"
    portal_description = "Weekly challenge questions, leaderboard, and reward points for your class level."

    def _challenge_queryset(self, *, payload):
        current_session = payload.get("current_session")
        current_term = payload.get("current_term")
        current_enrollment = payload.get("current_enrollment")
        challenge_qs = WeeklyChallenge.objects.filter(is_published=True).select_related(
            "academic_class", "academic_class__base_class", "session", "term", "created_by"
        )
        if current_session:
            challenge_qs = challenge_qs.filter(Q(session=current_session) | Q(session__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(session__isnull=True)
        if current_term:
            challenge_qs = challenge_qs.filter(Q(term=current_term) | Q(term__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(term__isnull=True)
        if current_enrollment:
            cohort_ids = current_enrollment.academic_class.instructional_class.cohort_class_ids()
            challenge_qs = challenge_qs.filter(Q(academic_class_id__in=cohort_ids) | Q(academic_class__isnull=True))
        else:
            challenge_qs = challenge_qs.filter(academic_class__isnull=True)
        return challenge_qs.order_by("-created_at")

    def _selected_challenge(self, challenge_qs):
        raw_id = (self.request.GET.get("challenge_id") or self.request.POST.get("challenge_id") or "").strip()
        if raw_id.isdigit():
            selected = challenge_qs.filter(pk=int(raw_id)).first()
            if selected is not None:
                return selected
        return challenge_qs.first()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = _student_dashboard_payload(self.request, self.request.user)
        context.update(payload)
        challenge_qs = self._challenge_queryset(payload=payload)
        selected_challenge = self._selected_challenge(challenge_qs)
        submission = None
        if selected_challenge is not None:
            submission = WeeklyChallengeSubmission.objects.filter(
                challenge=selected_challenge,
                student=self.request.user,
            ).first()
        leaderboard_rows = []
        if selected_challenge is not None:
            leaderboard_rows = list(
                selected_challenge.submissions.select_related("student__student_profile")
                .order_by("-awarded_points", "updated_at", "student__username")[:10]
            )
        context["challenge_rows"] = list(challenge_qs[:12])
        context["selected_challenge"] = selected_challenge
        context["challenge_submission"] = submission
        context["submission_form"] = kwargs.get("submission_form") or WeeklyChallengeSubmissionForm(instance=submission)
        context["leaderboard_rows"] = leaderboard_rows
        return context

    def post(self, request, *args, **kwargs):
        payload = _student_dashboard_payload(self.request, self.request.user)
        challenge_qs = self._challenge_queryset(payload=payload)
        selected_challenge = self._selected_challenge(challenge_qs)
        if selected_challenge is None:
            messages.error(request, "No weekly challenge is available for your class right now.")
            return redirect("dashboard:student-weekly-challenge")
        submission = WeeklyChallengeSubmission.objects.filter(
            challenge=selected_challenge,
            student=request.user,
        ).first()
        submission_form = WeeklyChallengeSubmissionForm(request.POST, instance=submission)
        if not submission_form.is_valid():
            return self.render_to_response(self.get_context_data(submission_form=submission_form))
        row = submission_form.save(commit=False)
        row.challenge = selected_challenge
        row.student = request.user
        row.reviewed_by = None
        row.save()
        if row.is_correct:
            messages.success(request, f"Challenge submitted successfully. You earned {row.awarded_points} points.")
        else:
            messages.success(request, "Challenge submitted successfully. Keep trying the weekly teasers.")
        return redirect(f"{reverse('dashboard:student-weekly-challenge')}?challenge_id={selected_challenge.id}")


class TeacherLessonPlannerView(StaffPortalBaseView):
    template_name = "dashboard/teacher_lesson_planner.html"
    portal_description = "Generate lesson plans, quizzes, and assignments, then publish to the student learning hub."

    def _planner_form(self):
        return LessonPlannerForm(teacher=self.request.user)

    def _resource_form(self):
        return LearningResourceForm(teacher=self.request.user)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        planner_rows = LessonPlanDraft.objects.filter(teacher=self.request.user).select_related(
            "academic_class", "subject", "session", "term"
        ).order_by("-created_at")[:10]
        resource_rows = LearningResource.objects.filter(uploaded_by=self.request.user).select_related(
            "academic_class", "subject"
        ).order_by("-created_at")[:10]
        context["planner_form"] = kwargs.get("planner_form") or self._planner_form()
        context["resource_form"] = kwargs.get("resource_form") or self._resource_form()
        context["planner_rows"] = planner_rows
        context["resource_rows"] = resource_rows
        context["generated_plan"] = kwargs.get("generated_plan")
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "generate").strip().lower()
        if action == "upload_resource":
            resource_form = LearningResourceForm(request.POST, request.FILES, teacher=request.user)
            if not resource_form.is_valid():
                return self.render_to_response(self.get_context_data(resource_form=resource_form))
            resource = resource_form.save(commit=False)
            resource.uploaded_by = request.user
            resource.save()
            if (
                resource.is_published
                and resource.category == LearningResourceCategory.ASSIGNMENT
                and resource.academic_class_id
                and resource.subject_id
            ):
                notify_assignment_deadline(
                    academic_class=resource.academic_class,
                    subject=resource.subject,
                    topic=resource.title,
                    due_date=resource.due_date,
                    session=resource.session,
                    actor=request.user,
                    request=request,
                )
            messages.success(request, "Learning hub resource published.")
            return redirect("dashboard:teacher-lesson-planner")

        planner_form = LessonPlannerForm(request.POST, teacher=request.user)
        if not planner_form.is_valid():
            return self.render_to_response(self.get_context_data(planner_form=planner_form))

        bundle = generate_lesson_plan_bundle(
            subject_name=planner_form.cleaned_data["subject"].name,
            topic=planner_form.cleaned_data["topic"],
            class_code=planner_form.cleaned_data["academic_class"].code,
            teaching_goal=planner_form.cleaned_data.get("teaching_goal", ""),
            teacher_notes=planner_form.cleaned_data.get("teacher_notes", ""),
        )
        row = LessonPlanDraft.objects.create(
            teacher=request.user,
            academic_class=planner_form.cleaned_data["academic_class"],
            subject=planner_form.cleaned_data["subject"],
            session=planner_form.cleaned_data.get("session"),
            term=planner_form.cleaned_data.get("term"),
            topic=planner_form.cleaned_data["topic"],
            teaching_goal=planner_form.cleaned_data.get("teaching_goal", ""),
            teacher_notes=planner_form.cleaned_data.get("teacher_notes", ""),
            lesson_objectives=bundle["objectives"],
            lesson_outline=bundle["outline"],
            class_activity=bundle["activity"],
            assignment_text=bundle["assignment"],
            quiz_text=bundle["quiz"],
            publish_to_learning_hub=planner_form.cleaned_data.get("publish_to_learning_hub", False),
            assignment_due_date=planner_form.cleaned_data.get("assignment_due_date"),
        )
        if row.publish_to_learning_hub:
            resource_type = (
                LearningResourceCategory.ASSIGNMENT if row.assignment_text.strip() else LearningResourceCategory.STUDY_MATERIAL
            )
            LearningResource.objects.create(
                title=f"{row.subject.name}: {row.topic}",
                description=f"AI lesson planner output for {row.academic_class.code}.",
                category=resource_type,
                academic_class=row.academic_class,
                subject=row.subject,
                session=row.session,
                term=row.term,
                uploaded_by=request.user,
                content_text=(
                    f"Objectives\n{row.lesson_objectives}\n\n"
                    f"Lesson Outline\n{row.lesson_outline}\n\n"
                    f"Class Activity\n{row.class_activity}\n\n"
                    f"Assignment\n{row.assignment_text}\n\n"
                    f"Quiz\n{row.quiz_text}"
                ).strip(),
                due_date=row.assignment_due_date,
                is_published=True,
            )
            notify_assignment_deadline(
                academic_class=row.academic_class,
                subject=row.subject,
                topic=row.topic,
                due_date=row.assignment_due_date,
                session=row.session,
                actor=request.user,
                request=request,
            )
        messages.success(request, "Lesson plan generated successfully.")
        return self.render_to_response(
            self.get_context_data(
                planner_form=self._planner_form(),
                resource_form=self._resource_form(),
                generated_plan={
                    "row": row,
                    "generator": bundle["generator"],
                },
            )
        )


class ClubManagementView(PortalPageView):
    template_name = "dashboard/club_management.html"
    portal_name = "Clubs & Societies"
    portal_description = "Register clubs, assign students, track offices held, and keep co-curricular records ready for reports."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_DEAN}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _club_form(self):
        return ClubForm()

    def _membership_form(self):
        return StudentClubMembershipForm()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        current_session, _current_term = _current_window()
        club_rows = Club.objects.order_by("name")
        membership_rows = StudentClubMembership.objects.select_related("student__student_profile", "club", "session", "assigned_by")
        if current_session is not None:
            membership_rows = membership_rows.filter(session=current_session)
        context["club_form"] = kwargs.get("club_form") or self._club_form()
        context["membership_form"] = kwargs.get("membership_form") or self._membership_form()
        context["club_rows"] = club_rows
        context["membership_rows"] = membership_rows.order_by("club__name", "student__student_profile__student_number", "student__username")[:100]
        context["current_session"] = current_session
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "create_club").strip().lower()
        if action == "assign_membership":
            membership_form = StudentClubMembershipForm(request.POST)
            if not membership_form.is_valid():
                return self.render_to_response(self.get_context_data(membership_form=membership_form))
            row = membership_form.save(commit=False)
            row.assigned_by = request.user
            row.save()
            messages.success(request, "Club membership saved.")
            return redirect("dashboard:club-management")

        club_form = ClubForm(request.POST)
        if not club_form.is_valid():
            return self.render_to_response(self.get_context_data(club_form=club_form))
        club_form.save()
        messages.success(request, "Club saved successfully.")
        return redirect("dashboard:club-management")



class DocumentVaultManagementView(PortalPageView):
    template_name = "dashboard/document_vault_manage.html"
    portal_name = "Document Vault"
    portal_description = "Store transcripts, certificates, student records, and graduation records in one vault."

    def dispatch(self, request, *args, **kwargs):
        if not has_any_role(request.user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
            return redirect("dashboard:landing")
        return super().dispatch(request, *args, **kwargs)

    def _form(self):
        return DocumentVaultUploadForm()

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = (self.request.GET.get("category") or "").strip().upper()
        student_query = (self.request.GET.get("student") or "").strip()
        rows = PortalDocument.objects.select_related("student__student_profile", "academic_class", "session", "term", "uploaded_by")
        if category:
            rows = rows.filter(category=category)
        if student_query:
            rows = rows.filter(
                Q(student__username__icontains=student_query)
                | Q(student__first_name__icontains=student_query)
                | Q(student__last_name__icontains=student_query)
                | Q(student__student_profile__student_number__icontains=student_query)
            )
        context["upload_form"] = kwargs.get("upload_form") or self._form()
        context["document_rows"] = rows.order_by("-created_at")[:30]
        context["selected_category"] = category
        context["student_query"] = student_query
        return context

    def post(self, request, *args, **kwargs):
        upload_form = DocumentVaultUploadForm(request.POST, request.FILES)
        if not upload_form.is_valid():
            return self.render_to_response(self.get_context_data(upload_form=upload_form))
        row = upload_form.save(commit=False)
        row.uploaded_by = request.user
        row.save()
        messages.success(request, "Document added to vault.")
        return redirect(request.path)


class StudentIDVerificationView(TemplateView):
    template_name = "dashboard/student_id_verify.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        student_number = kwargs["student_number"]
        enrollment = (
            StudentClassEnrollment.objects.select_related("student", "student__student_profile", "academic_class")
            .filter(student__student_profile__student_number=student_number, is_active=True)
            .order_by("-updated_at")
            .first()
        )
        student = enrollment.student if enrollment else None
        context["student_number"] = student_number
        context["student"] = student
        context["student_profile"] = getattr(student, "student_profile", None) if student else None
        context["academic_class"] = enrollment.academic_class if enrollment else None
        context["is_valid_id"] = bool(student and getattr(student, "is_active", False))
        return context
