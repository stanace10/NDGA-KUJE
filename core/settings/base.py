import os
from pathlib import Path
import sys

from celery.schedules import crontab
import environ

ROOT_DIR = Path(__file__).resolve().parents[2]
APPS_DIR = ROOT_DIR / "apps"

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    CBT_ENABLED=(bool, False),
    ELECTION_ENABLED=(bool, False),
    OFFLINE_MODE_ENABLED=(bool, True),
    LOCKDOWN_ENABLED=(bool, True),
    GRADE_OVERRIDE_REQUIRES_ELEVATED_APPROVAL=(bool, False),
    PRINCIPAL_OVERRIDE_ENABLED=(bool, True),
    NOTIFICATIONS_EMAIL_PROVIDER=(str, "console"),
    NOTIFICATIONS_FROM_EMAIL=(str, "no-reply@ndgakuje.org"),
    BREVO_API_KEY=(str, ""),
    BREVO_SENDER_NAME=(str, "NDGA"),
    PAYMENT_GATEWAY_PROVIDER=(str, "PAYSTACK"),
    PAYSTACK_PUBLIC_KEY=(str, ""),
    PAYSTACK_SECRET_KEY=(str, ""),
    PAYSTACK_WEBHOOK_SECRET=(str, ""),
    PAYSTACK_API_BASE_URL=(str, "https://api.paystack.co"),
    FLUTTERWAVE_PUBLIC_KEY=(str, ""),
    FLUTTERWAVE_SECRET_KEY=(str, ""),
    FLUTTERWAVE_ENCRYPTION_KEY=(str, ""),
    FLUTTERWAVE_API_BASE_URL=(str, "https://api.flutterwave.com/v3"),
    REMITTA_MERCHANT_ID=(str, ""),
    REMITTA_SERVICE_TYPE_ID=(str, ""),
    REMITTA_API_KEY=(str, ""),
    REMITTA_CHECKOUT_URL=(str, "https://login.remita.net/remita/ecomm/finalize.reg"),
    REMITTA_VERIFY_URL_TEMPLATE=(str, ""),
    MOBILE_CAPTURE_PUBLIC_BASE_URL=(str, ""),
    PAYMENT_GATEWAY_CALLBACK_URL=(str, ""),
    PAYMENT_GATEWAY_TIMEOUT_SECONDS=(int, 12),
    WHATSAPP_PROVIDER=(str, "disabled"),
    WHATSAPP_GRAPH_API_BASE_URL=(str, "https://graph.facebook.com/v23.0"),
    WHATSAPP_ACCESS_TOKEN=(str, ""),
    WHATSAPP_PHONE_NUMBER_ID=(str, ""),
    FINANCE_REMINDER_BEAT_INTERVAL_SECONDS=(int, 3600),
    FINANCE_REMINDER_DAYS_AHEAD=(int, 3),
    LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS=(int, 8),
    LOCKDOWN_INACTIVITY_TIMEOUT_SECONDS=(int, 90),
    SYNC_LOCAL_NODE_ENABLED=(bool, True),
    SYNC_LOCAL_NODE_ID=(str, "ndga-cbt-local-node"),
    SYNC_CLOUD_ENDPOINT=(str, ""),
    SYNC_ENDPOINT_AUTH_TOKEN=(str, ""),
    SYNC_MAX_RETRIES=(int, 8),
    SYNC_RETRY_BASE_SECONDS=(int, 20),
    SYNC_RETRY_MAX_SECONDS=(int, 1800),
    SYNC_CONNECTIVITY_TIMEOUT_SECONDS=(int, 2),
    SYNC_CONNECTIVITY_CACHE_TTL_SECONDS=(int, 5),
    SYNC_NODE_ROLE=(str, "CLOUD"),
    SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY=(bool, True),
    SYNC_MANUAL_MODE=(bool, True),
    SYNC_AUTO_ON_REQUEST=(bool, False),
    SYNC_AUTO_MIN_INTERVAL_SECONDS=(int, 5),
    SYNC_AUTO_BATCH_LIMIT=(int, 60),
    SYNC_PROCESS_BEAT_ENABLED=(bool, False),
    SYNC_PROCESS_BEAT_INTERVAL_SECONDS=(int, 5),
    SYNC_PULL_ENABLED=(bool, True),
    SYNC_PULL_BATCH_LIMIT=(int, 200),
    SYNC_PULL_MAX_PAGES_PER_RUN=(int, 4),
    SYNC_PULL_TIMEOUT_SECONDS=(int, 5),
    SYNC_PULL_BEAT_ENABLED=(bool, False),
    SYNC_PULL_BEAT_INTERVAL_SECONDS=(int, 5),
    LAN_RUNTIME_RESTRICT_PORTALS=(bool, False),
    CLOUD_STAFF_OPERATIONS_LAN_ONLY=(bool, False),
    MONITOR_CELERY_QUEUE_NAMES=(str, "celery"),
    BACKUP_PG_ENABLED=(bool, False),
    BACKUP_PG_OUTPUT_DIR=(str, "backups/postgres"),
    BACKUP_PG_S3_ENABLED=(bool, False),
    BACKUP_PG_S3_BUCKET=(str, ""),
    BACKUP_PG_S3_PREFIX=(str, "nightly"),
    BACKUP_PG_KEEP_LOCAL_COUNT=(int, 14),
    BACKUP_PG_BEAT_HOUR=(int, 2),
    BACKUP_PG_BEAT_MINUTE=(int, 0),
    CHANNEL_LAYER_CAPACITY=(int, 1500),
    CHANNEL_LAYER_EXPIRY_SECONDS=(int, 60),
    CHANNEL_LAYER_GROUP_EXPIRY_SECONDS=(int, 86400),
    CELERY_WORKER_PREFETCH_MULTIPLIER=(int, 1),
    CELERY_BROKER_POOL_LIMIT=(int, 50),
    CELERY_TASK_ACKS_LATE=(bool, True),
    CELERY_TASK_REJECT_ON_WORKER_LOST=(bool, True),
    CELERY_WORKER_MAX_TASKS_PER_CHILD=(int, 500),
    CELERY_REDIS_VISIBILITY_TIMEOUT_SECONDS=(int, 21600),
    CELERY_RESULT_EXPIRES_SECONDS=(int, 86400),
    RATE_LIMIT_ENABLED=(bool, True),
    RATE_LIMIT_LOGIN_LIMIT=(int, 12),
    RATE_LIMIT_LOGIN_WINDOW_SECONDS=(int, 60),
    RATE_LIMIT_PASSWORD_RESET_LIMIT=(int, 8),
    RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS=(int, 300),
    RATE_LIMIT_IT_SENSITIVE_LIMIT=(int, 30),
    RATE_LIMIT_IT_SENSITIVE_WINDOW_SECONDS=(int, 300),
    RATE_LIMIT_SENSITIVE_LIMIT=(int, 60),
    RATE_LIMIT_SENSITIVE_WINDOW_SECONDS=(int, 300),
    UPLOAD_MAX_IMAGE_MB=(int, 8),
    UPLOAD_MAX_DOCUMENT_MB=(int, 12),
    UPLOAD_MAX_RECEIPT_MB=(int, 10),
    UPLOAD_MAX_EVIDENCE_MB=(int, 20),
    UPLOAD_MAX_JSON_MB=(int, 15),
    AUDIT_RETENTION_DAYS=(int, 2555),
    CACHE_BACKEND=(str, "redis"),
    CHANNEL_LAYER_BACKEND=(str, "redis"),
    NDGA_LOCAL_SIMPLE_HOST_MODE=(bool, False),
    GOOGLE_SITE_VERIFICATION=(str, ""),
    GOOGLE_ANALYTICS_ID=(str, ""),
    GOOGLE_ADS_ID=(str, ""),
    GOOGLE_ADSENSE_CLIENT_ID=(str, ""),
    SEO_SITE_NAME=(str, "NDGA Portal"),
    SEO_ORGANIZATION_NAME=(str, "Notre Dame Girls Academy"),
    SEO_DEFAULT_DESCRIPTION=(str, "Portal access for students, staff, academic records, finance, CBT, and school operations at Notre Dame Girls Academy, Kuje Abuja."),
    AI_PROVIDER_ORDER=(str, "openai,groq,gemini,huggingface"),
    GROQ_API_KEY=(str, ""),
    GROQ_MODEL=(str, "llama-3.1-8b-instant"),
    GEMINI_API_KEY=(str, ""),
    GEMINI_MODEL=(str, "gemini-2.5-flash-lite"),
    HUGGINGFACE_API_KEY=(str, ""),
    HUGGINGFACE_MODEL=(str, "google/gemma-2-2b-it"),
)
_configured_env_file = os.environ.get("NDGA_ENV_FILE", "").strip()
_env_candidates: list[Path] = []
if _configured_env_file:
    configured_path = Path(_configured_env_file)
    if not configured_path.is_absolute():
        configured_path = ROOT_DIR / configured_path
    _env_candidates.append(configured_path)
