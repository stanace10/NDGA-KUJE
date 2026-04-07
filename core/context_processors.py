from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from apps.accounts.constants import ROLE_IT_MANAGER
from apps.dashboard.navigation import PORTAL_TITLES, build_portal_navigation
from apps.notifications.models import Notification
from apps.setup_wizard.feature_flags import get_runtime_feature_flags
from apps.setup_wizard.services import get_setup_state
from apps.sync.services import build_runtime_status_payload
from apps.tenancy.utils import (
    build_portal_url,
    cloud_staff_operations_lan_only_enabled,
    current_portal_key,
    lan_runtime_restrictions_enabled,
)
from core.seo import build_seo_context


def _minimal_cbt_runtime_context(request, portal_key):
    seo_context = {
        "seo_default_title": "NDGA CBT",
        "seo_default_description": "NDGA CBT runtime",
        "seo_robots_content": "noindex, nofollow",
        "seo_site_name": "Notre Dame Girls Academy",
        "seo_canonical_url": "",
        "seo_sitemap_url": "",
        "seo_url": "",
        "seo_image_url": "",
        "seo_google_site_verification": "",
        "seo_schema_json": "",
        "seo_is_public_indexable": False,
        "seo_google_analytics_id": "",
        "seo_google_ads_id": "",
        "seo_google_adsense_client_id": "",
    }
    return {
        "feature_flags": settings.FEATURE_FLAGS,
        "portal_subdomains": settings.PORTAL_SUBDOMAINS,
        "portal_root_urls": {},
        "portal_login_urls": {},
        "current_portal_key": portal_key,
        "ndga_base_domain": settings.NDGA_BASE_DOMAIN,
        "setup_state": None,
        "setup_state_code": "READY",
        "setup_is_ready": True,
        "setup_current_session": None,
        "setup_current_term": None,
        "show_setup_banner": False,
        "notification_unread_count": 0,
        "sync_runtime_status": {
            "code": "LOCAL_MODE",
            "label": "Local Mode",
            "tone": "blue",
            "pending_count": 0,
            "local_node_id": "",
            "cloud_configured": False,
            "cloud_connected": False,
            "offline_mode_enabled": bool(settings.FEATURE_FLAGS.get("OFFLINE_MODE_ENABLED", False)),
            "latest_synced_at": None,
            "dot_class": "bg-sky-500",
            "chip_class": "border-sky-200 bg-sky-50 text-sky-800",
        },
        "portal_mode_chips": [],
        "lan_runtime_restricted": False,
        "show_portal_shell": False,
        "portal_nav_items": [],
        "portal_nav_sections": [],
        "portal_shell_title": "NDGA CBT",
        **seo_context,
    }


def _mode_chips(*, feature_flags, sync_runtime_status, portal_key):
    cbt_enabled = feature_flags.get("CBT_ENABLED", False)
    election_enabled = feature_flags.get("ELECTION_ENABLED", False)
    offline_enabled = feature_flags.get("OFFLINE_MODE_ENABLED", False)

    chips = [
        {
            "label": "Offline",
            "value": "ON" if offline_enabled else "OFF",
            "chip_class": (
                "border-sky-200 bg-sky-50 text-sky-800"
                if offline_enabled
                else "border-slate-200 bg-slate-100 text-slate-600"
            ),
        },
        {
            "label": "Network",
            "value": sync_runtime_status.get("label", "Unknown"),
            "chip_class": sync_runtime_status.get(
                "chip_class",
                "border-slate-200 bg-slate-100 text-slate-600",
            ),
        },
    ]
    if portal_key != "student":
        chips.insert(
            0,
            {
                "label": "Election",
                "value": "ON" if election_enabled else "OFF",
                "chip_class": (
                    "border-emerald-200 bg-emerald-50 text-emerald-800"
                    if election_enabled
                    else "border-slate-200 bg-slate-100 text-slate-600"
                ),
            },
        )
        chips.insert(
            0,
            {
                "label": "CBT",
                "value": "ON" if cbt_enabled else "OFF",
                "chip_class": (
                    "border-emerald-200 bg-emerald-50 text-emerald-800"
                    if cbt_enabled
                    else "border-slate-200 bg-slate-100 text-slate-600"
                ),
            },
        )
    return chips


