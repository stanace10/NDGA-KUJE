from datetime import date, timedelta
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_FORM_TEACHER, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.permissions import has_any_role
from apps.academics.models import StudentClassEnrollment
from apps.attendance.forms import (
    CalendarManagementForm,
    HolidayCreateForm,
    HolidayUpdateForm,
)
from apps.attendance.models import AttendanceRecord, AttendanceStatus, Holiday, SchoolCalendar
from apps.attendance.services import (
    compute_student_attendance_percentage,
    get_form_teacher_assignments_for_current_session,
)
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event
from apps.notifications.services import notify_attendance_alert
from apps.setup_wizard.services import get_setup_state


class RoleRestrictedView(LoginRequiredMixin, UserPassesTestMixin, TemplateView):
    allowed_roles = set()

    def test_func(self):
        return has_any_role(self.request.user, self.allowed_roles)


def _pick_form_assignment(request, assignments):
    class_id_raw = (request.GET.get("class_id") or request.POST.get("class_id") or "").strip()
    if class_id_raw.isdigit():
        selected = assignments.filter(academic_class_id=int(class_id_raw)).first()
        if selected is not None:
            return selected
    return assignments.first()


class FormTeacherClassListView(RoleRestrictedView):
    template_name = "attendance/form_class_list.html"
    allowed_roles = {ROLE_FORM_TEACHER}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        setup_state = get_setup_state()
        assignments = list(
            get_form_teacher_assignments_for_current_session(self.request.user)
            .select_related("academic_class", "session")
            .order_by("academic_class__code")
        )
        context["current_session"] = setup_state.current_session
        context["current_term"] = setup_state.current_term
        context["class_rows"] = [
            {
                "assignment": assignment,
                "display_name": assignment.academic_class.display_name or assignment.academic_class.code,
                "daily_url": f"{reverse('attendance:form-mark')}?{urlencode({'class_id': assignment.academic_class_id, 'attendance_date': date.today().isoformat()})}",
                "weekly_url": f"{reverse('attendance:form-weekly')}?{urlencode({'class_id': assignment.academic_class_id, 'week_start': date.today().isoformat()})}",
            }
            for assignment in assignments
        ]
        return context