_env_candidates.extend(
    [
        ROOT_DIR / ".env",
        ROOT_DIR / ".env.lan",
        ROOT_DIR / ".env.cloud",
    ]
)
for _env_path in _env_candidates:
    if _env_path.exists():
        environ.Env.read_env(_env_path)
        break

SECRET_KEY = env(
    "DJANGO_SECRET_KEY",
    default="ndga-dev-only-secret-key-change-before-production",
)
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=["localhost", "127.0.0.1", "[::1]"],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=["http://localhost:8000", "http://127.0.0.1:8000"],
)

INSTALLED_APPS = [
    "django_hosts",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "channels",
    "django_htmx",
    "guardian",
    "apps.accounts.apps.AccountsConfig",
    "apps.tenancy.apps.TenancyConfig",
    "apps.setup_wizard.apps.SetupWizardConfig",
    "apps.academics.apps.AcademicsConfig",
    "apps.attendance.apps.AttendanceConfig",
    "apps.results.apps.ResultsConfig",
    "apps.cbt.apps.CbtConfig",
    "apps.sync.apps.SyncConfig",
    "apps.elections.apps.ElectionsConfig",
    "apps.finance.apps.FinanceConfig",
    "apps.pdfs.apps.PdfsConfig",
    "apps.notifications.apps.NotificationsConfig",
    "apps.audit.apps.AuditConfig",
    "apps.dashboard.apps.DashboardConfig",
]

