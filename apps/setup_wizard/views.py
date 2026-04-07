import csv
from io import StringIO

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.db import models
from django.http import HttpResponse
from django.shortcuts import redirect
from django.urls import reverse
from django.utils import timezone
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.models import User
from apps.academics.models import AcademicSession, Term
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event
from apps.elections.models import Election, Vote
from apps.finance.models import Expense, Payment, SalaryRecord, StudentCharge
from apps.pdfs.services import render_pdf_bytes
from apps.setup_wizard.forms import (
    CalendarSetupForm,
    ClassSetupForm,
    ClassSubjectMappingForm,
    EndSessionProgressForm,
    EndTermProgressForm,
    GradeScaleDefaultsForm,
    SessionSetupForm,
    SessionTermContextForm,
    SetupFinalizeForm,
    SubjectSetupForm,
    TermSetupForm,
)
from apps.setup_wizard.models import SetupStateCode
from apps.setup_wizard.services import (
    WIZARD_STEPS,
    TERM_SEQUENCE,
    advance_current_term,
    can_access_step,
    configure_calendar,
    configure_classes,
    configure_class_subject_mappings,
    configure_grade_scale,
    end_current_session,
    configure_session,
    configure_subjects,
    configure_term,
    current_wizard_step,
    finalize_setup,
    get_setup_state,
    preview_session_promotion,
    set_current_session_term,
)
from apps.setup_wizard.backup_services import create_local_backup_archive
from apps.academics.models import AcademicClass, ClassSubject, Subject
from apps.attendance.models import SchoolCalendar
from apps.sync.models import SyncQueue, SyncQueueStatus


STEP_TITLES = {
    "session": "Create Session",
    "term": "Choose Current Term",
    "calendar": "Configure Attendance Calendar",
    "classes": "Create Classes",
    "subjects": "Create Subjects",
    "class-subjects": "Map Subjects To Classes",
    "grade-scale": "Grade Scale Defaults",
    "finalize": "Finalize Setup",
}