class CalendarManagementView(RoleRestrictedView):
    template_name = "attendance/calendar_manage.html"
    allowed_roles = {ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
    MODE_VIEW = "view"
    MODE_EDIT = "edit"

    def _current_mode(self):
        mode = (self.request.GET.get("mode") or self.MODE_VIEW).strip().lower()
        if mode not in {self.MODE_VIEW, self.MODE_EDIT}:
            return self.MODE_VIEW
        return mode

    def _selected_calendar(self):
        calendar_id = self.request.GET.get("calendar_id")
        queryset = SchoolCalendar.objects.select_related("session", "term")
        if calendar_id and calendar_id.isdigit():
            return queryset.filter(id=int(calendar_id)).first()
        setup_state = get_setup_state()
        if setup_state.current_term_id:
            current = queryset.filter(term=setup_state.current_term).first()
            if current:
                return current
        return queryset.first()

    def _calendar_from_post(self):
        calendar_id = self.request.POST.get("calendar_id")
        if calendar_id and calendar_id.isdigit():
            return SchoolCalendar.objects.select_related("session", "term").filter(
                id=int(calendar_id)
            ).first()
        return self._selected_calendar()

    def _edit_target_holiday(self, selected):
        if not selected:
            return None
        holiday_id = self.request.GET.get("holiday_edit_id")
        if holiday_id and holiday_id.isdigit():
            return selected.holidays.filter(id=int(holiday_id)).first()
        return None

    def _build_redirect(self, *, calendar=None, mode=None):
        params = {}
        if calendar is not None:
            params["calendar_id"] = calendar.id
        if mode:
            params["mode"] = mode
        base_url = reverse("attendance:calendar-manage")
        if not params:
            return base_url
        return f"{base_url}?{urlencode(params)}"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected = kwargs.get("selected_calendar") or self._selected_calendar()
        current_mode = kwargs.get("calendar_mode") or self._current_mode()
        is_edit_mode = current_mode == self.MODE_EDIT
        edit_target = kwargs.get("holiday_edit_target")
        if edit_target is None:
            edit_target = self._edit_target_holiday(selected)
        initial = {}
        if selected and is_edit_mode:
            initial = {
                "session": selected.session_id,
                "term": selected.term_id,
                "start_date": selected.start_date,
                "end_date": selected.end_date,
            }
        context["calendar_mode"] = current_mode
        context["is_edit_mode"] = is_edit_mode
        context["form"] = kwargs.get("form") or (
            CalendarManagementForm(initial=initial) if is_edit_mode else None
        )
        context["selected_calendar"] = selected
        context["calendars"] = SchoolCalendar.objects.select_related("session", "term").order_by(
            "-session__name", "term__name"
        )
        context["holiday_create_form"] = kwargs.get("holiday_create_form") or HolidayCreateForm(
            initial={
                "entry_mode": HolidayCreateForm.EntryMode.SINGLE,
                "start_date": selected.start_date if selected else None,
                "end_date": selected.start_date if selected else None,
                "exclude_weekends": True,
            }
        )
        context["holiday_rows"] = selected.holidays.order_by("date") if selected else []
        context["holiday_edit_target"] = edit_target
        context["holiday_edit_form"] = kwargs.get("holiday_edit_form") or (
            HolidayUpdateForm(instance=edit_target) if edit_target else None
        )
        return context

    def _extract_holiday_form(self, action):
        if action == "add-holiday":
            return HolidayCreateForm(self.request.POST)
        if action == "add-holiday-single":
            payload = self.request.POST.copy()
            payload["entry_mode"] = HolidayCreateForm.EntryMode.SINGLE
            payload["start_date"] = payload.get("holiday_date")
            payload["end_date"] = payload.get("holiday_date")
            payload.setdefault("exclude_weekends", "")
            return HolidayCreateForm(payload)
        if action == "add-holiday-range":
            payload = self.request.POST.copy()
            payload["entry_mode"] = HolidayCreateForm.EntryMode.RANGE
            payload["start_date"] = payload.get("start_date")
            payload["end_date"] = payload.get("end_date")
            return HolidayCreateForm(payload)
        return None

    def _save_holiday_form(self, *, holiday_form, selected_calendar, actor, request):
        start = holiday_form.cleaned_data["start_date"]
        end = holiday_form.cleaned_data["end_date"]
        description = holiday_form.cleaned_data["description"]
        exclude_weekends = holiday_form.cleaned_data.get("exclude_weekends", False)
        entry_mode = holiday_form.cleaned_data["entry_mode"]

        if start < selected_calendar.start_date or end > selected_calendar.end_date:
            holiday_form.add_error(
                "start_date",
                "Holiday date/range must stay within calendar start/end dates.",
            )
            return None

        saved_count = 0
        current_date = start
        while current_date <= end:
            if (
                entry_mode == HolidayCreateForm.EntryMode.RANGE
                and exclude_weekends
                and current_date.weekday() >= 5
            ):
                current_date += timedelta(days=1)
                continue
            Holiday.objects.update_or_create(
                calendar=selected_calendar,
                date=current_date,
                defaults={"description": description},
            )
            saved_count += 1
            current_date += timedelta(days=1)

        event_type = (
            "CALENDAR_HOLIDAY_RANGE_ADDED"
            if entry_mode == HolidayCreateForm.EntryMode.RANGE
            else "CALENDAR_HOLIDAY_ADDED"
        )
        log_event(
            category=AuditCategory.SYSTEM,
            event_type=event_type,
            status=AuditStatus.SUCCESS,
            actor=actor,
            request=request,
            metadata={
                "calendar_id": selected_calendar.id,
                "start_date": str(start),
                "end_date": str(end),
                "count": saved_count,
            },
        )
        return saved_count

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "save-calendar")
        selected_calendar = self._calendar_from_post()
        current_mode = self.MODE_EDIT

        if action == "save-calendar":
            form = CalendarManagementForm(request.POST)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        form=form,
                        selected_calendar=selected_calendar,
                        calendar_mode=current_mode,
                    )
                )

            with transaction.atomic():
                session = form.cleaned_data["session"]
                term = form.cleaned_data["term"]
                calendar, _ = SchoolCalendar.objects.update_or_create(
                    term=term,
                    defaults={
                        "session": session,
                        "start_date": form.cleaned_data["start_date"],
                        "end_date": form.cleaned_data["end_date"],
                    },
                )

            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CALENDAR_UPDATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"calendar_id": calendar.id},
            )
            messages.success(request, "School calendar saved successfully.")
            return redirect(self._build_redirect(calendar=calendar, mode=self.MODE_VIEW))

        if action == "delete-calendar":
            if not selected_calendar:
                messages.error(request, "Select a calendar first.")
                return redirect("attendance:calendar-manage")
            if AttendanceRecord.objects.filter(calendar=selected_calendar).exists():
                messages.error(request, "Calendar cannot be deleted after attendance has been recorded.")
                return redirect(f"{reverse('attendance:calendar-manage')}?calendar_id={selected_calendar.id}")
            removed_id = selected_calendar.id
            selected_calendar.delete()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CALENDAR_DELETED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"calendar_id": removed_id},
            )
            messages.success(request, "Calendar deleted.")
            return redirect(self._build_redirect(mode=self.MODE_VIEW))

        if action in {"add-holiday", "add-holiday-single", "add-holiday-range"}:
            if not selected_calendar:
                messages.error(
                    request,
                    "Select or create a calendar before adding holidays.",
                )
                return redirect("attendance:calendar-manage")
            holiday_form = self._extract_holiday_form(action)
            if not holiday_form or not holiday_form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_calendar=selected_calendar,
                        calendar_mode=current_mode,
                        holiday_create_form=holiday_form,
                    )
                )
            saved_count = self._save_holiday_form(
                holiday_form=holiday_form,
                selected_calendar=selected_calendar,
                actor=request.user,
                request=request,
            )
            if saved_count is None:
                return self.render_to_response(
                    self.get_context_data(
                        selected_calendar=selected_calendar,
                        calendar_mode=current_mode,
                        holiday_create_form=holiday_form,
                    )
                )
            if holiday_form.cleaned_data["entry_mode"] == HolidayCreateForm.EntryMode.RANGE:
                messages.success(request, f"{saved_count} holiday date(s) added from range.")
            else:
                messages.success(request, "Holiday date added.")
            return redirect(
                self._build_redirect(calendar=selected_calendar, mode=self.MODE_EDIT)
            )

        if action == "update-holiday":
            if not selected_calendar:
                messages.error(request, "Select a calendar first.")
                return redirect("attendance:calendar-manage")
            holiday_id = request.POST.get("holiday_id")
            if not holiday_id or not holiday_id.isdigit():
                messages.error(request, "Invalid holiday selection.")
                return redirect(
                    self._build_redirect(calendar=selected_calendar, mode=self.MODE_EDIT)
                )
            holiday = get_object_or_404(Holiday, id=int(holiday_id), calendar=selected_calendar)
            form = HolidayUpdateForm(request.POST, instance=holiday)
            if not form.is_valid():
                return self.render_to_response(
                    self.get_context_data(
                        selected_calendar=selected_calendar,
                        calendar_mode=current_mode,
                        holiday_edit_target=holiday,
                        holiday_edit_form=form,
                    )
                )
            new_date = form.cleaned_data["date"]
            if new_date < selected_calendar.start_date or new_date > selected_calendar.end_date:
                form.add_error("date", "Holiday date must be within calendar start/end.")
                return self.render_to_response(
                    self.get_context_data(
                        selected_calendar=selected_calendar,
                        calendar_mode=current_mode,
                        holiday_edit_target=holiday,
                        holiday_edit_form=form,
                    )
                )
            Holiday.objects.update_or_create(
                calendar=selected_calendar,
                date=form.cleaned_data["date"],
                defaults={"description": form.cleaned_data["description"]},
            )
            if holiday.date != form.cleaned_data["date"]:
                Holiday.objects.filter(id=holiday.id).delete()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CALENDAR_HOLIDAY_UPDATED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"calendar_id": selected_calendar.id, "holiday_id": holiday.id},
            )
            messages.success(request, "Holiday updated.")
            return redirect(
                self._build_redirect(calendar=selected_calendar, mode=self.MODE_EDIT)
            )

        if action == "delete-holiday":
            if not selected_calendar:
                messages.error(request, "Select a calendar first.")
                return redirect("attendance:calendar-manage")
            holiday_id = request.POST.get("holiday_id")
            if not holiday_id or not holiday_id.isdigit():
                messages.error(request, "Invalid holiday selection.")
                return redirect(
                    self._build_redirect(calendar=selected_calendar, mode=self.MODE_EDIT)
                )
            holiday = get_object_or_404(Holiday, id=int(holiday_id), calendar=selected_calendar)
            holiday.delete()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CALENDAR_HOLIDAY_DELETED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"calendar_id": selected_calendar.id, "holiday_id": int(holiday_id)},
            )
            messages.success(request, "Holiday removed.")
            return redirect(
                self._build_redirect(calendar=selected_calendar, mode=self.MODE_EDIT)
            )

        messages.error(request, "Invalid calendar action.")
        return redirect("attendance:calendar-manage")