MIDDLEWARE = [
    "django_hosts.middleware.HostsRequestMiddleware",
    "core.security.LocalNetworkHostCompatibilityMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "core.security.RequestRateLimitMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "apps.tenancy.middleware.PortalAccessMiddleware",
    "apps.cbt.middleware.CBTLockdownMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "core.security.StrictSecurityHeadersMiddleware",
    "django_hosts.middleware.HostsResponseMiddleware",
]

ROOT_URLCONF = "core.urls"
ROOT_HOSTCONF = "core.hosts"
DEFAULT_HOST = "landing"
WSGI_APPLICATION = "core.wsgi.application"
ASGI_APPLICATION = "core.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [ROOT_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.platform_context",
            ],
        },
    },
]

LOCAL_POSTGRES_PORT = str(env.int("NDGA_POSTGRES_PORT", default=5433))
DATABASE_URL = env("DATABASE_URL", default="").strip()
if DATABASE_URL:
    DATABASES = {
        "default": env.db(
            "DATABASE_URL",
            default=f"postgresql://ndga:ndga@127.0.0.1:{LOCAL_POSTGRES_PORT}/ndga",
        )
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": env(
                "DB_ENGINE",
                default="django.db.backends.postgresql",
            ),
            "NAME": env("DB_NAME", default="ndga"),
            "USER": env("DB_USER", default="ndga"),
            "PASSWORD": env("DB_PASSWORD", default="ndga"),
            "HOST": env("DB_HOST", default="127.0.0.1"),
            "PORT": env("DB_PORT", default=LOCAL_POSTGRES_PORT),
        }
    }
DATABASES["default"]["CONN_MAX_AGE"] = env.int(
    "DATABASE_CONN_MAX_AGE",
    default=env.int("CONN_MAX_AGE", default=60),
)

_cache_backend = env("CACHE_BACKEND", default="redis").strip().lower()
if _cache_backend == "locmem":
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "ndga-local-cache",
        }
    }
else:
    CACHES = {
        "default": {
            "BACKEND": "django.core.cache.backends.redis.RedisCache",
            "LOCATION": env("REDIS_CACHE_URL", default="redis://127.0.0.1:6379/1"),
        }
    }

_channel_layer_backend = env("CHANNEL_LAYER_BACKEND", default="redis").strip().lower()
if _channel_layer_backend == "inmemory":
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels.layers.InMemoryChannelLayer",
        }
    }