class SetupWizardView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "setup_wizard/wizard.html"

    def test_func(self):
        return self.request.user.has_role(ROLE_IT_MANAGER)

    def dispatch(self, request, *args, **kwargs):
        self.setup_state = get_setup_state()
        if self.setup_state.is_ready and "step" not in kwargs:
            return redirect("dashboard:it-portal")
        requested_step = kwargs.get("step") or current_wizard_step(self.setup_state)
        if requested_step not in WIZARD_STEPS:
            requested_step = current_wizard_step(self.setup_state)
        if not can_access_step(requested_step, self.setup_state):
            return redirect("setup_wizard:wizard-step", step=current_wizard_step(self.setup_state))
        self.step = requested_step
        return super().dispatch(request, *args, **kwargs)

    def get_form_class(self):
        return {
            "session": SessionSetupForm,
            "term": TermSetupForm,
            "calendar": CalendarSetupForm,
            "classes": ClassSetupForm,
            "subjects": SubjectSetupForm,
            "class-subjects": ClassSubjectMappingForm,
            "grade-scale": GradeScaleDefaultsForm,
            "finalize": SetupFinalizeForm,
        }[self.step]

    def get_form(self):
        form_class = self.get_form_class()
        form_kwargs = {"initial": self._initial_data()}
        if self.step == "term":
            form_kwargs["session"] = self.setup_state.current_session
        if self.step == "class-subjects":
            form_kwargs["classes"] = AcademicClass.objects.filter(is_active=True).order_by("code")
            form_kwargs["subjects"] = Subject.objects.filter(is_active=True).order_by("name")
        return form_class(self.request.POST or None, **form_kwargs)

    def _initial_data(self):
        if self.step == "session" and self.setup_state.current_session:
            return {"session_name": self.setup_state.current_session.name}
        if self.step == "term" and self.setup_state.current_term:
            return {"term_name": self.setup_state.current_term.name}
        if self.step == "calendar" and self.setup_state.current_term_id:
            calendar = SchoolCalendar.objects.filter(term=self.setup_state.current_term).first()
            if calendar:
                holiday_lines = "\n".join(
                    f"{holiday.date}|{holiday.description}" for holiday in calendar.holidays.all()
                )
                return {
                    "start_date": calendar.start_date,
                    "end_date": calendar.end_date,
                    "holidays": holiday_lines,
                }
        if self.step == "class-subjects":
            classes = list(AcademicClass.objects.filter(is_active=True).order_by("code"))
            query_class_id = self.request.GET.get("class_id")
            if query_class_id and query_class_id.isdigit():
                return {"academic_class": int(query_class_id)}
            if classes:
                return {"academic_class": classes[0].id}
        return {}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "setup_state": self.setup_state,
                "setup_state_code": self.setup_state.state,
                "current_step": self.step,
                "step_title": STEP_TITLES[self.step],
                "wizard_steps": WIZARD_STEPS,
                "wizard_step_items": [(step, STEP_TITLES.get(step, step.title())) for step in WIZARD_STEPS],
                "form": kwargs.get("form") or self.get_form(),
            }
        )
        if self.step == "class-subjects":
            class_rows = list(AcademicClass.objects.filter(is_active=True).order_by("code"))
            counts = {
                row["academic_class_id"]: row["total"]
                for row in ClassSubject.objects.filter(is_active=True)
                .values("academic_class_id")
                .annotate(total=models.Count("id"))
            }
            selected_class = context["form"].data.get("academic_class") if context["form"].is_bound else context["form"].initial.get("academic_class")
            context["selected_class_id"] = int(selected_class) if str(selected_class).isdigit() else None
            context["class_subject_summary"] = [
                {
                    "class_id": row.id,
                    "class_code": row.code,
                    "subject_count": counts.get(row.id, 0),
                }
                for row in class_rows
            ]
        return context

    def post(self, request, *args, **kwargs):
        form = self.get_form()
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))

        try:
            next_step = self._handle_step(form)
        except ValueError as exc:
            form.add_error(None, str(exc))
            return self.render_to_response(self.get_context_data(form=form))

        messages.success(request, f"{STEP_TITLES[self.step]} completed.")
        if self.step == "class-subjects" and not request.POST.get("continue_next"):
            selected_class = form.cleaned_data.get("academic_class")
            next_class_id = self._next_active_class_id(selected_class.id if selected_class else None)
            params = f"?class_id={next_class_id}" if next_class_id else ""
            return redirect(f"{reverse('setup_wizard:wizard-step', kwargs={'step': 'class-subjects'})}{params}")
        if self.step == "finalize":
            return redirect("dashboard:it-portal")
        return redirect("setup_wizard:wizard-step", step=next_step)

    def _next_active_class_id(self, current_class_id):
        classes = list(AcademicClass.objects.filter(is_active=True).order_by("code").values_list("id", flat=True))
        if not classes:
            return None
        if current_class_id not in classes:
            return classes[0]
        index = classes.index(current_class_id)
        if index + 1 < len(classes):
            return classes[index + 1]
        return classes[0]

    def _handle_step(self, form):
        actor = self.request.user
        if self.step == "session":
            setup_state = configure_session(actor=actor, session_name=form.cleaned_data["session_name"])
            next_step = current_wizard_step(setup_state)
        elif self.step == "term":
            setup_state = configure_term(actor=actor, term_name=form.cleaned_data["term_name"])
            next_step = current_wizard_step(setup_state)
        elif self.step == "calendar":
            setup_state = configure_calendar(
                actor=actor,
                start_date=form.cleaned_data["start_date"],
                end_date=form.cleaned_data["end_date"],
                holidays=form.cleaned_data["parsed_holidays"],
            )
            next_step = current_wizard_step(setup_state)
        elif self.step == "classes":
            setup_state = configure_classes(actor=actor, class_codes=form.cleaned_data["class_codes"])
            next_step = current_wizard_step(setup_state)
        elif self.step == "subjects":
            setup_state = configure_subjects(actor=actor, subjects=form.cleaned_data["subjects"])
            next_step = current_wizard_step(setup_state)
        elif self.step == "class-subjects":
            setup_state = configure_class_subject_mappings(
                actor=actor,
                class_subject_map=form.cleaned_data["class_subject_map"],
            )
            next_step = current_wizard_step(setup_state)
        elif self.step == "grade-scale":
            setup_state = configure_grade_scale(
                actor=actor,
                apply_defaults=form.cleaned_data.get("apply_defaults", False),
                grade_ranges=form.cleaned_data.get("grade_ranges", {}),
            )
            next_step = current_wizard_step(setup_state)
        else:
            setup_state = finalize_setup(actor=actor)
            next_step = "finalize" if setup_state.state == SetupStateCode.IT_READY else current_wizard_step(setup_state)

        log_event(
            category=AuditCategory.SYSTEM,
            event_type="SETUP_WIZARD_STEP_COMPLETED",
            status=AuditStatus.SUCCESS,
            actor=actor,
            request=self.request,
            message=f"Completed wizard step: {self.step}",
            metadata={"step": self.step, "next_step": next_step},
        )
        return next_step


