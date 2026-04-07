import json
from datetime import date

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import reverse

from apps.dashboard.public_site import (
    PUBLIC_INDEXABLE_PATHS,
    get_public_news_item,
    get_public_page,
    public_site_enabled,
)
from apps.tenancy.utils import build_portal_url, current_portal_key

DEFAULT_SITE_NAME = "NDGA Portal"
DEFAULT_ORGANIZATION_NAME = "Notre Dame Girls Academy"
DEFAULT_DESCRIPTION = (
    "Portal access for students, staff, academic records, finance, CBT, and "
    "school operations at Notre Dame Girls Academy, Kuje Abuja."
)
PUBLIC_SITE_NAME = "Notre Dame Girls' Academy, Kuje-Abuja"
PUBLIC_DESCRIPTION = (
    "Notre Dame Girls' Academy, Kuje-Abuja: a Catholic girls' boarding school with "
    "strong academics, discipline, care, and guided admissions."
)


def _indexable_paths():
    if public_site_enabled():
        return PUBLIC_INDEXABLE_PATHS
    return {"/"}


def _landing_url(request, path="/"):
    return build_portal_url(request, "landing", path)


def _is_indexable(request):
    return (
        request.method == "GET"
        and not getattr(request.user, "is_authenticated", False)
        and current_portal_key(request) == "landing"
        and request.path in _indexable_paths()
    )


def _public_meta(request):
    if not public_site_enabled() or current_portal_key(request) != "landing":
        return None
    if request.path == "/":
        return {
            "site_name": PUBLIC_SITE_NAME,
            "description": PUBLIC_DESCRIPTION,
        }
    page_map = {
        "/about/": "about",
        "/principal/": "principal",
        "/about/leadership/": "leadership",
        "/about/mission-vision-values/": "mission-vision-values",
        "/about/school-life/": "school-life",
        "/academics/": "academics",
        "/academics/junior-secondary/": "junior-secondary",
        "/academics/senior-secondary/": "senior-secondary",
        "/academics/curriculum/": "curriculum",
        "/academics/subjects-departments/": "subjects-departments",
        "/academics/ict-digital-learning/": "ict-digital-learning",
        "/academics/co-curricular-activities/": "co-curricular-activities",
        "/academics/learning-support/": "learning-support",
        "/academics/examinations-assessment/": "examinations-assessment",
        "/admissions/": "admissions",
        "/admissions/how-to-apply/": "how-to-apply",
        "/admissions/registration/": "registration",
        "/fees/": "fees",
        "/hostel-boarding/": "hostel-boarding",
        "/admissions/payment-information/": "payment-information",
        "/admissions/admission-faqs/": "admission-faqs",
        "/life-at-ndga/": "life-at-ndga",
        "/facilities/": "facilities",
        "/gallery/": "gallery",
        "/news/": "news",
        "/events/": "events",
        "/contact/": "contact",
    }
    slug = page_map.get(request.path)
    if slug:
        page = get_public_page(slug)
        if page:
            return {
                "site_name": PUBLIC_SITE_NAME,
                "description": page["description"],
            }
    if request.path.startswith("/news/"):
        slug = request.path.strip("/").split("/")[-1]
        article = get_public_news_item(slug)
        if article:
            return {
                "site_name": f"{article['title']} | {PUBLIC_SITE_NAME}",
                "description": article["summary"],
            }
    return {
        "site_name": PUBLIC_SITE_NAME,
        "description": PUBLIC_DESCRIPTION,
    }


def build_seo_context(request):
    landing_url = _landing_url(request, "/")
    share_image_url = _landing_url(request, static("ndga-share.png"))
    logo_url = _landing_url(request, static("images/ndga/logo.png"))
    public_meta = _public_meta(request)
    site_name = public_meta["site_name"] if public_meta else getattr(settings, "SEO_SITE_NAME", DEFAULT_SITE_NAME)
    organization_name = getattr(settings, "SEO_ORGANIZATION_NAME", DEFAULT_ORGANIZATION_NAME)
    description = public_meta["description"] if public_meta else getattr(settings, "SEO_DEFAULT_DESCRIPTION", DEFAULT_DESCRIPTION)
    is_indexable = _is_indexable(request)
    page_url = request.build_absolute_uri()
    schema_payload = [
        {
            "@context": "https://schema.org",
            "@type": "EducationalOrganization",
            "name": organization_name,
            "alternateName": site_name,
            "url": landing_url,
            "logo": logo_url,
            "description": description,
        },
        {
            "@context": "https://schema.org",
            "@type": "WebSite",
            "name": site_name,
            "url": landing_url,
            "description": description,
            "publisher": {
                "@type": "EducationalOrganization",
                "name": organization_name,
                "url": landing_url,
                "logo": logo_url,
            },
        },
    ]
    return {
        "seo_site_name": site_name,
        "seo_default_title": site_name,
        "seo_default_description": description,
        "seo_robots_content": "index, follow" if is_indexable else "noindex, nofollow",
        "seo_canonical_url": page_url,
        "seo_image_url": share_image_url,
        "seo_url": page_url,
        "seo_is_public_indexable": is_indexable,
        "seo_google_site_verification": getattr(settings, "GOOGLE_SITE_VERIFICATION", ""),
        "seo_google_analytics_id": getattr(settings, "GOOGLE_ANALYTICS_ID", ""),
        "seo_google_ads_id": getattr(settings, "GOOGLE_ADS_ID", ""),
        "seo_google_adsense_client_id": getattr(settings, "GOOGLE_ADSENSE_CLIENT_ID", ""),
        "seo_schema_json": json.dumps(schema_payload),
        "seo_sitemap_url": _landing_url(request, reverse("sitemap-xml")),
    }


def robots_txt(request):
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /auth/\n"
        "Disallow: /portal/\n"
        "Disallow: /setup/\n"
        "Disallow: /attendance/\n"
        "Disallow: /results/\n"
        "Disallow: /cbt/\n"
        "Disallow: /elections/\n"
        "Disallow: /finance/\n"
        "Disallow: /sync/\n"
        "Disallow: /audit/\n"
        "Disallow: /notifications/\n"
        "Disallow: /pdfs/\n\n"
        f"Sitemap: {_landing_url(request, reverse('sitemap-xml'))}\n"
    )
    return HttpResponse(content, content_type="text/plain; charset=utf-8")


def sitemap_xml(request):
    today = date.today().isoformat()
    urls = []
    for path in sorted(_indexable_paths()):
        priority = "1.0" if path == "/" else "0.8"
        changefreq = "daily" if path == "/" else "weekly"
        urls.append(
            f"""  <url>
    <loc>{_landing_url(request, path)}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>{changefreq}</changefreq>
    <priority>{priority}</priority>
  </url>"""
        )
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
{chr(10).join(urls)}
</urlset>
'''
    return HttpResponse(content, content_type="application/xml; charset=utf-8")
