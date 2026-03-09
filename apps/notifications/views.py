from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import (
    ROLE_BURSAR,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_VP,
)
from apps.accounts.models import User
from apps.academics.models import StudentClassEnrollment
from apps.accounts.permissions import has_any_role
from apps.notifications.forms import MediaBroadcastForm
from apps.notifications.models import Notification, NotificationCategory
from apps.notifications.services import create_bulk_notifications, send_email_event
from apps.setup_wizard.services import get_setup_state


def _allowed_notification_categories(user):
    allow_payment = any(
        user.has_role(code)
        for code in {ROLE_STUDENT, ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL}
    )
    allowed = [code for code, _ in NotificationCategory.choices]
    if allow_payment:
        return allowed
    return [code for code in allowed if code != NotificationCategory.PAYMENT]


def _notification_queryset(user):
    allowed_categories = _allowed_notification_categories(user)
    return Notification.objects.filter(
        recipient=user,
        category__in=allowed_categories,
    )


class NotificationCenterView(LoginRequiredMixin, TemplateView):
    template_name = "notifications/center.html"
    page_size = 20

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        status = (self.request.GET.get("status") or "all").strip().lower()
        category = (self.request.GET.get("category") or "all").strip().upper()
        window = (self.request.GET.get("window") or "all").strip().lower()
        queryset = _notification_queryset(self.request.user).order_by("-created_at")
        if status == "unread":
            queryset = queryset.filter(read_at__isnull=True)
        valid_categories = set(_allowed_notification_categories(self.request.user))
        if category in valid_categories:
            queryset = queryset.filter(category=category)
        valid_windows = {"all": None, "30d": 30, "90d": 90, "365d": 365}
        window_days = valid_windows.get(window, None)
        if window_days:
            queryset = queryset.filter(created_at__gte=timezone.now() - timedelta(days=window_days))

        paginator = Paginator(queryset, self.page_size)
        page_obj = paginator.get_page(self.request.GET.get("page", 1))
        context["status_filter"] = status
        context["category_filter"] = category
        context["window_filter"] = window
        context["page_obj"] = page_obj
        context["category_choices"] = [
            choice for choice in NotificationCategory.choices if choice[0] in valid_categories
        ]
        context["unread_count"] = _notification_queryset(self.request.user).filter(
            read_at__isnull=True,
        ).count()
        return context


class NotificationDetailView(LoginRequiredMixin, TemplateView):
    template_name = "notifications/detail.html"

    def dispatch(self, request, *args, **kwargs):
        self.notification = get_object_or_404(
            _notification_queryset(request.user),
            pk=kwargs["notification_id"],
        )
        self.notification.mark_read()
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        action_url = (self.notification.action_url or "").strip()
        # Backward compatibility for older payment notifications that pointed to portal home.
        if (
            self.notification.category == NotificationCategory.PAYMENT
            and action_url in {"", "/portal/student", "/portal/student/"}
        ):
            action_url = "/finance/student/overview/"
        context["notification"] = self.notification
        context["resolved_action_url"] = action_url
        return context


class NotificationMarkReadView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        notification = get_object_or_404(
            _notification_queryset(request.user),
            pk=kwargs["notification_id"],
        )
        notification.mark_read()
        messages.success(request, "Notification marked as read.")
        return redirect("notifications:center")


class NotificationMarkAllReadView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        updated = _notification_queryset(request.user).filter(
            read_at__isnull=True,
        ).update(read_at=timezone.now())
        if updated:
            messages.success(request, f"{updated} notifications marked as read.")
        else:
            messages.info(request, "No unread notifications.")
        return redirect("notifications:center")


class MediaCenterView(LoginRequiredMixin, TemplateView):
    template_name = "notifications/media_center.html"

    @staticmethod
    def _can_manage_media(user):
        return has_any_role(user, {ROLE_VP, ROLE_PRINCIPAL})

    def dispatch(self, request, *args, **kwargs):
        if not self._can_manage_media(request.user):
            messages.error(request, "Media center is restricted to VP and Principal.")
            return redirect("notifications:center")
        return super().dispatch(request, *args, **kwargs)

    def _form(self, data=None):
        return MediaBroadcastForm(data=data)

    def _recipient_emails(self, recipients):
        emails = set()
        for user in recipients:
            profile = getattr(user, "student_profile", None)
            if profile and profile.guardian_email:
                emails.add(profile.guardian_email.strip().lower())
            if user.email:
                emails.add(user.email.strip().lower())
        return sorted(email for email in emails if email)

    def _resolve_recipients(self, cleaned_data):
        audience = cleaned_data["audience"]
        if audience == MediaBroadcastForm.Audience.ALL_STUDENTS:
            return list(
                User.objects.filter(
                    primary_role__code=ROLE_STUDENT,
                    is_active=True,
                ).order_by("username")
            )
        if audience == MediaBroadcastForm.Audience.CLASS_STUDENTS:
            setup_state = get_setup_state()
            enrollments = StudentClassEnrollment.objects.filter(
                academic_class=cleaned_data["academic_class"],
                is_active=True,
            )
            if setup_state.current_session_id:
                enrollments = enrollments.filter(session_id=setup_state.current_session_id)
            student_ids = enrollments.values_list("student_id", flat=True)
            return list(
                User.objects.filter(
                    id__in=student_ids,
                    primary_role__code=ROLE_STUDENT,
                    is_active=True,
                ).order_by("username")
            )
        if audience == MediaBroadcastForm.Audience.ALL_STAFF:
            return list(
                User.objects.filter(staff_profile__isnull=False, is_active=True)
                .distinct()
                .order_by("username")
            )
        return list(cleaned_data["recipients"])

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["media_form"] = kwargs.get("media_form") or self._form()
        context["inbox_rows"] = _notification_queryset(self.request.user).order_by("-created_at")[:40]
        context["sent_rows"] = Notification.objects.filter(
            created_by=self.request.user
        ).select_related("recipient").order_by("-created_at")[:80]
        context["media_unread_count"] = _notification_queryset(self.request.user).filter(
            read_at__isnull=True
        ).count()
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action != "send_broadcast":
            messages.error(request, "Invalid media action.")
            return redirect("notifications:media-center")

        form = self._form(request.POST)
        if not form.is_valid():
            return self.render_to_response(self.get_context_data(media_form=form))

        recipients = self._resolve_recipients(form.cleaned_data)
        if not recipients:
            messages.error(request, "No recipients found for the selected audience.")
            return self.render_to_response(self.get_context_data(media_form=form))

        title = form.cleaned_data["subject"]
        body = form.cleaned_data["message"]
        create_bulk_notifications(
            recipients=recipients,
            category=NotificationCategory.SYSTEM,
            title=title,
            message=body,
            created_by=request.user,
            action_url="/notifications/center/",
            metadata={
                "event": "MEDIA_BROADCAST",
                "audience": form.cleaned_data["audience"],
            },
        )

        if form.cleaned_data.get("send_email"):
            send_email_event(
                to_emails=self._recipient_emails(recipients),
                subject=f"NDGA Bulletin: {title}",
                body_text=body,
                actor=request.user,
                request=request,
                metadata={
                    "event": "MEDIA_BROADCAST",
                    "audience": form.cleaned_data["audience"],
                    "recipient_count": len(recipients),
                },
            )

        messages.success(request, f"Broadcast sent to {len(recipients)} recipient(s).")
        return redirect("notifications:media-center")