class SessionTermManagementView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "setup_wizard/session_term_manage.html"

    def test_func(self):
        user = self.request.user
        return any(
            [
                user.has_role(ROLE_IT_MANAGER),
                user.has_role(ROLE_VP),
                user.has_role(ROLE_PRINCIPAL),
                user.has_role(ROLE_BURSAR),
            ]
        )

    def dispatch(self, request, *args, **kwargs):
        setup_state = get_setup_state()
        if not setup_state.is_ready:
            messages.info(request, "Complete setup wizard before using session/term controls.")
            return redirect("setup_wizard:wizard")
        return super().dispatch(request, *args, **kwargs)

    def _context_form(self, data=None):
        setup_state = get_setup_state()
        initial = {}
        if setup_state.current_session_id:
            initial["session"] = setup_state.current_session_id
        if setup_state.current_term_id:
            initial["term"] = setup_state.current_term_id
        return SessionTermContextForm(data=data, initial=initial)

    def _end_term_form(self, data=None):
        return EndTermProgressForm(data=data)

    def _end_session_form(self, data=None):
        return EndSessionProgressForm(data=data)

    def _term_status_rows(self):
        setup_state = get_setup_state()
        current_term_code = setup_state.current_term.name if setup_state.current_term_id else None
        status_rows = []
        if not setup_state.current_session_id:
            return status_rows
        label_map = {
            "FIRST": "First Term",
            "SECOND": "Second Term",
            "THIRD": "Third Term",
        }
        current_index = TERM_SEQUENCE.index(current_term_code) if current_term_code else -1
        for index, term_name in enumerate(TERM_SEQUENCE):
            if current_index < 0:
                status = "pending"
            else:
                if index < current_index:
                    status = "completed"
                elif index == current_index:
                    status = "current"
                else:
                    status = "pending"
            status_rows.append(
                {
                    "code": term_name,
                    "display": label_map.get(term_name, term_name),
                    "status": status,
                }
            )
        return status_rows

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        setup_state = get_setup_state()
        can_progress = self.request.user.has_role(ROLE_IT_MANAGER)
        context["setup_state"] = setup_state
        context["can_progress_academic_cycle"] = can_progress
        context["context_form"] = kwargs.get("context_form") or self._context_form()
        context["end_term_form"] = kwargs.get("end_term_form") or self._end_term_form()
        context["end_session_form"] = kwargs.get("end_session_form") or self._end_session_form()
        context["term_status_rows"] = self._term_status_rows()
        if setup_state.current_session_id:
            context["promotion_preview"] = preview_session_promotion(session=setup_state.current_session)
        else:
            context["promotion_preview"] = None
        return context

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action")
        is_it_manager = request.user.has_role(ROLE_IT_MANAGER)
        if action == "set-context":
            context_form = self._context_form(data=request.POST)
            end_term_form = self._end_term_form()
            end_session_form = self._end_session_form()
            if not context_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )
            try:
                set_current_session_term(
                    actor=request.user,
                    session=context_form.cleaned_data["session"],
                    term=context_form.cleaned_data["term"],
                )
            except ValueError as exc:
                context_form.add_error(None, str(exc))
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CURRENT_SESSION_TERM_CHANGED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "session": context_form.cleaned_data["session"].name,
                    "term": context_form.cleaned_data["term"].name,
                },
            )
            messages.success(request, "Current session and term updated.")
            return redirect("setup_wizard:session-term-manage")

        if action == "end-term":
            if not is_it_manager:
                messages.error(request, "Only IT Manager can end the active term.")
                return redirect("setup_wizard:session-term-manage")
            end_term_form = self._end_term_form(data=request.POST)
            context_form = self._context_form()
            end_session_form = self._end_session_form()
            if not end_term_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )
            try:
                advance_result = advance_current_term(actor=request.user)
            except ValueError as exc:
                end_term_form.add_error(None, str(exc))
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="TERM_ADVANCED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "previous_session": advance_result.previous_session_name,
                    "previous_term": advance_result.previous_term_name,
                    "new_session": advance_result.current_session_name,
                    "new_term": advance_result.current_term_name,
                    "session_changed": advance_result.session_changed,
                },
            )
            if advance_result.session_changed:
                messages.success(
                    request,
                    f"Session advanced to {advance_result.current_session_name} and set to {advance_result.current_term_name}.",
                )
            else:
                messages.success(
                    request,
                    f"Current term advanced to {advance_result.current_term_name}.",
            )
            return redirect("setup_wizard:session-term-manage")

        if action == "end-session":
            if not is_it_manager:
                messages.error(request, "Only IT Manager can close an academic session.")
                return redirect("setup_wizard:session-term-manage")
            end_session_form = self._end_session_form(data=request.POST)
            context_form = self._context_form()
            end_term_form = self._end_term_form()
            if not end_session_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )
            try:
                result = end_current_session(actor=request.user)
            except ValueError as exc:
                end_session_form.add_error(None, str(exc))
                return self.render_to_response(
                    self.get_context_data(
                        context_form=context_form,
                        end_term_form=end_term_form,
                        end_session_form=end_session_form,
                    )
                )

            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SESSION_CLOSED_AND_PROMOTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={
                    "closed_session": result.closed_session_name,
                    "opened_session": result.opened_session_name,
                    "opened_term": result.opened_term_name,
                    "promoted_count": result.promoted_count,
                    "retained_count": result.retained_count,
                    "graduated_count": result.graduated_count,
                    "transcript_snapshot_count": result.transcript_snapshot_count,
                },
            )
            messages.success(
                request,
                (
                    f"Session {result.closed_session_name} closed. Opened "
                    f"{result.opened_session_name} ({result.opened_term_name}). "
                    f"Promoted: {result.promoted_count}, Retained: {result.retained_count}, "
                    f"Graduated: {result.graduated_count}."
                ),
            )
            return redirect("setup_wizard:session-term-manage")

        messages.error(request, "Invalid session/term action.")
        return redirect("setup_wizard:session-term-manage")


