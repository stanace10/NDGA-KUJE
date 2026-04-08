from __future__ import annotations

from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.models import User
from apps.dashboard.forms import PublicAdmissionRegistrationForm, PublicContactForm
from apps.dashboard.models import SchoolProfile
from apps.notifications.models import NotificationCategory
from apps.notifications.services import create_bulk_notifications, send_email_event
from apps.dashboard.public_site import (
    PUBLIC_INDEXABLE_PATHS,
    get_public_events,
    get_public_gallery,
    get_public_gallery_category,
    get_public_news,
    get_public_news_item,
    get_public_page,
    get_public_site_context,
    public_site_enabled,
)


def _management_team_recipients(*, include_bursar=False):
    role_codes = [ROLE_IT_MANAGER, ROLE_VP, ROLE_PRINCIPAL]
    if include_bursar:
        role_codes.append(ROLE_BURSAR)
    role_filter = Q(primary_role__code__in=role_codes) | Q(secondary_roles__code__in=role_codes)
    return list(User.objects.filter(is_active=True).filter(role_filter).distinct())


def _notify_public_submission(*, submission, request):
    profile = SchoolProfile.load()
    include_bursar = submission.submission_type == "ADMISSION"
    recipients = _management_team_recipients(include_bursar=include_bursar)
    if submission.submission_type == "ADMISSION":
        title = f"New admission application: {submission.applicant_name or submission.contact_name}"
        message = (
            f"{submission.applicant_name or submission.contact_name} applied for {submission.intended_class or '-'}.\n"
            f"Guardian: {submission.guardian_name or submission.contact_name} | "
            f"Phone: {submission.guardian_phone or submission.contact_phone or '-'} | "
            f"Payment: {submission.get_payment_status_display()}."
        )
    else:
        title = f"New enquiry: {submission.subject or submission.category or 'Website message'}"
        message = (
            f"{submission.contact_name} sent a {submission.category or 'website'} message.\n"
            f"Email: {submission.contact_email or '-'} | Phone: {submission.contact_phone or '-'}."
        )
    if recipients:
        create_bulk_notifications(
            recipients=recipients,
            category=NotificationCategory.SYSTEM,
            title=title,
            message=message,
            action_url="/notifications/center/",
            metadata={
                "event": "PUBLIC_SITE_SUBMISSION",
                "submission_id": str(submission.id),
                "submission_type": submission.submission_type,
            },
        )
    send_email_event(
        to_emails=[profile.contact_email or "office@ndgakuje.org"],
        subject=f"NDGA Website: {title}",
        body_text=f"{message}\n\nOpen the portal notification center for follow-up.",
        request=request,
        metadata={
            "event": "PUBLIC_SITE_SUBMISSION",
            "submission_id": str(submission.id),
            "submission_type": submission.submission_type,
        },
    )


class PublicSiteEnabledMixin:
    def dispatch(self, request, *args, **kwargs):
        if not public_site_enabled():
            raise Http404()
        if getattr(request, "portal_key", "landing") != "landing":
            raise Http404()
        return super().dispatch(request, *args, **kwargs)

    def school_profile(self):
        return SchoolProfile.load()

    def base_context(self):
        profile = self.school_profile()
        context = get_public_site_context(school_profile=profile)
        context["school_profile"] = profile
        context["public_indexable_paths"] = PUBLIC_INDEXABLE_PATHS
        return context


class PublicHomeView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_title": "Educating Girls for Life",
                "page_description": (
                    "Notre Dame Girls' Academy, Kuje-Abuja: a Catholic girls' boarding "
                    "school focused on academic formation, discipline, and care."
                ),
                "page_key": "home",
                "home_about": get_public_page("about"),
                "home_principal": get_public_page("principal"),
                "home_academics": get_public_page("academics"),
                "home_admissions": get_public_page("admissions"),
                "home_life": get_public_page("life-at-ndga"),
                "home_fees": get_public_page("fees"),
                "home_facilities": get_public_page("facilities"),
                "home_academic_highlights": [
                    {
                        "title": "Junior Secondary",
                        "text": "Strong foundations in English Studies, Mathematics, Intermediate Science, Digital Technologies, citizenship, and disciplined study routine.",
                        "image": context["public_images"]["computer_lab_junior"],
                        "images": [
                            context["public_images"]["computer_lab_junior"],
                            context["public_images"]["computer_lab_pair"],
                            context["public_images"]["hero_students"],
                        ],
                        "href": "/academics/junior-secondary/",
                    },
                    {
                        "title": "Senior Secondary",
                        "text": "A balanced programme preparing students for WAEC, NECO, leadership, and responsible choices beyond school.",
                        "image": context["public_images"]["science_lab"],
                        "images": [
                            context["public_images"]["science_lab"],
                            context["public_images"]["physics_lab"],
                            context["public_images"]["library"],
                        ],
                        "href": "/academics/senior-secondary/",
                    },
                    {
                        "title": "Subjects, Exams, and Support",
                        "text": "Subjects are broad, assessment is structured, and mentoring, revision, and guided follow-up support every girl's progress.",
                        "image": context["public_images"]["library"],
                        "images": [
                            context["public_images"]["library"],
                            context["public_images"]["cbt_room"],
                            context["public_images"]["computer_lab"],
                        ],
                        "href": "/academics/subjects-departments/",
                    },
                ],
                "home_hallmarks": [
                    {
                        "title": "A Welcoming Community",
                        "text": "Girls are known, encouraged, and helped to settle into a calm and friendly school environment.",
                    },
                    {
                        "title": "A Learning Community",
                        "text": "High expectations, academic follow-up, and celebration of achievement shape the rhythm of school life.",
                    },
                    {
                        "title": "A Caring Community",
                        "text": "Pastoral attention, boarding supervision, and close staff support remain visible in the daily life of students.",
                    },
                    {
                        "title": "A Worshipping Community",
                        "text": "Prayer, assemblies, Mass, retreats, and Catholic witness remain part of the formation of every student.",
                    },
                ],
                "home_gallery": get_public_gallery()[:4],
                "home_news": get_public_news()[:2],
                "home_events": get_public_events()[:3],
                "credibility_points": [
                    "Structured boarding routine and supervised student welfare.",
                    "Academic support from junior to senior secondary.",
                    "Catholic formation rooted in discipline, responsibility, and service.",
                    "Learning spaces that support science, ICT, reading, and student growth.",
                ],
                "chatbot_prompts": [
                    "How do I apply?",
                    "What are the entrance exam subjects?",
                    "Tell me about boarding.",
                    "How do I contact admissions?",
                ],
            }
        )
        return context


