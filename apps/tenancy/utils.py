import ipaddress
from urllib.parse import urlencode

from django.conf import settings

from apps.accounts.constants import ROLE_HOME_PORTAL, STAFF_ROLE_CODES

_LOCAL_HOSTS = {"localhost", "127.0.0.1", "[::1]"}
_LOCAL_SIMPLE_PORTAL_ROOTS = {
    "landing": "/",
    "portal": "/",
    "student": "/portal/student/",
    "staff": "/portal/staff/",
    "it": "/portal/it/",
    "bursar": "/portal/bursar/",
    "vp": "/portal/vp/",
    "principal": "/portal/principal/",
    "cbt": "/portal/cbt/",
    "election": "/portal/election/",
}
_LOCAL_SIMPLE_PATH_PORTAL_HINTS = (
    ("/sync/", "it"),
    ("/audit/", "it"),
    ("/setup/", "it"),
    ("/auth/it/", "it"),
    ("/cbt/exams/", "cbt"),
    ("/cbt/attempts/", "cbt"),
    ("/cbt/it/", "it"),
    ("/cbt/authoring/", "cbt"),
    ("/cbt/dean/", "cbt"),
    ("/cbt/marking/", "cbt"),
    ("/cbt/simulator/", "cbt"),
    ("/cbt/", "cbt"),
    ("/elections/it/", "it"),
    ("/elections/vote/", "election"),
    ("/elections/analytics/", "election"),
    ("/elections/results/", "election"),
    ("/elections/verify/", "election"),
    ("/elections/", "election"),
    ("/finance/bursar/", "bursar"),
    ("/results/vp/", "vp"),
    ("/results/principal/", "principal"),
    ("/results/grade-entry/", "staff"),
    ("/results/dean/", "staff"),
    ("/results/form/", "staff"),
    ("/portal/student/", "student"),
    ("/portal/staff/", "staff"),
    ("/portal/it/", "it"),
    ("/portal/bursar/", "bursar"),
    ("/portal/vp/", "vp"),
    ("/portal/principal/", "principal"),
    ("/portal/cbt/", "cbt"),
    ("/portal/election/", "election"),
)

CLOUD_LAN_ONLY_OPERATION_PREFIXES = (
    "/attendance/",
    "/auth/it/",
    "/notifications/media/",
    "/setup/",
    "/results/approval/",
    "/results/grade-entry/",
    "/results/dean/",
    "/results/form/",
    "/results/report/send-results/",
    "/results/settings/",
    "/results/vp/",
    "/results/principal/",
    "/results/timeline/",
    "/sync/dashboard/",
    "/cbt/",
    "/elections/",
    "/finance/bursar/settings/",
    "/finance/bursar/charges/",
    "/finance/bursar/fees/",
    "/finance/bursar/payments/",
    "/finance/bursar/debtors/",
    "/finance/bursar/expenses/",
    "/finance/bursar/staff-payments/",
    "/finance/bursar/salaries/",
    "/finance/bursar/assets/",
    "/finance/bursar/messaging/",
    "/finance/bursar/reminders/run/",
)


def normalize_host(host):
    return (host or "").split(":")[0].lower()


def sync_node_role():
    return (getattr(settings, "SYNC_NODE_ROLE", "CLOUD") or "CLOUD").strip().upper()


def lan_runtime_restrictions_enabled():
    return bool(getattr(settings, "LAN_RUNTIME_RESTRICT_PORTALS", False) and sync_node_role() == "LAN")


def cloud_staff_operations_lan_only_enabled():
    return bool(getattr(settings, "CLOUD_STAFF_OPERATIONS_LAN_ONLY", False) and sync_node_role() == "CLOUD")


def user_has_lan_only_operation_roles(user_or_role_codes):
    if user_or_role_codes is None:
        return False
    if hasattr(user_or_role_codes, "is_authenticated"):
        if not getattr(user_or_role_codes, "is_authenticated", False):
            return False
        role_codes = set(user_or_role_codes.get_all_role_codes())
    else:
        role_codes = set(user_or_role_codes)
    return bool(role_codes & STAFF_ROLE_CODES)


def path_is_cloud_lan_only_operation(path):
    request_path = path or "/"
    return any(request_path.startswith(prefix) for prefix in CLOUD_LAN_ONLY_OPERATION_PREFIXES)


def _local_simple_portal_key_from_host(host):
    normalized = normalize_host(host).strip(".")
    if not normalized:
        return "landing"
    parts = normalized.split(".")
    if not parts:
        return "landing"
    candidate = parts[0].strip().lower()
    if candidate in settings.PORTAL_SUBDOMAINS:
        return candidate
    return "landing"


def _is_local_like_host(host):
    normalized = normalize_host(host)
    if normalized in _LOCAL_HOSTS or normalized.endswith(".local"):
        return True
    try:
        parsed = ipaddress.ip_address(normalized.strip("[]"))
    except ValueError:
        return False
    return parsed.is_private or parsed.is_loopback or parsed.is_link_local


