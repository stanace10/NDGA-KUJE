from urllib.parse import urlencode

from django.conf import settings


def normalize_host(host):
    return (host or "").split(":")[0].lower()


def current_portal_key(request):
    host_obj = getattr(request, "host", None)
    if host_obj is not None and host_obj.name in settings.PORTAL_SUBDOMAINS:
        return host_obj.name

    req_host = normalize_host(request.get_host())
    for key, configured_host in settings.PORTAL_SUBDOMAINS.items():
        if req_host == normalize_host(configured_host):
            return key

    if req_host in {"localhost", "127.0.0.1", "[::1]", "testserver"}:
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
            return host.rsplit("]:", 1)[1]
        return ""
    if host.count(":") == 1:
        maybe_port = host.rsplit(":", 1)[1]
        if maybe_port.isdigit():
            return maybe_port
    return ""


def build_portal_url(request, portal_key, path="/", query=None):
    host = settings.PORTAL_SUBDOMAINS.get(portal_key, settings.PORTAL_SUBDOMAINS["landing"])
    scheme = "https" if request.is_secure() else "http"
    request_host = request.get_host()
    port = _extract_port_from_host(request_host) or str(request.get_port() or "")
    default_port = "443" if scheme == "https" else "80"
    if port and port != default_port and not _host_has_explicit_port(host):
        host = f"{host}:{port}"
    if not path.startswith("/"):
        path = f"/{path}"
    query_string = ""
    if query:
        query_string = f"?{urlencode(query, doseq=True)}"
    return f"{scheme}://{host}{path}{query_string}"