def platform_context(request):
    portal_key = current_portal_key(request)
    request_path = getattr(request, "path", "") or ""
    if request_path.startswith("/cbt/attempts/"):
        return _minimal_cbt_runtime_context(request, portal_key)
    lan_runtime_restricted = lan_runtime_restrictions_enabled()
    cloud_staff_operations_lan_only = cloud_staff_operations_lan_only_enabled()
    runtime_feature_flags = get_runtime_feature_flags()
    portal_root_urls = {
        key: build_portal_url(request, key, "/")
        for key in settings.PORTAL_SUBDOMAINS
    }
    portal_login_urls = {
        "student": build_portal_url(
            request,
            "student",
            "/auth/login/",
            {"audience": "student"},
        ),
        "staff": build_portal_url(
            request,
            "staff",
            "/auth/login/",
            {"audience": "staff"},
        ),
    }
    setup_state_code = "BOOT_EMPTY"
    setup_is_ready = False
    setup_current_session = None
    setup_current_term = None
    try:
        setup_state = get_setup_state()
        setup_state_code = setup_state.state
        setup_is_ready = setup_state.is_ready
        setup_current_session = setup_state.current_session
        setup_current_term = setup_state.current_term
    except (OperationalError, ProgrammingError):
        # During fresh migrations/tests before setup tables exist.
        setup_state = None

    show_setup_banner = (
        bool(getattr(request.user, "is_authenticated", False))
        and not setup_is_ready
        and not request.user.has_role(ROLE_IT_MANAGER)
    )
    notification_unread_count = 0
    if getattr(request.user, "is_authenticated", False):
        try:
            notification_unread_count = Notification.objects.filter(
                recipient=request.user,
                read_at__isnull=True,
            ).count()
        except (OperationalError, ProgrammingError):
            notification_unread_count = 0
    sync_runtime_status = {
        "code": "DISCONNECTED",
        "label": "Disconnected",
        "tone": "red",
        "pending_count": 0,
        "local_node_id": "",
        "cloud_configured": False,
        "cloud_connected": False,
        "offline_mode_enabled": False,
        "latest_synced_at": None,
        "dot_class": "bg-rose-500",
        "chip_class": "border-rose-200 bg-rose-50 text-rose-800",
    }
    try:
        sync_runtime_status = build_runtime_status_payload()
    except (OperationalError, ProgrammingError):
        pass

    portal_nav_items = _portal_nav_items(
        request=request,
        portal_key=portal_key,
        setup_is_ready=setup_is_ready,
    )

    seo_context = build_seo_context(request)

    return {
        "feature_flags": runtime_feature_flags,
        "portal_subdomains": settings.PORTAL_SUBDOMAINS,
        "portal_root_urls": portal_root_urls,
        "portal_login_urls": portal_login_urls,
        "current_portal_key": portal_key,
        "ndga_base_domain": settings.NDGA_BASE_DOMAIN,
        "setup_state": setup_state,
        "setup_state_code": setup_state_code,
        "setup_is_ready": setup_is_ready,
        "setup_current_session": setup_current_session,
        "setup_current_term": setup_current_term,
        "show_setup_banner": show_setup_banner,
        "notification_unread_count": notification_unread_count,
        "sync_runtime_status": sync_runtime_status,
        "portal_mode_chips": _mode_chips(
            feature_flags=runtime_feature_flags,
            sync_runtime_status=sync_runtime_status,
            portal_key=portal_key,
        ),
        "lan_runtime_restricted": lan_runtime_restricted,
        "cloud_staff_operations_lan_only": cloud_staff_operations_lan_only,
        "show_portal_shell": _show_portal_shell(request, portal_key),
        "portal_nav_items": portal_nav_items,
        "portal_nav_sections": _portal_nav_sections(portal_nav_items),
        "portal_shell_title": PORTAL_TITLES.get(portal_key, "NDGA Platform"),
        **seo_context,
    }


def _show_portal_shell(request, portal_key):
    if not getattr(request.user, "is_authenticated", False):
        return False
    if portal_key in {"landing", "portal"}:
        return False
    if request.path.startswith("/auth/login/"):
        return False
    if request.path.startswith("/auth/password/change/"):
        return False
    return True


def _portal_nav_items(*, request, portal_key, setup_is_ready):
    if not getattr(request.user, "is_authenticated", False):
        return []
    role_codes = request.user.get_all_role_codes()
    return build_portal_navigation(
        portal_key=portal_key,
        role_codes=role_codes,
        request_path=request.path,
        setup_is_ready=setup_is_ready,
    )


def _portal_nav_sections(items):
    section_rows = []
    seen = {}
    for item in items:
        section_name = (item.get("section") or "").strip() or "Menu"
        if section_name not in seen:
            seen[section_name] = {"label": section_name, "items": []}
            section_rows.append(seen[section_name])
        seen[section_name]["items"].append(item)
    return section_rows