else:
    CHANNEL_LAYERS = {
        "default": {
            "BACKEND": "channels_redis.core.RedisChannelLayer",
            "CONFIG": {
                "hosts": [env("CHANNEL_REDIS_URL", default="redis://127.0.0.1:6379/2")],
                "capacity": env.int("CHANNEL_LAYER_CAPACITY", default=1500),
                "expiry": env.int("CHANNEL_LAYER_EXPIRY_SECONDS", default=60),
                "group_expiry": env.int("CHANNEL_LAYER_GROUP_EXPIRY_SECONDS", default=86400),
            },
        }
    }

CELERY_BROKER_URL = env("CELERY_BROKER_URL", default="redis://127.0.0.1:6379/0")
CELERY_RESULT_BACKEND = env("CELERY_RESULT_BACKEND", default=CELERY_BROKER_URL)
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = env("DJANGO_TIME_ZONE", default="Africa/Lagos")
CELERY_TASK_ACKS_LATE = env.bool("CELERY_TASK_ACKS_LATE", default=True)
CELERY_TASK_REJECT_ON_WORKER_LOST = env.bool("CELERY_TASK_REJECT_ON_WORKER_LOST", default=True)
CELERY_WORKER_PREFETCH_MULTIPLIER = env.int("CELERY_WORKER_PREFETCH_MULTIPLIER", default=1)
CELERY_BROKER_POOL_LIMIT = env.int("CELERY_BROKER_POOL_LIMIT", default=50)
CELERY_WORKER_MAX_TASKS_PER_CHILD = env.int("CELERY_WORKER_MAX_TASKS_PER_CHILD", default=500)
CELERY_TASK_TRACK_STARTED = True
CELERY_BROKER_CONNECTION_RETRY_ON_STARTUP = True
CELERY_BROKER_TRANSPORT_OPTIONS = {
    "visibility_timeout": env.int("CELERY_REDIS_VISIBILITY_TIMEOUT_SECONDS", default=21600),
}
CELERY_RESULT_EXPIRES = env.int("CELERY_RESULT_EXPIRES_SECONDS", default=86400)

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = env("DJANGO_TIME_ZONE", default="Africa/Lagos")
USE_I18N = True
USE_TZ = True

STATIC_URL = "/static/"
STATIC_ROOT = ROOT_DIR / "staticfiles"
STATICFILES_DIRS = [ROOT_DIR / "static"]
MEDIA_URL = "/media/"
MEDIA_ROOT = ROOT_DIR / "media"

STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
AUTH_USER_MODEL = "accounts.User"
ANONYMOUS_USER_NAME = "ndga-anonymous"

AUTHENTICATION_BACKENDS = (
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
)

LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "accounts:role-redirect"
LOGOUT_REDIRECT_URL = "dashboard:landing"

FEATURE_FLAGS = {
    "CBT_ENABLED": env.bool("CBT_ENABLED"),
    "ELECTION_ENABLED": env.bool("ELECTION_ENABLED"),
    "OFFLINE_MODE_ENABLED": env.bool("OFFLINE_MODE_ENABLED"),
    "LOCKDOWN_ENABLED": env.bool("LOCKDOWN_ENABLED"),
}

RESULTS_POLICY = {
    "GRADE_OVERRIDE_REQUIRES_ELEVATED_APPROVAL": env.bool(
        "GRADE_OVERRIDE_REQUIRES_ELEVATED_APPROVAL"
    ),
    "PRINCIPAL_OVERRIDE_ENABLED": env.bool("PRINCIPAL_OVERRIDE_ENABLED"),
}

IT_BOOTSTRAP_USERNAME = env("IT_BOOTSTRAP_USERNAME", default="admin@ndgakuje.org")
NDGA_BASE_DOMAIN = env("NDGA_BASE_DOMAIN", default="ndgakuje.org")
NDGA_LOCAL_SIMPLE_HOST_MODE = env.bool("NDGA_LOCAL_SIMPLE_HOST_MODE", default=False)
if NDGA_LOCAL_SIMPLE_HOST_MODE and "*" not in ALLOWED_HOSTS:
    ALLOWED_HOSTS = ["*"]

_session_cookie_domain = env("SESSION_COOKIE_DOMAIN", default="")
if NDGA_LOCAL_SIMPLE_HOST_MODE:
    SESSION_COOKIE_DOMAIN = None
elif _session_cookie_domain:
    SESSION_COOKIE_DOMAIN = _session_cookie_domain
else:
    normalized_base_domain = (NDGA_BASE_DOMAIN or "").strip().lower()
    if normalized_base_domain and normalized_base_domain not in {"localhost", "127.0.0.1", "[::1]"}:
        SESSION_COOKIE_DOMAIN = f".{normalized_base_domain}"
    else:
        SESSION_COOKIE_DOMAIN = None
