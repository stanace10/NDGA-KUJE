from __future__ import annotations

from django.http import Http404
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.dashboard.forms import PublicAdmissionRegistrationForm, PublicContactForm
from apps.dashboard.models import SchoolProfile
from apps.dashboard.public_site import (
    PUBLIC_INDEXABLE_PATHS,
    get_public_events,
    get_public_gallery,
    get_public_news,
    get_public_news_item,
    get_public_page,
    get_public_site_context,
    public_site_enabled,
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
                "home_gallery": get_public_gallery()[:6],
                "home_news": get_public_news()[:3],
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
            form.save()
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
            form.save()
            return redirect(f"{request.path}?submitted=1")
        return self.render_to_response(self.get_context_data(form=form))
