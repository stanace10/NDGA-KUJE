from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin, UserPassesTestMixin
from django.core.paginator import Paginator
from django.db import models
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import RedirectView, TemplateView, UpdateView

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.academics.forms import (
    AcademicClassForm,
    ClassSubjectBulkMappingForm,
    ClassSubjectForm,
    FormTeacherAssignmentForm,
    SubjectForm,
    TeacherSubjectAssignmentForm,
    TimetableGeneratorForm,
)
from apps.academics.models import (
    AcademicClass,
    Campus,
    ClassSubject,
    FormTeacherAssignment,
    Subject,
    TeacherSubjectAssignment,
)
from apps.audit.models import AuditCategory, AuditStatus
from apps.audit.services import log_event
from apps.academics.timetable import generate_timetable_preview


class ITManagerRequiredMixin(LoginRequiredMixin, UserPassesTestMixin):
    PAGE_SIZE_OPTIONS = (4, 8, 12, 25, 50)

    def test_func(self):
        return self.request.user.has_role(ROLE_IT_MANAGER)

    def _resolve_page_size(self, raw_value):
        value = (raw_value or "").strip().lower()
        if value == "all":
            return "all"
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return self.PAGE_SIZE_OPTIONS[0]
        if parsed in self.PAGE_SIZE_OPTIONS:
            return parsed
        return self.PAGE_SIZE_OPTIONS[0]

    def _paginate_queryset(self, queryset, *, page_param="page", page_size_param="page_size"):
        page_size = self._resolve_page_size(self.request.GET.get(page_size_param))
        if page_size == "all":
            return {
                "rows": list(queryset),
                "page_obj": None,
                "page_size": "all",
                "page_size_options": self.PAGE_SIZE_OPTIONS,
            }
        paginator = Paginator(queryset, page_size)
        page_obj = paginator.get_page(self.request.GET.get(page_param) or 1)
        return {
            "rows": list(page_obj.object_list),
            "page_obj": page_obj,
            "page_size": page_size,
            "page_size_options": self.PAGE_SIZE_OPTIONS,
        }

    def _query_string_without(self, *keys):
        query = self.request.GET.copy()
        for key in keys:
            if key in query:
                query.pop(key)
        return query.urlencode()


class ITAcademicHubView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_hub.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["counts"] = {
            "campuses": Campus.objects.count(),
            "classes": AcademicClass.objects.count(),
            "subjects": Subject.objects.count(),
            "class_subjects": ClassSubject.objects.count(),
            "subject_assignments": TeacherSubjectAssignment.objects.filter(is_active=True).count(),
            "form_assignments": FormTeacherAssignment.objects.filter(is_active=True).count(),
        }
        return context


class ITTimetableGeneratorView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_timetable_generator.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or TimetableGeneratorForm()
        context["preview"] = kwargs.get("preview")
        context["assignment_count"] = kwargs.get("assignment_count", 0)
        return context

    def post(self, request, *args, **kwargs):
        form = TimetableGeneratorForm(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(form=form))
        assignments = list(
            TeacherSubjectAssignment.objects.filter(
                session=form.cleaned_data["session"],
                term=form.cleaned_data["term"],
                is_active=True,
            )
            .select_related("teacher", "subject", "academic_class")
            .order_by("academic_class__code", "subject__name", "teacher__username")
        )
        preview = generate_timetable_preview(
            assignments=assignments,
            days=form.cleaned_data["days"],
            periods_per_day=form.cleaned_data["periods_per_day"],
            periods_per_assignment=form.cleaned_data["periods_per_assignment"],
            room_prefix=(form.cleaned_data.get("room_prefix") or "Room").strip() or "Room",
        )
        return self.render_to_response(
            self.get_context_data(
                form=form,
                preview=preview,
                assignment_count=len(assignments),
            )
        )


class ITClassListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_classes.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or AcademicClassForm()
        paginated = self._paginate_queryset(AcademicClass.objects.select_related("campus").order_by("code"))
        context["classes"] = paginated["rows"]
        context["classes_page_obj"] = paginated["page_obj"]
        context["classes_page_size"] = paginated["page_size"]
        context["classes_page_size_options"] = paginated["page_size_options"]
        context["classes_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = AcademicClassForm(request.POST)
        if form.is_valid():
            item = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="ACADEMIC_CLASS_SAVED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"id": item.id, "code": item.code},
            )
            messages.success(request, "Class saved successfully.")
            return redirect("academics:it-classes")
        return self.render_to_response(self.get_context_data(form=form))


