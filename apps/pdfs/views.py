from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_STUDENT, ROLE_VP
from apps.accounts.models import User
from apps.academics.models import AcademicSession, Term
from apps.accounts.permissions import has_any_role
from apps.accounts.services import resolve_role_home_url
from apps.audit.services import log_pdf_generation
from apps.pdfs.models import PDFArtifact
from apps.pdfs.services import (
    STAFF_REPORT_DOWNLOAD_ROLES,
    available_student_compilations,
    build_term_report_payload,
    can_staff_download_term_report,
    generate_performance_analysis_pdf,
    generate_term_report_pdf,
    generate_transcript_pdf,
)
from apps.dashboard.models import SchoolProfile
from apps.results.analytics import active_result_pin_for_student, build_student_performance_report
from apps.results.models import ClassCompilationStatus, ClassResultCompilation
from apps.setup_wizard.services import get_setup_state


def _pdf_download_response(*, pdf_bytes, filename):
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


def _pdf_runtime_error_response(*, request, fallback_url):
    messages.error(
        request,
        "PDF engine dependencies are not available on this machine. "
        "Install WeasyPrint runtime libraries and try again.",
    )
    return redirect(fallback_url)


def _student_transcript_request_allows_access(student):
    from apps.finance.models import TranscriptRequest

    latest_request = (
        TranscriptRequest.objects.filter(student=student)
        .order_by("-created_at")
        .first()
    )
    return latest_request if latest_request and latest_request.is_access_granted else None


def _result_pin_session_key(*, student_id, compilation_id):
    return f"pdfs.result_pin.{student_id}.{compilation_id}"


def _student_result_pin_is_verified(request, *, compilation):
    active_pin = active_result_pin_for_student(
        student=request.user,
        session=compilation.session,
        term=compilation.term,
    )
    if active_pin is None:
        return False
    return request.session.get(
        _result_pin_session_key(student_id=request.user.id, compilation_id=compilation.id)
    ) == active_pin.pin_code


def _student_result_pin_required(*, request, compilation):
    if not SchoolProfile.load().require_result_access_pin:
        return False
    return active_result_pin_for_student(
        student=request.user,
        session=compilation.session,
        term=compilation.term,
    ) is not None


def _ensure_student_report_access(request, *, compilation):
    if not SchoolProfile.load().require_result_access_pin:
        return True
    active_pin = active_result_pin_for_student(
        student=request.user,
        session=compilation.session,
        term=compilation.term,
    )
    if active_pin is None:
        messages.error(request, "Result access PIN is required, but no active PIN has been issued for this term yet.")
        return False
    if _student_result_pin_is_verified(request, compilation=compilation):
        return True
    messages.error(request, "Enter your result access PIN before opening this report.")
    return False


class StudentReportsView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "pdfs/student_reports.html"

    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def _filtered_compilations(self):
        compilations = available_student_compilations(self.request.user)
        setup_state = get_setup_state()
        requested_session_id = (self.request.GET.get("session_id") or "").strip()
        requested_term_id = (self.request.GET.get("term_id") or "").strip()

        session_ids = set(compilations.values_list("session_id", flat=True))
        if setup_state.current_session_id:
            session_ids.add(setup_state.current_session_id)
        available_sessions = list(AcademicSession.objects.filter(id__in=session_ids).distinct().order_by("-name"))
        selected_session = None
        if requested_session_id.isdigit():
            selected_session = next(
                (session for session in available_sessions if session.id == int(requested_session_id)),
                None,
            )
        if selected_session is None and setup_state.current_session_id:
            selected_session = next(
                (session for session in available_sessions if session.id == setup_state.current_session_id),
                None,
            )
        if selected_session is None and available_sessions:
            selected_session = available_sessions[0]
        if selected_session is not None:
            compilations = compilations.filter(session=selected_session)

        available_terms = list(
            Term.objects.filter(session=selected_session) if selected_session else Term.objects.none()
        )
        if not available_terms:
            available_terms = list(Term.objects.filter(id__in=compilations.values("term_id")))
        available_terms = list(
            Term.objects.filter(id__in=[term.id for term in available_terms]).distinct().select_related("session")
        )
        available_terms.sort(
            key=lambda term: (
                term.session.name,
                {"FIRST": 1, "SECOND": 2, "THIRD": 3}.get(term.name, 99),
            )
        )
        selected_term = None
        if requested_term_id.isdigit():
            selected_term = next(
                (term for term in available_terms if term.id == int(requested_term_id)),
                None,
            )
        if (
            selected_term is None
            and setup_state.current_term_id
            and selected_session
            and setup_state.current_session_id == selected_session.id
        ):
            selected_term = next(
                (term for term in available_terms if term.id == setup_state.current_term_id),
                None,
            )
        if selected_term is None and available_terms:
            selected_term = available_terms[0]
        if selected_term is not None:
            compilations = compilations.filter(term=selected_term)
        return compilations, available_sessions, available_terms, selected_session, selected_term

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        compilations, available_sessions, available_terms, selected_session, selected_term = self._filtered_compilations()
        school_profile = SchoolProfile.load()
        compilation_rows = []
        for compilation in compilations:
            pin_required = _student_result_pin_required(request=self.request, compilation=compilation)
            compilation_rows.append(
                {
                    "compilation": compilation,
                    "pin_required": pin_required,
                    "pin_verified": _student_result_pin_is_verified(self.request, compilation=compilation) if pin_required else True,
                }
            )

        context["compilation_rows"] = compilation_rows
        context["available_sessions"] = available_sessions
        context["available_terms"] = available_terms
        context["selected_session"] = selected_session
        context["selected_term"] = selected_term
        context["school_profile"] = school_profile
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=request.POST.get("compilation_id"),
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=request.user,
        )
        if action != "verify_pin":
            messages.error(request, "Invalid report access action.")
            return redirect("pdfs:student-reports")
        active_pin = active_result_pin_for_student(student=request.user, session=compilation.session, term=compilation.term)
        if active_pin is None:
            messages.error(request, "No active result access PIN is available for this result.")
            return redirect("pdfs:student-reports")
        entered_pin = (request.POST.get("pin_code") or "").strip().upper()
        if entered_pin != active_pin.pin_code:
            messages.error(request, "Invalid result access PIN.")
            return redirect("pdfs:student-reports")
        request.session[_result_pin_session_key(student_id=request.user.id, compilation_id=compilation.id)] = active_pin.pin_code
        messages.success(request, "Result access unlocked for this report.")
        return redirect("pdfs:student-reports")


class StudentTermReportDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def get(self, request, *args, **kwargs):
        compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=request.user,
        )
        if not _ensure_student_report_access(request, compilation=compilation):
            return redirect("pdfs:student-reports")
        try:
            pdf_bytes, _artifact = generate_term_report_pdf(
                request=request,
                student=request.user,
                compilation=compilation,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url="pdfs:student-reports",
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TERM_REPORT",
                "student_id": str(request.user.id),
                "compilation_id": str(compilation.id),
            },
        )
        filename = (
            f"NDGA-Term-Report-{request.user.username}-"
            f"{compilation.session.name}-{compilation.term.name}.pdf"
        )
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StudentTermReportView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "pdfs/student_term_report_view.html"

    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def dispatch(self, request, *args, **kwargs):
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=request.user,
        )
        if not _ensure_student_report_access(request, compilation=self.compilation):
            return redirect("pdfs:student-reports")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        payload = build_term_report_payload(
            student=self.request.user,
            compilation=self.compilation,
        )
        context["compilation"] = self.compilation
        context["payload"] = payload
        return context


class StudentPerformanceAnalysisView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "pdfs/student_performance_analysis_view.html"

    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def dispatch(self, request, *args, **kwargs):
        self.compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=request.user,
        )
        if not _ensure_student_report_access(request, compilation=self.compilation):
            return redirect("pdfs:student-reports")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["compilation"] = self.compilation
        context["payload"] = build_student_performance_report(
            student=self.request.user,
            session=self.compilation.session,
            term=self.compilation.term,
        )
        return context


class StudentPerformanceAnalysisDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def get(self, request, *args, **kwargs):
        compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
            student_records__student=request.user,
        )
        if not _ensure_student_report_access(request, compilation=compilation):
            return redirect("pdfs:student-reports")
        try:
            pdf_bytes, _artifact = generate_performance_analysis_pdf(
                request=request,
                student=request.user,
                compilation=compilation,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(request=request, fallback_url="pdfs:student-reports")
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "PERFORMANCE_ANALYSIS",
                "student_id": str(request.user.id),
                "compilation_id": str(compilation.id),
            },
        )
        filename = f"NDGA-Performance-Analysis-{request.user.username}-{compilation.session.name}-{compilation.term.name}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StudentTranscriptDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def get(self, request, *args, **kwargs):
        if _student_transcript_request_allows_access(request.user) is None:
            messages.error(
                request,
                "Transcript access is available only after payment is confirmed and management releases it.",
            )
            return redirect("dashboard:student-transcript")
        try:
            pdf_bytes, _artifact = generate_transcript_pdf(
                request=request,
                student=request.user,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url="pdfs:student-reports",
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TRANSCRIPT",
                "student_id": str(request.user.id),
            },
        )
        filename = f"NDGA-Transcript-{request.user.username}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StudentSessionTranscriptDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return self.request.user.has_role(ROLE_STUDENT)

    def get(self, request, *args, **kwargs):
        if _student_transcript_request_allows_access(request.user) is None:
            messages.error(
                request,
                "Transcript access is available only after payment is confirmed and management releases it.",
            )
            return redirect("dashboard:student-transcript")
        session = get_object_or_404(AcademicSession, pk=kwargs["session_id"])
        try:
            pdf_bytes, _artifact = generate_transcript_pdf(
                request=request,
                student=request.user,
                generated_by=request.user,
                session=session,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url="pdfs:student-reports",
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TRANSCRIPT_SESSION",
                "student_id": str(request.user.id),
                "session_id": str(session.id),
            },
        )
        filename = f"NDGA-Transcript-{request.user.username}-{session.name}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StaffTermReportDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return has_any_role(self.request.user, STAFF_REPORT_DOWNLOAD_ROLES)

    def get(self, request, *args, **kwargs):
        compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term", "form_teacher"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
        )
        if not can_staff_download_term_report(user=request.user, compilation=compilation):
            messages.error(request, "You are not authorized to export this class report.")
            return redirect(resolve_role_home_url(request.user, request=request))

        student = get_object_or_404(
            User,
            pk=kwargs["student_id"],
            class_result_records__compilation=compilation,
        )
        try:
            pdf_bytes, _artifact = generate_term_report_pdf(
                request=request,
                student=student,
                compilation=compilation,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url=resolve_role_home_url(request.user, request=request),
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TERM_REPORT",
                "student_id": str(student.id),
                "compilation_id": str(compilation.id),
            },
        )
        filename = (
            f"NDGA-Term-Report-{student.username}-"
            f"{compilation.session.name}-{compilation.term.name}.pdf"
        )
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StaffPerformanceAnalysisDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return has_any_role(self.request.user, STAFF_REPORT_DOWNLOAD_ROLES)

    def get(self, request, *args, **kwargs):
        compilation = get_object_or_404(
            ClassResultCompilation.objects.select_related("academic_class", "session", "term", "form_teacher"),
            pk=kwargs["compilation_id"],
            status=ClassCompilationStatus.PUBLISHED,
        )
        if not can_staff_download_term_report(user=request.user, compilation=compilation):
            messages.error(request, "You are not authorized to export this performance analysis.")
            return redirect(resolve_role_home_url(request.user, request=request))

        student = get_object_or_404(
            User,
            pk=kwargs["student_id"],
            class_result_records__compilation=compilation,
        )
        try:
            pdf_bytes, _artifact = generate_performance_analysis_pdf(
                request=request,
                student=student,
                compilation=compilation,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url=resolve_role_home_url(request.user, request=request),
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "PERFORMANCE_ANALYSIS",
                "student_id": str(student.id),
                "compilation_id": str(compilation.id),
            },
        )
        filename = f"NDGA-Performance-Analysis-{student.username}-{compilation.session.name}-{compilation.term.name}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StaffTranscriptDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return has_any_role(self.request.user, {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL})

    def get(self, request, *args, **kwargs):
        student = get_object_or_404(User, pk=kwargs["student_id"])
        if not student.has_role(ROLE_STUDENT):
            messages.error(request, "Transcript export is available only for students.")
            return redirect(resolve_role_home_url(request.user, request=request))

        try:
            pdf_bytes, _artifact = generate_transcript_pdf(
                request=request,
                student=student,
                generated_by=request.user,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url=resolve_role_home_url(request.user, request=request),
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TRANSCRIPT",
                "student_id": str(student.id),
            },
        )
        filename = f"NDGA-Transcript-{student.username}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class StaffSessionTranscriptDownloadView(LoginRequiredMixin, UserPassesTestMixin, View):
    def test_func(self):
        return has_any_role(self.request.user, {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL})

    def get(self, request, *args, **kwargs):
        student = get_object_or_404(User, pk=kwargs["student_id"])
        session = get_object_or_404(AcademicSession, pk=kwargs["session_id"])
        if not student.has_role(ROLE_STUDENT):
            messages.error(request, "Transcript export is available only for students.")
            return redirect(resolve_role_home_url(request.user, request=request))

        try:
            pdf_bytes, _artifact = generate_transcript_pdf(
                request=request,
                student=student,
                generated_by=request.user,
                session=session,
            )
        except RuntimeError:
            return _pdf_runtime_error_response(
                request=request,
                fallback_url=resolve_role_home_url(request.user, request=request),
            )
        log_pdf_generation(
            actor=request.user,
            request=request,
            metadata={
                "document_type": "TRANSCRIPT_SESSION",
                "student_id": str(student.id),
                "session_id": str(session.id),
            },
        )
        filename = f"NDGA-Transcript-{student.username}-{session.name}.pdf"
        return _pdf_download_response(pdf_bytes=pdf_bytes, filename=filename)


class PDFVerificationView(TemplateView):
    template_name = "pdfs/verify.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        artifact = get_object_or_404(
            PDFArtifact.objects.select_related(
                "student",
                "session",
                "term",
                "compilation",
                "generated_by",
            ),
            pk=kwargs["artifact_id"],
        )
        incoming_hash = (self.request.GET.get("hash") or "").strip().lower()
        stored_hash = artifact.payload_hash.lower()
        hash_matches = bool(incoming_hash) and incoming_hash == stored_hash
        context["artifact"] = artifact
        context["incoming_hash"] = incoming_hash
        context["hash_matches"] = hash_matches
        context["verification_state"] = "VALID" if hash_matches else "CHECK_REQUIRED"
        return context