if "test" in sys.argv:
    SESSION_COOKIE_DOMAIN = None
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False
CSRF_COOKIE_DOMAIN = SESSION_COOKIE_DOMAIN
CSRF_FAILURE_VIEW = "core.csrf.csrf_failure_view"
SESSION_COOKIE_SECURE = env.bool("SESSION_COOKIE_SECURE", default=not DEBUG)
CSRF_COOKIE_SECURE = env.bool("CSRF_COOKIE_SECURE", default=not DEBUG)

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = env(
    "DJANGO_SECURE_REFERRER_POLICY",
    default="strict-origin-when-cross-origin",
)
X_FRAME_OPTIONS = "DENY"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"

PARENT_HOST = NDGA_BASE_DOMAIN
PORTAL_SUBDOMAINS = {
    "landing": env("NDGA_LANDING_HOST", default=NDGA_BASE_DOMAIN),
    "portal": env("NDGA_PORTAL_HOST", default=f"portal.{NDGA_BASE_DOMAIN}"),
    "student": env("NDGA_STUDENT_HOST", default=f"student.{NDGA_BASE_DOMAIN}"),
    "staff": env("NDGA_STAFF_HOST", default=f"staff.{NDGA_BASE_DOMAIN}"),
    "it": env("NDGA_IT_HOST", default=f"it.{NDGA_BASE_DOMAIN}"),
    "bursar": env("NDGA_BURSAR_HOST", default=f"bursar.{NDGA_BASE_DOMAIN}"),
    "vp": env("NDGA_VP_HOST", default=f"vp.{NDGA_BASE_DOMAIN}"),
    "principal": env("NDGA_PRINCIPAL_HOST", default=f"principal.{NDGA_BASE_DOMAIN}"),
    "cbt": env("NDGA_CBT_HOST", default=f"cbt.{NDGA_BASE_DOMAIN}"),
    "election": env("NDGA_ELECTION_HOST", default=f"election.{NDGA_BASE_DOMAIN}"),
}
FRESH_LOGIN_REQUIRED_PORTALS = ("cbt", "election")
NOTIFICATIONS_EMAIL_PROVIDER = env("NOTIFICATIONS_EMAIL_PROVIDER", default="console")
NOTIFICATIONS_FROM_EMAIL = env(
    "NOTIFICATIONS_FROM_EMAIL",
    default="no-reply@ndgakuje.org",
)
BREVO_API_KEY = env("BREVO_API_KEY", default="")
BREVO_SENDER_NAME = env("BREVO_SENDER_NAME", default="NDGA")
PAYMENT_GATEWAY_PROVIDER = env("PAYMENT_GATEWAY_PROVIDER", default="PAYSTACK")
PAYSTACK_PUBLIC_KEY = env("PAYSTACK_PUBLIC_KEY", default="")
PAYSTACK_SECRET_KEY = env("PAYSTACK_SECRET_KEY", default="")
PAYSTACK_WEBHOOK_SECRET = env("PAYSTACK_WEBHOOK_SECRET", default="")
PAYSTACK_API_BASE_URL = env("PAYSTACK_API_BASE_URL", default="https://api.paystack.co")
FLUTTERWAVE_PUBLIC_KEY = env("FLUTTERWAVE_PUBLIC_KEY", default="")
FLUTTERWAVE_SECRET_KEY = env("FLUTTERWAVE_SECRET_KEY", default="")
FLUTTERWAVE_ENCRYPTION_KEY = env("FLUTTERWAVE_ENCRYPTION_KEY", default="")
FLUTTERWAVE_API_BASE_URL = env("FLUTTERWAVE_API_BASE_URL", default="https://api.flutterwave.com/v3")
REMITTA_MERCHANT_ID = env("REMITTA_MERCHANT_ID", default="")
REMITTA_SERVICE_TYPE_ID = env("REMITTA_SERVICE_TYPE_ID", default="")
REMITTA_API_KEY = env("REMITTA_API_KEY", default="")
REMITTA_CHECKOUT_URL = env(
    "REMITTA_CHECKOUT_URL",
    default="https://login.remita.net/remita/ecomm/finalize.reg",
)
REMITTA_VERIFY_URL_TEMPLATE = env("REMITTA_VERIFY_URL_TEMPLATE", default="")
MOBILE_CAPTURE_PUBLIC_BASE_URL = (
    env("MOBILE_CAPTURE_PUBLIC_BASE_URL", default="").strip().rstrip("/")
)
PAYMENT_GATEWAY_CALLBACK_URL = env("PAYMENT_GATEWAY_CALLBACK_URL", default="")
PAYMENT_GATEWAY_TIMEOUT_SECONDS = env.int("PAYMENT_GATEWAY_TIMEOUT_SECONDS", default=12)
WHATSAPP_PROVIDER = env("WHATSAPP_PROVIDER", default="disabled")
WHATSAPP_GRAPH_API_BASE_URL = env(
    "WHATSAPP_GRAPH_API_BASE_URL",
    default="https://graph.facebook.com/v23.0",
)
WHATSAPP_ACCESS_TOKEN = env("WHATSAPP_ACCESS_TOKEN", default="")
WHATSAPP_PHONE_NUMBER_ID = env("WHATSAPP_PHONE_NUMBER_ID", default="")
FINANCE_REMINDER_BEAT_INTERVAL_SECONDS = env.int("FINANCE_REMINDER_BEAT_INTERVAL_SECONDS", default=3600)
FINANCE_REMINDER_DAYS_AHEAD = env.int("FINANCE_REMINDER_DAYS_AHEAD", default=3)
LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS = env.int(
    "LOCKDOWN_HEARTBEAT_INTERVAL_SECONDS",
    default=8,
)
LOCKDOWN_INACTIVITY_TIMEOUT_SECONDS = env.int(
    "LOCKDOWN_INACTIVITY_TIMEOUT_SECONDS",
    default=90,
)
SYNC_LOCAL_NODE_ENABLED = env.bool("SYNC_LOCAL_NODE_ENABLED", default=True)
SYNC_LOCAL_NODE_ID = env("SYNC_LOCAL_NODE_ID", default="ndga-cbt-local-node")
SYNC_CLOUD_ENDPOINT = env("SYNC_CLOUD_ENDPOINT", default="")
SYNC_ENDPOINT_AUTH_TOKEN = env("SYNC_ENDPOINT_AUTH_TOKEN", default="")
SYNC_MAX_RETRIES = env.int("SYNC_MAX_RETRIES", default=8)
SYNC_RETRY_BASE_SECONDS = env.int("SYNC_RETRY_BASE_SECONDS", default=20)
SYNC_RETRY_MAX_SECONDS = env.int("SYNC_RETRY_MAX_SECONDS", default=1800)
_local_sync_connectivity_timeout_default = 1 if NDGA_LOCAL_SIMPLE_HOST_MODE else 2
_local_sync_connectivity_cache_ttl_default = 60 if NDGA_LOCAL_SIMPLE_HOST_MODE else 5
_local_sync_auto_on_request_default = not NDGA_LOCAL_SIMPLE_HOST_MODE
SYNC_CONNECTIVITY_TIMEOUT_SECONDS = env.int(
    "SYNC_CONNECTIVITY_TIMEOUT_SECONDS",
    default=_local_sync_connectivity_timeout_default,
)
SYNC_CONNECTIVITY_CACHE_TTL_SECONDS = env.int(
    "SYNC_CONNECTIVITY_CACHE_TTL_SECONDS",
    default=_local_sync_connectivity_cache_ttl_default,
)
SYNC_NODE_ROLE = env("SYNC_NODE_ROLE", default="CLOUD").strip().upper()
SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY = env.bool(
    "SYNC_ENFORCE_ACTIVE_SESSION_AUTHORITY",
    default=True,
)
SYNC_MANUAL_MODE = env.bool("SYNC_MANUAL_MODE", default=True)
SYNC_AUTO_ON_REQUEST = env.bool(
    "SYNC_AUTO_ON_REQUEST",
    default=False,
)
SYNC_AUTO_MIN_INTERVAL_SECONDS = env.int("SYNC_AUTO_MIN_INTERVAL_SECONDS", default=5)
SYNC_AUTO_BATCH_LIMIT = env.int("SYNC_AUTO_BATCH_LIMIT", default=60)
SYNC_PROCESS_BEAT_ENABLED = env.bool(
    "SYNC_PROCESS_BEAT_ENABLED",
    default=False,
)
SYNC_PROCESS_BEAT_INTERVAL_SECONDS = env.int("SYNC_PROCESS_BEAT_INTERVAL_SECONDS", default=5)
SYNC_PULL_ENABLED = env.bool("SYNC_PULL_ENABLED", default=True)
SYNC_PULL_BATCH_LIMIT = env.int("SYNC_PULL_BATCH_LIMIT", default=200)
SYNC_PULL_MAX_PAGES_PER_RUN = env.int("SYNC_PULL_MAX_PAGES_PER_RUN", default=4)
SYNC_PULL_TIMEOUT_SECONDS = env.int("SYNC_PULL_TIMEOUT_SECONDS", default=5)
SYNC_PULL_BEAT_ENABLED = env.bool(
    "SYNC_PULL_BEAT_ENABLED",
    default=False,
)
SYNC_PULL_BEAT_INTERVAL_SECONDS = env.int("SYNC_PULL_BEAT_INTERVAL_SECONDS", default=5)
LAN_RUNTIME_RESTRICT_PORTALS = env.bool(
    "LAN_RUNTIME_RESTRICT_PORTALS",
    default=False,
)
CLOUD_STAFF_OPERATIONS_LAN_ONLY = env.bool(
    "CLOUD_STAFF_OPERATIONS_LAN_ONLY",
    default=(SYNC_NODE_ROLE == "CLOUD"),
)
if "test" in sys.argv:
    LAN_RUNTIME_RESTRICT_PORTALS = False
    CLOUD_STAFF_OPERATIONS_LAN_ONLY = False