class ITClassUpdateView(ITManagerRequiredMixin, UpdateView):
    model = AcademicClass
    form_class = AcademicClassForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-classes")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit Class: {self.object.code}"
        context["back_url"] = reverse("academics:it-classes")
        return context


class ITSubjectListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_subjects.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or SubjectForm()
        paginated = self._paginate_queryset(Subject.objects.order_by("name"))
        context["subjects"] = paginated["rows"]
        context["subjects_page_obj"] = paginated["page_obj"]
        context["subjects_page_size"] = paginated["page_size"]
        context["subjects_page_size_options"] = paginated["page_size_options"]
        context["subjects_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = SubjectForm(request.POST)
        if form.is_valid():
            item = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SUBJECT_SAVED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"id": item.id, "name": item.name},
            )
            messages.success(request, "Subject saved successfully.")
            return redirect("academics:it-subjects")
        return self.render_to_response(self.get_context_data(form=form))


class ITSubjectUpdateView(ITManagerRequiredMixin, UpdateView):
    model = Subject
    form_class = SubjectForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-subjects")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = f"Edit Subject: {self.object.name}"
        context["back_url"] = reverse("academics:it-subjects")
        return context


class ITClassSubjectListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_class_subjects.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        initial = kwargs.get("initial") or {}
        if not initial.get("academic_class"):
            initial["academic_class"] = self.request.GET.get("class_id")
        context["form"] = kwargs.get("form") or ClassSubjectBulkMappingForm(initial=initial)
        class_rows = list(AcademicClass.objects.filter(is_active=True).order_by("code"))
        context["mapping_counts"] = {
            row["academic_class_id"]: row["total"]
            for row in ClassSubject.objects.filter(is_active=True)
            .values("academic_class_id")
            .annotate(total=models.Count("id"))
        }
        context["class_summaries"] = [
            {
                "academic_class": row,
                "subject_count": context["mapping_counts"].get(row.id, 0),
            }
            for row in class_rows
        ]
        context["mapped_subjects"] = (
            ClassSubject.objects.select_related("academic_class", "subject")
            .order_by("-is_active", "academic_class__code", "subject__name")
        )
        mapped_paginated = self._paginate_queryset(context["mapped_subjects"])
        context["mapped_subjects"] = mapped_paginated["rows"]
        context["mapped_subjects_page_obj"] = mapped_paginated["page_obj"]
        context["mapped_subjects_page_size"] = mapped_paginated["page_size"]
        context["mapped_subjects_page_size_options"] = mapped_paginated["page_size_options"]
        context["mapped_subjects_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = ClassSubjectBulkMappingForm(request.POST)
        if form.is_valid():
            academic_class = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CLASS_SUBJECT_MAPPED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"class_id": academic_class.id, "class_code": academic_class.code},
            )
            messages.success(request, f"Subject mapping updated for {academic_class.code}.")
            return redirect(f"{reverse('academics:it-class-subjects')}?class_id={academic_class.id}")
        return self.render_to_response(self.get_context_data(form=form, initial={"academic_class": request.POST.get("academic_class")}))


class ITClassSubjectUpdateView(ITManagerRequiredMixin, UpdateView):
    model = ClassSubject
    form_class = ClassSubjectForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-class-subjects")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Class-Subject Mapping"
        context["back_url"] = reverse("academics:it-class-subjects")
        return context


class ITTeacherSubjectAssignmentListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_teacher_subject_assignments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or TeacherSubjectAssignmentForm()
        assignment_qs = TeacherSubjectAssignment.objects.select_related(
            "teacher", "subject", "academic_class", "session", "term"
        ).order_by("-is_active", "academic_class__code", "subject__name")
        paginated = self._paginate_queryset(assignment_qs)
        context["assignments"] = paginated["rows"]
        context["assignments_page_obj"] = paginated["page_obj"]
        context["assignments_page_size"] = paginated["page_size"]
        context["assignments_page_size_options"] = paginated["page_size_options"]
        context["assignments_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = TeacherSubjectAssignmentForm(request.POST)
        if form.is_valid():
            item = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="TEACHER_SUBJECT_ASSIGNED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"id": item.id},
            )
            messages.success(request, "Teacher-subject assignment saved.")
            return redirect("academics:it-teacher-subject-assignments")
        return self.render_to_response(self.get_context_data(form=form))


