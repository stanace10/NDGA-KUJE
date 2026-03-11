from .base import *  # noqa

DEBUG = env.bool("DJANGO_DEBUG", default=True)
NDGA_LOCAL_SIMPLE_HOST_MODE = env.bool("NDGA_LOCAL_SIMPLE_HOST_MODE", default=True)
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[
        "localhost",
        "127.0.0.1",
        "[::1]",
        ".ndga.local",
        "testserver",
    ],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[
        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "http://*.ndga.local:8000",
    ],
)

EMAIL_BACKEND = env(
    "EMAIL_BACKEND", default="django.core.mail.backends.console.EmailBackend"
)

STORAGES["staticfiles"] = {
    "BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"
}

# COOP is only meaningful on trustworthy origins (HTTPS/localhost).
# Disable it in local HTTP host testing to avoid noisy browser warnings.
SECURE_CROSS_ORIGIN_OPENER_POLICY = None

# Local dev CSP relaxes script eval for Alpine interactive templates.
_local_csp = SECURITY_RESPONSE_HEADERS.get("Content-Security-Policy", "")
if "script-src 'self' 'unsafe-inline';" in _local_csp and "'unsafe-eval'" not in _local_csp:
    SECURITY_RESPONSE_HEADERS["Content-Security-Policy"] = _local_csp.replace(
        "script-src 'self' 'unsafe-inline';",
        "script-src 'self' 'unsafe-inline' 'unsafe-eval';",
    )
