from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
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
    StudentClubMembershipForm,
    WeeklyChallengeForm,
    WeeklyChallengeSubmissionForm,
)
from apps.dashboard.models import Club, LearningResource, LearningResourceCategory, LessonPlanDraft, PortalDocument, StudentClubMembership, WeeklyChallenge, WeeklyChallengeSubmission
from apps.dashboard.views import PortalPageView, StudentPortalBaseView, StaffPortalBaseView, _current_window, _student_dashboard_payload
from apps.notifications.services import notify_assignment_deadline
from apps.pdfs.services import qr_code_data_uri
from apps.tenancy.utils import build_portal_url


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