class ITTeacherSubjectAssignmentUpdateView(ITManagerRequiredMixin, UpdateView):
    model = TeacherSubjectAssignment
    form_class = TeacherSubjectAssignmentForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-teacher-subject-assignments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Teacher Subject Assignment"
        context["back_url"] = reverse("academics:it-teacher-subject-assignments")
        return context


class ITFormTeacherAssignmentListCreateView(ITManagerRequiredMixin, TemplateView):
    template_name = "academics/it_form_teacher_assignments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form"] = kwargs.get("form") or FormTeacherAssignmentForm()
        assignment_qs = FormTeacherAssignment.objects.select_related(
            "teacher", "academic_class", "session"
        ).order_by("-is_active", "academic_class__code")
        paginated = self._paginate_queryset(assignment_qs)
        context["assignments"] = paginated["rows"]
        context["assignments_page_obj"] = paginated["page_obj"]
        context["assignments_page_size"] = paginated["page_size"]
        context["assignments_page_size_options"] = paginated["page_size_options"]
        context["assignments_base_query"] = self._query_string_without("page")
        return context

    def post(self, request, *args, **kwargs):
        form = FormTeacherAssignmentForm(request.POST)
        if form.is_valid():
            item = form.save()
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="FORM_TEACHER_ASSIGNED",
                status=AuditStatus.SUCCESS,
                actor=request.user,
                request=request,
                metadata={"id": item.id},
            )
            messages.success(request, "Form teacher assignment saved.")
            return redirect("academics:it-form-teacher-assignments")
        return self.render_to_response(self.get_context_data(form=form))


class ITFormTeacherAssignmentUpdateView(ITManagerRequiredMixin, UpdateView):
    model = FormTeacherAssignment
    form_class = FormTeacherAssignmentForm
    template_name = "academics/it_edit_form.html"
    success_url = reverse_lazy("academics:it-form-teacher-assignments")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "Edit Form Teacher Assignment"
        context["back_url"] = reverse("academics:it-form-teacher-assignments")
        return context


class ITClassDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(AcademicClass, pk=kwargs["pk"])
        code = row.code
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        if not row.is_active:
            ClassSubject.objects.filter(academic_class=row, is_active=True).update(
                is_active=False
            )
            TeacherSubjectAssignment.objects.filter(
                academic_class=row, is_active=True
            ).update(is_active=False)
            FormTeacherAssignment.objects.filter(
                academic_class=row, is_active=True
            ).update(is_active=False)
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="ACADEMIC_CLASS_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"code": code, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Class {code} {status_label}.")
        return redirect("academics:it-classes")


class ITSubjectDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(Subject, pk=kwargs["pk"])
        name = row.name
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        if not row.is_active:
            ClassSubject.objects.filter(subject=row, is_active=True).update(is_active=False)
            TeacherSubjectAssignment.objects.filter(subject=row, is_active=True).update(
                is_active=False
            )
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="SUBJECT_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"name": name, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Subject {name} {status_label}.")
        return redirect("academics:it-subjects")


class ITClassSubjectDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(ClassSubject, pk=kwargs["pk"])
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="CLASS_SUBJECT_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"id": row.id, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Class-subject mapping {status_label}.")
        return redirect("academics:it-class-subjects")


class ITTeacherSubjectAssignmentDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(TeacherSubjectAssignment, pk=kwargs["pk"])
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="TEACHER_SUBJECT_ASSIGNMENT_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"id": row.id, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Teacher subject assignment {status_label}.")
        return redirect("academics:it-teacher-subject-assignments")


class ITFormTeacherAssignmentDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(FormTeacherAssignment, pk=kwargs["pk"])
        row.is_active = not row.is_active
        row.save(update_fields=["is_active", "updated_at"])
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="FORM_TEACHER_ASSIGNMENT_TOGGLED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"id": row.id, "is_active": row.is_active},
        )
        status_label = "activated" if row.is_active else "deactivated"
        messages.success(request, f"Form teacher assignment {status_label}.")
        return redirect("academics:it-form-teacher-assignments")