MONITOR_CELERY_QUEUE_NAMES = [
    item.strip()
    for item in env("MONITOR_CELERY_QUEUE_NAMES", default="celery").split(",")
    if item.strip()
]
BACKUP_PG_ENABLED = env.bool("BACKUP_PG_ENABLED", default=False)
BACKUP_PG_OUTPUT_DIR = env("BACKUP_PG_OUTPUT_DIR", default="backups/postgres").strip() or "backups/postgres"
BACKUP_PG_S3_ENABLED = env.bool("BACKUP_PG_S3_ENABLED", default=False)
BACKUP_PG_S3_BUCKET = env("BACKUP_PG_S3_BUCKET", default="").strip()
BACKUP_PG_S3_PREFIX = env("BACKUP_PG_S3_PREFIX", default="nightly").strip().strip("/")
BACKUP_PG_KEEP_LOCAL_COUNT = max(env.int("BACKUP_PG_KEEP_LOCAL_COUNT", default=14), 1)
BACKUP_PG_BEAT_HOUR = max(min(env.int("BACKUP_PG_BEAT_HOUR", default=2), 23), 0)
BACKUP_PG_BEAT_MINUTE = max(min(env.int("BACKUP_PG_BEAT_MINUTE", default=0), 59), 0)

CELERY_BEAT_SCHEDULE = {
    "finance-send-scheduled-fee-reminders": {
        "task": "finance.send_scheduled_fee_reminders",
        "schedule": float(max(FINANCE_REMINDER_BEAT_INTERVAL_SECONDS, 300)),
        "args": (FINANCE_REMINDER_DAYS_AHEAD,),
    },
}
if SYNC_PROCESS_BEAT_ENABLED:
    CELERY_BEAT_SCHEDULE["sync-process-queue-batch"] = {
        "task": "sync.process_queue_batch",
        "schedule": float(max(SYNC_PROCESS_BEAT_INTERVAL_SECONDS, 1)),
        "args": (100,),
    }