class FormTeacherAttendanceView(RoleRestrictedView):
    template_name = "attendance/form_mark.html"
    allowed_roles = {ROLE_FORM_TEACHER}
    page_size = 20
    page_size_options = (10, 20, 50)

    def _setup_and_assignment(self):
        setup_state = get_setup_state()
        assignments = get_form_teacher_assignments_for_current_session(
            self.request.user
        ).select_related("academic_class", "session")
        return setup_state, assignments, _pick_form_assignment(self.request, assignments)

    def _selected_page_size(self):
        page_size_raw = self.request.GET.get("page_size") or self.request.POST.get("page_size")
        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError):
            page_size = self.page_size
        if page_size not in self.page_size_options:
            page_size = self.page_size
        return page_size

    def _selected_date(self):
        raw_date = self.request.GET.get("attendance_date") or self.request.POST.get(
            "attendance_date"
        )
        if raw_date:
            try:
                return date.fromisoformat(raw_date)
            except ValueError:
                return date.today()
        return date.today()

    def _selected_class_scope_label(self, assignment):
        if not assignment:
            return ""
        selected_class = assignment.academic_class
        arm_labels = list(
            selected_class.arm_classes.filter(is_active=True)
            .order_by("arm_name", "code")
            .values_list("display_name", flat=True)
        )
        if not arm_labels:
            return selected_class.display_name or selected_class.code
        return f"{selected_class.code} ({', '.join(arm_labels)})"

    def _build_context(self):
        setup_state, assignments, assignment = self._setup_and_assignment()
        selected_date = self._selected_date()
        selected_class = assignment.academic_class if assignment else None
        week_start = selected_date - timedelta(days=selected_date.weekday())
        context = {
            "assignments": assignments,
            "setup_state": setup_state,
            "calendar": None,
            "page_obj": None,
            "present_student_ids": set(),
            "selected_class": selected_class,
            "selected_class_id": assignment.academic_class_id if assignment else "",
            "selected_class_scope_label": self._selected_class_scope_label(assignment),
            "selected_date": selected_date,
            "week_start": week_start,
            "marking_allowed": False,
            "attendance_block_reason": "",
            "page_size": self._selected_page_size(),
            "page_size_options": self.page_size_options,
            "current_page": int((self.request.GET.get("page") or self.request.POST.get("page") or "1")),
            "weekly_url": (
                f"{reverse('attendance:form-weekly')}?"
                f"{urlencode({'class_id': assignment.academic_class_id, 'week_start': week_start.isoformat()})}"
                if assignment
                else f"{reverse('attendance:form-weekly')}?week_start={week_start.isoformat()}"
            ),
            "daily_base_url": reverse("attendance:form-mark"),
            "prev_date": selected_date - timedelta(days=1),
            "next_date": selected_date + timedelta(days=1),
        }

        if not assignment:
            messages.warning(self.request, "No active form teacher assignment found.")
            return context

        calendar = SchoolCalendar.objects.filter(
            session=assignment.session,
            term=setup_state.current_term,
        ).first()
        context["calendar"] = calendar
        if not calendar:
            messages.error(self.request, "School calendar not configured for current term.")
            return context

        if selected_date < calendar.start_date or selected_date > calendar.end_date:
            context["attendance_block_reason"] = "Selected date is outside the school calendar range."
        elif selected_date.weekday() >= 5:
            context["attendance_block_reason"] = "Attendance cannot be marked on weekends."
        elif calendar.holidays.filter(date=selected_date).exists():
            context["attendance_block_reason"] = "Attendance cannot be marked on holidays."
        else:
            context["marking_allowed"] = True

        enrollments_qs = StudentClassEnrollment.objects.select_related("student").filter(
            academic_class_id__in=assignment.academic_class.cohort_class_ids(),
            session=assignment.session,
            is_active=True,
        )
        paginator = Paginator(enrollments_qs, context["page_size"])
        page_obj = paginator.get_page(context["current_page"])
        context["page_obj"] = page_obj

        if page_obj.object_list:
            student_ids = [row.student_id for row in page_obj.object_list]
            present_ids = AttendanceRecord.objects.filter(
                calendar=calendar,
                academic_class=assignment.academic_class,
                student_id__in=student_ids,
                date=selected_date,
                status=AttendanceStatus.PRESENT,
            ).values_list("student_id", flat=True)
            context["present_student_ids"] = set(present_ids)
            for row in page_obj.object_list:
                row.term_percentage = compute_student_attendance_percentage(
                    student=row.student,
                    calendar=calendar,
                    academic_class=assignment.academic_class,
                )

        return context

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self._build_context())

    def post(self, request, *args, **kwargs):
        setup_state, _assignments, assignment = self._setup_and_assignment()
        if not assignment:
            messages.error(request, "No active form teacher assignment found.")
            return self.render_to_response(self._build_context())

        selected_date = self._selected_date()
        calendar = SchoolCalendar.objects.filter(
            session=assignment.session,
            term=setup_state.current_term,
        ).first()
        if not calendar:
            messages.error(request, "School calendar is not configured.")
            return self.render_to_response(self._build_context())

        if selected_date.weekday() >= 5:
            messages.error(request, "Attendance cannot be marked on weekends.")
            return self.render_to_response(self._build_context())
        if not calendar.is_school_day(selected_date):
            messages.error(request, "Attendance cannot be marked on the selected non-school day.")
            return self.render_to_response(self._build_context())

        visible_student_ids = [
            int(value)
            for value in request.POST.getlist("visible_student_ids")
            if value.isdigit()
        ]
        present_student_ids = {
            int(value)
            for value in request.POST.getlist("present_student_ids")
            if value.isdigit()
        }

        with transaction.atomic():
            for student_id in visible_student_ids:
                status = (
                    AttendanceStatus.PRESENT
                    if student_id in present_student_ids
                    else AttendanceStatus.ABSENT
                )
                existing_record = AttendanceRecord.objects.filter(
                    calendar=calendar,
                    academic_class=assignment.academic_class,
                    student_id=student_id,
                    date=selected_date,
                ).select_related("student", "student__student_profile").first()
                record, _ = AttendanceRecord.objects.update_or_create(
                    calendar=calendar,
                    academic_class=assignment.academic_class,
                    student_id=student_id,
                    date=selected_date,
                    defaults={"status": status, "marked_by": request.user},
                )
                was_absent = existing_record and existing_record.status == AttendanceStatus.ABSENT
                if status == AttendanceStatus.ABSENT and not was_absent:
                    notify_attendance_alert(
                        student=record.student,
                        attendance_date=selected_date,
                        status=status,
                        actor=request.user,
                        request=request,
                        academic_class=assignment.academic_class,
                    )

        log_event(
            category=AuditCategory.SYSTEM,
            event_type="ATTENDANCE_MARKED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "class_id": assignment.academic_class_id,
                "date": str(selected_date),
                "students_updated": len(visible_student_ids),
            },
        )
        messages.success(request, "Attendance saved successfully.")
        page_size = self._selected_page_size()
        return redirect(
            f"{reverse('attendance:form-mark')}?class_id={assignment.academic_class_id}"
            f"&attendance_date={selected_date}"
            f"&page={request.POST.get('page', 1)}&page_size={page_size}"
        )