def _related_usage_counts(instance):
    usage = {}
    for relation in instance._meta.related_objects:
        accessor_name = relation.get_accessor_name()
        if not accessor_name:
            continue
        related = getattr(instance, accessor_name, None)
        try:
            if hasattr(related, "all"):
                count = related.all().count()
            else:
                count = 1 if related is not None else 0
        except Exception:
            continue
        if count:
            model_label = (
                f"{relation.related_model._meta.app_label}."
                f"{relation.related_model.__name__}"
            )
            usage[model_label] = count
    return usage


def _usage_summary_text(usage):
    rows = [f"{label}={count}" for label, count in sorted(usage.items())[:5]]
    if len(usage) > 5:
        rows.append("...")
    return ", ".join(rows)


class ITClassHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(AcademicClass, pk=kwargs["pk"])
        code = row.code
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="ACADEMIC_CLASS_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"code": code, "usage": usage},
            )
            messages.error(
                request,
                (
                    f"Class {code} cannot be deleted because records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-classes")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="ACADEMIC_CLASS_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"code": code},
        )
        messages.success(request, f"Class {code} deleted permanently.")
        return redirect("academics:it-classes")


class ITSubjectHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(Subject, pk=kwargs["pk"])
        name = row.name
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="SUBJECT_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"name": name, "usage": usage},
            )
            messages.error(
                request,
                (
                    f"Subject {name} cannot be deleted because records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-subjects")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="SUBJECT_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"name": name},
        )
        messages.success(request, f"Subject {name} deleted permanently.")
        return redirect("academics:it-subjects")


class ITClassSubjectHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(ClassSubject, pk=kwargs["pk"])
        descriptor = f"{row.academic_class.code}-{row.subject.code}"
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="CLASS_SUBJECT_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"descriptor": descriptor, "usage": usage},
            )
            messages.error(
                request,
                (
                    "Mapping cannot be deleted because dependent records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-class-subjects")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="CLASS_SUBJECT_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"descriptor": descriptor},
        )
        messages.success(request, "Class-subject mapping deleted permanently.")
        return redirect("academics:it-class-subjects")


class ITTeacherSubjectAssignmentHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(TeacherSubjectAssignment, pk=kwargs["pk"])
        descriptor = f"{row.teacher.username}:{row.subject.code}:{row.academic_class.code}"
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="TEACHER_SUBJECT_ASSIGNMENT_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"descriptor": descriptor, "usage": usage},
            )
            messages.error(
                request,
                (
                    "Assignment cannot be deleted because dependent records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-teacher-subject-assignments")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="TEACHER_SUBJECT_ASSIGNMENT_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"descriptor": descriptor},
        )
        messages.success(request, "Teacher-subject assignment deleted permanently.")
        return redirect("academics:it-teacher-subject-assignments")


class ITFormTeacherAssignmentHardDeleteView(ITManagerRequiredMixin, RedirectView):
    permanent = False

    def post(self, request, *args, **kwargs):
        row = get_object_or_404(FormTeacherAssignment, pk=kwargs["pk"])
        descriptor = f"{row.teacher.username}:{row.academic_class.code}:{row.session.name}"
        usage = _related_usage_counts(row)
        if usage:
            log_event(
                category=AuditCategory.SYSTEM,
                event_type="FORM_TEACHER_ASSIGNMENT_DELETE_BLOCKED",
                status=AuditStatus.DENIED,
                actor=request.user,
                request=request,
                metadata={"descriptor": descriptor, "usage": usage},
            )
            messages.error(
                request,
                (
                    "Assignment cannot be deleted because dependent records exist: "
                    f"{_usage_summary_text(usage)}. Use deactivate instead."
                ),
            )
            return redirect("academics:it-form-teacher-assignments")

        row.delete()
        log_event(
            category=AuditCategory.SYSTEM,
            event_type="FORM_TEACHER_ASSIGNMENT_DELETED",
            status=AuditStatus.SUCCESS,
            actor=request.user,
            request=request,
            metadata={"descriptor": descriptor},
        )
        messages.success(request, "Form-teacher assignment deleted permanently.")
        return redirect("academics:it-form-teacher-assignments")