if SYNC_PULL_BEAT_ENABLED:
    CELERY_BEAT_SCHEDULE["sync-pull-remote-outbox"] = {
        "task": "sync.pull_remote_outbox",
        "schedule": float(max(SYNC_PULL_BEAT_INTERVAL_SECONDS, 1)),
        "args": (SYNC_PULL_BATCH_LIMIT, SYNC_PULL_MAX_PAGES_PER_RUN),
    }
    CELERY_BEAT_SCHEDULE["sync-pull-cbt-content"] = {
        "task": "sync.pull_cbt_content",
        "schedule": float(max(SYNC_PULL_BEAT_INTERVAL_SECONDS, 1)),
        "args": (SYNC_PULL_BATCH_LIMIT, SYNC_PULL_MAX_PAGES_PER_RUN),
    }
if BACKUP_PG_ENABLED:
    CELERY_BEAT_SCHEDULE["setup-nightly-postgres-backup"] = {
        "task": "setup.nightly_pg_backup",
        "schedule": crontab(hour=BACKUP_PG_BEAT_HOUR, minute=BACKUP_PG_BEAT_MINUTE),
    }
RATE_LIMIT_ENABLED = env.bool("RATE_LIMIT_ENABLED", default=True)
if "test" in sys.argv:
    RATE_LIMIT_ENABLED = False