def _local_simple_host_mode_enabled(request):
    return bool(getattr(settings, "NDGA_LOCAL_SIMPLE_HOST_MODE", False)) and _is_local_like_host(
        request.get_host()
    )


def _local_simple_portal_key_from_path(path):
    request_path = path or "/"
    for root_path, portal_key in _LOCAL_SIMPLE_PATH_PORTAL_HINTS:
        if request_path.startswith(root_path):
            return portal_key
    return "landing"


def _local_simple_portal_key_from_user(user):
    if not getattr(user, "is_authenticated", False):
        return "landing"
    primary_role = getattr(user, "primary_role", None)
    if primary_role is not None:
        portal_key = ROLE_HOME_PORTAL.get(primary_role.code)
        if portal_key:
            return portal_key
    secondary_codes = sorted(
        role_code
        for role_code in user.get_all_role_codes()
        if not primary_role or role_code != primary_role.code
    )
    for role_code in secondary_codes:
        portal_key = ROLE_HOME_PORTAL.get(role_code)
        if portal_key:
            return portal_key
    return "landing"


def _local_simple_portal_key_from_request(request):
    audience = (request.GET.get("audience", "") or request.POST.get("audience", "")).strip().lower()
    if audience in settings.PORTAL_SUBDOMAINS:
        return audience
    host_portal = _local_simple_portal_key_from_host(request.get_host())
    path_portal = _local_simple_portal_key_from_path(getattr(request, "path", "/"))
    request_path = getattr(request, "path", "/") or "/"
    # Student CBT/election runtime requests are path-owned and extremely hot.
    # Skip role resolution here to avoid extra role queries on every screen move.
    if request_path.startswith(("/cbt/attempts/", "/cbt/exams/available/")):
        return path_portal if path_portal != "landing" else "cbt"
    if request_path.startswith("/elections/vote/"):
        return path_portal if path_portal != "landing" else "election"
    user = getattr(request, "user", None)
    user_portal = _local_simple_portal_key_from_user(user)
    staff_cbt_prefixes = (
        "/cbt/authoring/",
        "/cbt/dean/",
        "/cbt/marking/",
    )
    if (
        user_portal in {"staff", "it", "vp", "principal"}
        and path_portal == "cbt"
        and (
            request_path.startswith(staff_cbt_prefixes)
            or request_path.rstrip("/") in {"/cbt", "/portal/cbt"}
        )
    ):
        return user_portal
    if host_portal != "landing" and path_portal == "landing":
        return host_portal
    if path_portal != "landing":
        return path_portal
    if user_portal != "landing":
        return user_portal
    return "landing"


def current_portal_key(request):
    if _local_simple_host_mode_enabled(request):
        return _local_simple_portal_key_from_request(request)

    host_obj = getattr(request, "host", None)
    if host_obj is not None and host_obj.name in settings.PORTAL_SUBDOMAINS:
        return host_obj.name

    req_host = normalize_host(request.get_host())
    for key, configured_host in settings.PORTAL_SUBDOMAINS.items():
        if req_host == normalize_host(configured_host):
            return key

    if req_host in _LOCAL_HOSTS:
        return "landing"
    return "landing"


def _host_has_explicit_port(host):
    # Supports regular host:port and bracketed IPv6 host: [::1]:8000
    if host.startswith("["):
        return "]:" in host
    return host.count(":") == 1 and host.rsplit(":", 1)[1].isdigit()


def _extract_port_from_host(host):
    if not host:
        return ""
    if host.startswith("["):
        if "]:" in host:
            return host.rsplit(":", 1)[1]
        return ""
    if host.count(":") == 1:
        maybe_port = host.rsplit(":", 1)[1]
        if maybe_port.isdigit():
            return maybe_port
    return ""


def _normalize_path(path):
    if not path:
        return "/"
    if not path.startswith("/"):
        return f"/{path}"
    return path


def _local_simple_root_path(portal_key, path):
    normalized_path = _normalize_path(path)
    if normalized_path == "/":
        return _LOCAL_SIMPLE_PORTAL_ROOTS.get(portal_key, "/")
    return normalized_path


def build_portal_url(request, portal_key, path="/", query=None):
    request_host = request.get_host()

    if _local_simple_host_mode_enabled(request):
        scheme = "http"
        host = request_host
        normalized_path = _local_simple_root_path(portal_key, path)
    else:
        scheme = "https" if request.is_secure() else "http"
        host = settings.PORTAL_SUBDOMAINS.get(portal_key, settings.PORTAL_SUBDOMAINS["landing"])
        normalized_path = _normalize_path(path)
        port = _extract_port_from_host(request_host) or str(request.get_port() or "")
        default_port = "443" if scheme == "https" else "80"
        if (
            port
            and port != default_port
            and not _host_has_explicit_port(host)
            and _is_local_like_host(request_host)
        ):
            host = f"{host}:{port}"

    query_string = ""
    if query:
        query_string = f"?{urlencode(query, doseq=True)}"
    return f"{scheme}://{host}{normalized_path}{query_string}"