class FormTeacherWeeklyAttendanceView(RoleRestrictedView):
    template_name = "attendance/form_mark_weekly.html"
    allowed_roles = {ROLE_FORM_TEACHER}
    page_size = 20
    page_size_options = (10, 20, 50)

    def _setup_and_assignment(self):
        setup_state = get_setup_state()
        assignments = get_form_teacher_assignments_for_current_session(
            self.request.user
        ).select_related("academic_class", "session")
        return setup_state, _pick_form_assignment(self.request, assignments)

    def _selected_page_size(self):
        page_size_raw = self.request.GET.get("page_size") or self.request.POST.get("page_size")
        try:
            page_size = int(page_size_raw)
        except (TypeError, ValueError):
            page_size = self.page_size
        if page_size not in self.page_size_options:
            page_size = self.page_size
        return page_size

    def _week_start(self):
        raw = self.request.GET.get("week_start") or self.request.POST.get("week_start")
        if raw:
            try:
                selected = date.fromisoformat(raw)
            except ValueError:
                selected = date.today()
        else:
            selected = date.today()
        return selected - timedelta(days=selected.weekday())

    def _selected_class_scope_label(self, assignment):
        if not assignment:
            return ""
        selected_class = assignment.academic_class
        arm_labels = list(
            selected_class.arm_classes.filter(is_active=True)
            .order_by("arm_name", "code")
            .values_list("display_name", flat=True)
        )
        if not arm_labels:
            return selected_class.display_name or selected_class.code
        return f"{selected_class.code} ({', '.join(arm_labels)})"

    def _week_days(self, *, week_start, calendar):
        holidays = set(calendar.holidays.values_list("date", flat=True))
        rows = []
        for index in range(5):
            row_date = week_start + timedelta(days=index)
            in_range = calendar.start_date <= row_date <= calendar.end_date
            is_holiday = row_date in holidays
            selectable = in_range and not is_holiday
            rows.append(
                {
                    "date": row_date,
                    "token": row_date.strftime("%Y%m%d"),
                    "in_range": in_range,
                    "is_holiday": is_holiday,
                    "selectable": selectable,
                }
            )
        return rows

    def _build_context(self):
        setup_state, assignment = self._setup_and_assignment()
        week_start = self._week_start()
        context = {
            "assignment": assignment,
            "calendar": None,
            "page_obj": None,
            "week_days": [],
            "selected_class_id": assignment.academic_class_id if assignment else "",
            "selected_class_scope_label": self._selected_class_scope_label(assignment),
            "week_start": week_start,
            "prev_week": week_start - timedelta(days=7),
            "next_week": week_start + timedelta(days=7),
            "page_size": self._selected_page_size(),
            "page_size_options": self.page_size_options,
            "current_page": int((self.request.GET.get("page") or self.request.POST.get("page") or "1")),
            "daily_url": (
                f"{reverse('attendance:form-mark')}?"
                f"{urlencode({'class_id': assignment.academic_class_id, 'attendance_date': date.today().isoformat()})}"
                if assignment
                else f"{reverse('attendance:form-mark')}?attendance_date={date.today().isoformat()}"
            ),
            "attendance_block_reason": "",
        }
        if not assignment:
            messages.warning(self.request, "No active form teacher assignment found.")
            return context

        calendar = SchoolCalendar.objects.filter(
            session=assignment.session,
            term=setup_state.current_term,
        ).first()
        context["calendar"] = calendar
        if not calendar:
            context["attendance_block_reason"] = "School calendar not configured for current term."
            return context

        week_days = self._week_days(week_start=week_start, calendar=calendar)
        context["week_days"] = week_days

        enrollments_qs = StudentClassEnrollment.objects.select_related("student").filter(
            academic_class_id__in=assignment.academic_class.cohort_class_ids(),
            session=assignment.session,
            is_active=True,
        )
        paginator = Paginator(enrollments_qs, context["page_size"])
        page_obj = paginator.get_page(context["current_page"])
        context["page_obj"] = page_obj

        if page_obj.object_list and week_days:
            student_ids = [row.student_id for row in page_obj.object_list]
            date_rows = [row["date"] for row in week_days if row["in_range"]]
            present_rows = set(
                AttendanceRecord.objects.filter(
                    calendar=calendar,
                    academic_class=assignment.academic_class,
                    student_id__in=student_ids,
                    date__in=date_rows,
                    status=AttendanceStatus.PRESENT,
                ).values_list("student_id", "date")
            )
            for enrollment in page_obj.object_list:
                enrollment.week_presence_tokens = {
                    row["token"]
                    for row in week_days
                    if (enrollment.student_id, row["date"]) in present_rows
                }
                enrollment.term_percentage = compute_student_attendance_percentage(
                    student=enrollment.student,
                    calendar=calendar,
                    academic_class=assignment.academic_class,
                )
        return context

    def get(self, request, *args, **kwargs):
        return self.render_to_response(self._build_context())

    def post(self, request, *args, **kwargs):
        setup_state, assignment = self._setup_and_assignment()
        if not assignment:
            messages.error(request, "No active form teacher assignment found.")
            return self.render_to_response(self._build_context())

        calendar = SchoolCalendar.objects.filter(
            session=assignment.session,
            term=setup_state.current_term,
        ).first()
        if not calendar:
            messages.error(request, "School calendar is not configured.")
            return self.render_to_response(self._build_context())

        week_start = self._week_start()
        week_days = self._week_days(week_start=week_start, calendar=calendar)
        visible_student_ids = [
            int(value)
            for value in request.POST.getlist("visible_student_ids")
            if value.isdigit()
        ]
        updates = 0
        with transaction.atomic():
            for student_id in visible_student_ids:
                for row in week_days:
                    if not row["selectable"]:
                        continue
                    checked = bool(
                        request.POST.get(f"present_{student_id}_{row['token']}")
                    )
                    status = (
                        AttendanceStatus.PRESENT if checked else AttendanceStatus.ABSENT
                    )
                    existing_record = AttendanceRecord.objects.filter(
                        calendar=calendar,
                        academic_class=assignment.academic_class,
                        student_id=student_id,
                        date=row["date"],
                    ).select_related("student", "student__student_profile").first()
                    record, _ = AttendanceRecord.objects.update_or_create(
                        calendar=calendar,
                        academic_class=assignment.academic_class,
                        student_id=student_id,
                        date=row["date"],
                        defaults={"status": status, "marked_by": request.user},
                    )
                    was_absent = existing_record and existing_record.status == AttendanceStatus.ABSENT
                    if status == AttendanceStatus.ABSENT and not was_absent:
                        notify_attendance_alert(
                            student=record.student,
                            attendance_date=row["date"],
                            status=status,
                            actor=request.user,
                            request=request,
                            academic_class=assignment.academic_class,
                        )
                    updates += 1

        log_event(
            category=AuditCategory.SYSTEM,
            event_type="ATTENDANCE_WEEKLY_MARKED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={
                "class_id": assignment.academic_class_id,
                "week_start": str(week_start),
                "records_updated": updates,
            },
        )
        messages.success(request, "Weekly attendance saved successfully.")
        page_size = self._selected_page_size()
        return redirect(
            f"{reverse('attendance:form-weekly')}?class_id={assignment.academic_class_id}"
            f"&week_start={week_start.isoformat()}"
            f"&page={request.POST.get('page', 1)}&page_size={page_size}"
        )