class BackupCenterView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    template_name = "setup_wizard/backup_center.html"

    def test_func(self):
        return self.request.user.has_role(ROLE_IT_MANAGER)

    def dispatch(self, request, *args, **kwargs):
        setup_state = get_setup_state()
        if not setup_state.is_ready:
            messages.info(request, "Complete setup wizard before running backups.")
            return redirect("setup_wizard:wizard")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["setup_state"] = get_setup_state()
        context["summary_rows"] = self._summary_rows()
        context["example_backup_command"] = (
            ".venv\\Scripts\\python.exe manage.py backup_ndga --output-dir backups"
        )
        context["example_restore_command"] = (
            ".venv\\Scripts\\python.exe manage.py restore_ndga backups\\ndga_backup_YYYYMMDD_HHMMSS.zip"
        )
        context["safe_bundle_backup_command"] = (
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\backup_lan_recovery_bundle.ps1"
        )
        context["safe_bundle_restore_command"] = (
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\restore_lan_recovery_bundle.ps1 "
            "-BundlePath \"C:\\Users\\<you>\\OneDrive\\NDGA Backups\\lan-node\\YYYYMMDD_HHMMSS\""
        )
        context["safe_bundle_schedule_command"] = (
            "powershell -ExecutionPolicy Bypass -File .\\scripts\\install_lan_backup_task.ps1"
        )
        return context

    def _summary_rows(self):
        setup_state = get_setup_state()
        pending_sync = SyncQueue.objects.filter(
            status__in=[SyncQueueStatus.PENDING, SyncQueueStatus.RETRY]
        ).count()
        class_levels_total = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).count()
        class_list_total = AcademicClass.objects.filter(is_active=True, base_class__isnull=False).count()
        if not class_list_total:
            class_list_total = class_levels_total
        return [
            {"metric": "Generated At", "value": timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")},
            {"metric": "Setup State", "value": setup_state.state},
            {
                "metric": "Current Session",
                "value": setup_state.current_session.name if setup_state.current_session_id else "-",
            },
            {
                "metric": "Current Term",
                "value": (
                    setup_state.current_term.get_name_display()
                    if setup_state.current_term_id
                    else "-"
                ),
            },
            {"metric": "Academic Sessions", "value": AcademicSession.objects.count()},
            {"metric": "Terms", "value": Term.objects.count()},
            {"metric": "Class Levels", "value": class_levels_total},
            {"metric": "Class List", "value": class_list_total},
            {"metric": "Subjects", "value": Subject.objects.count()},
            {"metric": "Users", "value": User.objects.count()},
            {"metric": "Charges", "value": StudentCharge.objects.count()},
            {"metric": "Payments", "value": Payment.objects.count()},
            {"metric": "Expenses", "value": Expense.objects.count()},
            {"metric": "Salary Records", "value": SalaryRecord.objects.count()},
            {"metric": "Elections", "value": Election.objects.count()},
            {"metric": "Votes", "value": Vote.objects.count()},
            {"metric": "Pending Manual Push Queue", "value": pending_sync},
        ]

    def _export_summary_csv(self):
        rows = self._summary_rows()
        buffer = StringIO()
        writer = csv.writer(buffer)
        writer.writerow(["Metric", "Value"])
        for row in rows:
            writer.writerow([row["metric"], row["value"]])
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(buffer.getvalue(), content_type="text/csv")
        response["Content-Disposition"] = f'attachment; filename="ndga_backup_summary_{stamp}.csv"'
        return response

    def _export_summary_pdf(self):
        rows = self._summary_rows()
        context = {
            "generated_at": timezone.localtime(),
            "summary_rows": rows,
            "ndga_name": "Notre Dame Girls Academy",
        }
        pdf_bytes = render_pdf_bytes(
            template_name="setup_wizard/backup_summary_pdf.html",
            context=context,
        )
        stamp = timezone.localtime().strftime("%Y%m%d_%H%M%S")
        response = HttpResponse(pdf_bytes, content_type="application/pdf")
        response["Content-Disposition"] = f'attachment; filename="ndga_backup_summary_{stamp}.pdf"'
        return response

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "backup-summary-csv":
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="LOCAL_BACKUP_SUMMARY_CSV_EXPORTED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
            )
            return self._export_summary_csv()

        if action == "backup-summary-pdf":
            try:
                log_event(
                    category=AuditCategory.SYSTEM,
                    event_type="LOCAL_BACKUP_SUMMARY_PDF_EXPORTED",
                    status=AuditStatus.SUCCESS,
                    actor=request.user,
                    request=request,
                )
                return self._export_summary_pdf()
            except Exception as exc:
                messages.error(
                    request,
                    (
                        "Summary PDF export failed. "
                        f"{exc}"
                    ),
                )
                return redirect("setup_wizard:backup-center")

        if action != "backup-now":
            messages.error(request, "Invalid backup action.")
            return redirect("setup_wizard:backup-center")
        try:
            payload = create_local_backup_archive(actor=request.user)
        except Exception as exc:
            messages.error(request, f"Backup failed: {exc}")
            return redirect("setup_wizard:backup-center")

        log_event(
            category=AuditCategory.SYSTEM,
            event_type="LOCAL_BACKUP_CREATED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "filename": payload.filename,
                "media_file_count": payload.media_file_count,
                "setup_state": payload.metadata.get("setup_state", ""),
            },
        )
        response = HttpResponse(payload.archive_bytes, content_type="application/zip")
        response["Content-Disposition"] = f'attachment; filename="{payload.filename}"'
        return response