RATE_LIMIT_RULES = (
    {
        "name": "auth_login",
        "path_prefix": "/auth/login/",
        "methods": ("POST",),
        "scope": "ip",
        "limit": env.int("RATE_LIMIT_LOGIN_LIMIT", default=12),
        "window_seconds": env.int("RATE_LIMIT_LOGIN_WINDOW_SECONDS", default=60),
    },
    {
        "name": "password_reset_request",
        "path_prefix": "/auth/password/reset/",
        "methods": ("POST",),
        "scope": "ip",
        "limit": env.int("RATE_LIMIT_PASSWORD_RESET_LIMIT", default=8),
        "window_seconds": env.int(
            "RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS",
            default=300,
        ),
    },
    {
        "name": "password_reset_confirm",
        "path_prefix": "/auth/password/reset/confirm/",
        "methods": ("POST",),
        "scope": "ip",
        "limit": env.int("RATE_LIMIT_PASSWORD_RESET_LIMIT", default=8),
        "window_seconds": env.int(
            "RATE_LIMIT_PASSWORD_RESET_WINDOW_SECONDS",
            default=300,
        ),
    },
    {
        "name": "it_sensitive",
        "path_prefix": "/auth/it/",
        "methods": ("POST",),
        "scope": "user_or_ip",
        "limit": env.int("RATE_LIMIT_IT_SENSITIVE_LIMIT", default=30),
        "window_seconds": env.int(
            "RATE_LIMIT_IT_SENSITIVE_WINDOW_SECONDS",
            default=300,
        ),
    },
    {
        "name": "session_term_controls",
        "path_prefix": "/setup/session-term/",
        "methods": ("POST",),
        "scope": "user_or_ip",
        "limit": env.int("RATE_LIMIT_SENSITIVE_LIMIT", default=60),
        "window_seconds": env.int(
            "RATE_LIMIT_SENSITIVE_WINDOW_SECONDS",
            default=300,
        ),
    },
    {
        "name": "finance_bursar_mutation",
        "path_prefix": "/finance/bursar/",
        "methods": ("POST",),
        "scope": "user_or_ip",
        "limit": env.int("RATE_LIMIT_SENSITIVE_LIMIT", default=60),
        "window_seconds": env.int(
            "RATE_LIMIT_SENSITIVE_WINDOW_SECONDS",
            default=300,
        ),
    },
)

SECURITY_RESPONSE_HEADERS = {
    "Content-Security-Policy": (
        "default-src 'self'; "
        "base-uri 'self'; "
        "object-src 'none'; "
        "frame-ancestors 'self'; "
        "img-src 'self' data: blob:; "
        "font-src 'self' data:; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:; "
        "frame-src 'self' https:; "
        "form-action 'self'"
    ),
    "Permissions-Policy": "camera=(self), microphone=(), geolocation=()",
    "Cross-Origin-Resource-Policy": "same-site",
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": SECURE_REFERRER_POLICY,
}

UPLOAD_SECURITY = {
    "MAX_IMAGE_MB": env.int("UPLOAD_MAX_IMAGE_MB", default=8),
    "MAX_DOCUMENT_MB": env.int("UPLOAD_MAX_DOCUMENT_MB", default=12),
    "MAX_RECEIPT_MB": env.int("UPLOAD_MAX_RECEIPT_MB", default=10),
    "MAX_EVIDENCE_MB": env.int("UPLOAD_MAX_EVIDENCE_MB", default=20),
    "MAX_JSON_MB": env.int("UPLOAD_MAX_JSON_MB", default=15),
    "MAX_SIM_BUNDLE_MB": env.int("UPLOAD_MAX_SIM_BUNDLE_MB", default=180),
}
_upload_request_limit_mb = max(
    env.int("UPLOAD_MAX_REQUEST_MB", default=24),
    UPLOAD_SECURITY["MAX_IMAGE_MB"] + 4,
)
DATA_UPLOAD_MAX_MEMORY_SIZE = _upload_request_limit_mb * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = DATA_UPLOAD_MAX_MEMORY_SIZE

AUDIT_RETENTION_DAYS = env.int("AUDIT_RETENTION_DAYS", default=2555)


