import json
from datetime import date

from django.conf import settings
from django.http import HttpResponse
from django.templatetags.static import static
from django.urls import reverse

from apps.tenancy.utils import build_portal_url, current_portal_key

DEFAULT_SITE_NAME = "NDGA AI Enterprise Platform"
DEFAULT_ORGANIZATION_NAME = "Notre Dame Girls Academy"
DEFAULT_DESCRIPTION = (
    "Governance-first school management, CBT, elections, finance, sync, and "
    "academic operations for Notre Dame Girls Academy, Kuje Abuja."
)


def _landing_url(request, path="/"):
    return build_portal_url(request, "landing", path)


def _is_public_indexable(request):
    return (
        request.method == "GET"
        and not getattr(request.user, "is_authenticated", False)
        and current_portal_key(request) == "landing"
        and request.path == "/"
    )


def build_seo_context(request):
    landing_url = _landing_url(request, "/")
    share_image_url = _landing_url(request, static("ndga-share.png"))
    logo_url = _landing_url(request, static("images/ndga/logo.png"))
    site_name = getattr(settings, "SEO_SITE_NAME", DEFAULT_SITE_NAME)
    organization_name = getattr(settings, "SEO_ORGANIZATION_NAME", DEFAULT_ORGANIZATION_NAME)
    description = getattr(settings, "SEO_DEFAULT_DESCRIPTION", DEFAULT_DESCRIPTION)
    is_public_indexable = _is_public_indexable(request)
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
        "seo_robots_content": "index, follow" if is_public_indexable else "noindex, nofollow",
        "seo_canonical_url": page_url,
        "seo_image_url": share_image_url,
        "seo_url": page_url,
        "seo_is_public_indexable": is_public_indexable,
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
    landing_url = _landing_url(request, "/")
    today = date.today().isoformat()
    content = f'''<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url>
    <loc>{landing_url}</loc>
    <lastmod>{today}</lastmod>
    <changefreq>daily</changefreq>
    <priority>1.0</priority>
  </url>
</urlset>
'''
    return HttpResponse(content, content_type="application/xml; charset=utf-8")
