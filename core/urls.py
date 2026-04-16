from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import TemplateView

from core.manual_updates import ManualUpdateExportView, ManualUpdateImportView
from core.ops import healthz, metrics, readyz
from core.seo import robots_txt, sitemap_xml

urlpatterns = [
    path(
        "manifest.webmanifest",
        TemplateView.as_view(
            template_name="pwa/manifest.webmanifest",
            content_type="application/manifest+json",
        ),
        name="pwa-manifest",
    ),
    path(
        "portal-sw.js",
        TemplateView.as_view(
            template_name="pwa/portal_sw.js",
            content_type="application/javascript",
        ),
        name="pwa-service-worker",
    ),
    path("robots.txt", robots_txt, name="robots-txt"),
    path("sitemap.xml", sitemap_xml, name="sitemap-xml"),
    path("ops/healthz/", healthz, name="ops-healthz"),
    path("ops/readyz/", readyz, name="ops-readyz"),
    path("ops/metrics/", metrics, name="ops-metrics"),
    path("ops/manual-export/updates/", ManualUpdateExportView.as_view(), name="ops-manual-update-export"),
    path("ops/manual-import/updates/", ManualUpdateImportView.as_view(), name="ops-manual-update-import"),
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls")),
    path("audit/", include("apps.audit.urls")),
    path("setup/", include("apps.setup_wizard.urls")),
    path("academics/", include("apps.academics.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("results/", include("apps.results.urls")),
    path("cbt/", include("apps.cbt.urls")),
    path("elections/", include("apps.elections.urls")),
    path("finance/", include("apps.finance.urls")),
    path("pdfs/", include("apps.pdfs.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("", include("apps.dashboard.urls")),
]

if getattr(settings, "SYNC_LOCAL_NODE_ENABLED", True):
    urlpatterns.insert(10, path("sync/", include("apps.sync.urls")))

if settings.DEBUG or getattr(settings, 'NDGA_LOCAL_SIMPLE_HOST_MODE', False):
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