class PublicContentPageView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/page.html"
    page_slug = ""

    def get_page(self):
        page = get_public_page(self.page_slug)
        if page is None:
            raise Http404()
        return page

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.get_page()
        context.update(self.base_context())
        context.update(
            {
                "page_key": self.page_slug,
                "page_title": page["title"],
                "page_description": page["description"],
                "public_page": page,
            }
        )
        if self.page_slug == "gallery":
            context["gallery_items"] = get_public_gallery()
        elif self.page_slug == "news":
            context["news_items"] = get_public_news()
        elif self.page_slug == "events":
            context["event_items"] = get_public_events()
        return context


class PublicGalleryCategoryView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/gallery_category.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_public_gallery_category(kwargs["slug"])
        if category is None:
            raise Http404()
        context.update(self.base_context())
        context.update(
            {
                "page_key": "gallery",
                "page_title": category["title"],
                "page_description": category["summary"],
                "gallery_category": category,
                "related_gallery_categories": [
                    row for row in get_public_gallery() if row["slug"] != category["slug"]
                ][:4],
            }
        )
        return context


class PublicNewsDetailView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/news_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = get_public_news_item(kwargs["slug"])
        if article is None:
            raise Http404()
        context.update(self.base_context())
        context.update(
            {
                "page_key": "news",
                "page_title": article["title"],
                "page_description": article["summary"],
                "article": article,
                "related_articles": [
                    row for row in get_public_news() if row["slug"] != article["slug"]
                ][:2],
            }
        )
        return context


class PublicContactView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_key": "contact",
                "page_title": "Contact Us",
                "page_description": "Contact admissions, send an enquiry, or find the school location.",
                "form": kwargs.get("form") or PublicContactForm(),
                "submitted": self.request.GET.get("submitted") == "1",
                "chatbot_prompts": [
                    "Ask about admissions",
                    "Ask about fees",
                    "Ask about boarding",
                    "Ask about portal help",
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = PublicContactForm(request.POST)
        if form.is_valid():
            submission = form.save()
            _notify_public_submission(submission=submission, request=request)
            return redirect(f"{request.path}?submitted=1")
        return self.render_to_response(self.get_context_data(form=form))


class PublicRegistrationView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/registration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_key": "registration",
                "page_title": "Online Registration",
                "page_description": "Begin the NDGA admission process with applicant details, boarding preference, and supporting documents.",
                "form": kwargs.get("form") or PublicAdmissionRegistrationForm(),
                "submitted": self.request.GET.get("submitted") == "1",
                "required_documents": [
                    "Passport photograph",
                    "Birth certificate",
                    "Recent school result or transcript",
                ],
                "registration_steps": [
                    "Applicant details",
                    "Parent or guardian details",
                    "Boarding and school records",
                    "Review and submit",
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = PublicAdmissionRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save()
            _notify_public_submission(submission=submission, request=request)
            return redirect(f"{request.path}?submitted=1")
        return self.render_to_response(self.get_context_data(form=form))


class PublicLiveChatCreateView(PublicSiteEnabledMixin, View):
    def post(self, request, *args, **kwargs):
        contact_email = request.POST.get("contact_email", "").strip()
        if not contact_email:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {
                        "contact_email": [
                            {
                                "message": "Email address is required so management can reply to you.",
                                "code": "required",
                            }
                        ]
                    },
                },
                status=400,
            )
        form = PublicContactForm(
            {
                "contact_name": request.POST.get("contact_name", "").strip(),
                "contact_email": contact_email,
                "contact_phone": request.POST.get("contact_phone", "").strip(),
                "category": "Live Chat",
                "subject": "Website Management Chat",
                "message": request.POST.get("message", "").strip(),
            }
        )
        if form.is_valid():
            submission = form.save()
            _notify_public_submission(submission=submission, request=request)
            ticket_reference = f"NDGA-CHAT-{submission.id:05d}"
            return JsonResponse(
                {
                    "ok": True,
                    "message": "Your message has been sent to management. Replies will go to your email.",
                    "ticket_reference": ticket_reference,
                }
            )
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
