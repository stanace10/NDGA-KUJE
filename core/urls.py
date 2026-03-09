from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from core.ops import healthz, readyz

urlpatterns = [
    path("ops/healthz/", healthz, name="ops-healthz"),
    path("ops/readyz/", readyz, name="ops-readyz"),
    path("admin/", admin.site.urls),
    path("auth/", include("apps.accounts.urls")),
    path("audit/", include("apps.audit.urls")),
    path("setup/", include("apps.setup_wizard.urls")),
    path("academics/", include("apps.academics.urls")),
    path("attendance/", include("apps.attendance.urls")),
    path("results/", include("apps.results.urls")),
    path("cbt/", include("apps.cbt.urls")),
    path("sync/", include("apps.sync.urls")),
    path("elections/", include("apps.elections.urls")),
    path("finance/", include("apps.finance.urls")),
    path("pdfs/", include("apps.pdfs.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("", include("apps.dashboard.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
