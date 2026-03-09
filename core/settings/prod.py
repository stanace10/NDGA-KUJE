from __future__ import annotations

import importlib.util

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa

DEBUG = False

ALLOWED_HOSTS = env.list(
    "DJANGO_ALLOWED_HOSTS",
    default=[
        NDGA_BASE_DOMAIN,
        f".{NDGA_BASE_DOMAIN}",
    ],
)
CSRF_TRUSTED_ORIGINS = env.list(
    "DJANGO_CSRF_TRUSTED_ORIGINS",
    default=[
        f"https://{NDGA_BASE_DOMAIN}",
        f"https://*.{NDGA_BASE_DOMAIN}",
    ],
)

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=31536000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool(
    "DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS",
    default=True,
)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = env(
    "DJANGO_SECURE_REFERRER_POLICY",
    default="strict-origin-when-cross-origin",
)
X_FRAME_OPTIONS = "DENY"

SESSION_COOKIE_AGE = env.int("SESSION_COOKIE_AGE_SECONDS", default=3600 * 12)
CSRF_COOKIE_AGE = env.int("CSRF_COOKIE_AGE_SECONDS", default=3600 * 24)

EMAIL_BACKEND = env(
    "EMAIL_BACKEND",
    default="django.core.mail.backends.smtp.EmailBackend",
)

MEDIA_STORAGE_BACKEND = env("MEDIA_STORAGE_BACKEND", default="filesystem").strip().lower()
if MEDIA_STORAGE_BACKEND not in {"filesystem", "s3", "cloudinary"}:
    raise ImproperlyConfigured(
        "Invalid MEDIA_STORAGE_BACKEND. Use one of: filesystem, s3, cloudinary."
    )

if MEDIA_STORAGE_BACKEND == "s3":
    if importlib.util.find_spec("storages") is None:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE_BACKEND=s3 requires django-storages and boto3."
        )
    AWS_ACCESS_KEY_ID = env("AWS_ACCESS_KEY_ID", default="")
    AWS_SECRET_ACCESS_KEY = env("AWS_SECRET_ACCESS_KEY", default="")
    AWS_STORAGE_BUCKET_NAME = env("AWS_STORAGE_BUCKET_NAME", default="")
    AWS_S3_REGION_NAME = env("AWS_S3_REGION_NAME", default=env("AWS_REGION", default=""))
    AWS_S3_ENDPOINT_URL = env("AWS_S3_ENDPOINT_URL", default="")
    AWS_S3_CUSTOM_DOMAIN = env("AWS_S3_CUSTOM_DOMAIN", default="")
    AWS_S3_FILE_OVERWRITE = env.bool("AWS_S3_FILE_OVERWRITE", default=False)
    AWS_QUERYSTRING_AUTH = env.bool("AWS_QUERYSTRING_AUTH", default=False)
    AWS_DEFAULT_ACL = None
    if not AWS_STORAGE_BUCKET_NAME:
        raise ImproperlyConfigured("AWS_STORAGE_BUCKET_NAME is required for S3 media.")
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN.rstrip('/')}/"
    elif AWS_S3_REGION_NAME:
        MEDIA_URL = (
            f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
        )
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
elif MEDIA_STORAGE_BACKEND == "cloudinary":
    if importlib.util.find_spec("cloudinary_storage") is None:
        raise ImproperlyConfigured(
            "MEDIA_STORAGE_BACKEND=cloudinary requires django-cloudinary-storage."
        )
    cloudinary_name = env("CLOUDINARY_CLOUD_NAME", default="")
    cloudinary_key = env("CLOUDINARY_API_KEY", default="")
    cloudinary_secret = env("CLOUDINARY_API_SECRET", default="")
    if not all([cloudinary_name, cloudinary_key, cloudinary_secret]):
        raise ImproperlyConfigured(
            "CLOUDINARY_CLOUD_NAME, CLOUDINARY_API_KEY, and "
            "CLOUDINARY_API_SECRET are required for Cloudinary media."
        )
    CLOUDINARY_STORAGE = {
        "CLOUD_NAME": cloudinary_name,
        "API_KEY": cloudinary_key,
        "API_SECRET": cloudinary_secret,
        "SECURE": True,
    }
    STORAGES["default"] = {
        "BACKEND": "cloudinary_storage.storage.MediaCloudinaryStorage"
    }
else:
    STORAGES["default"] = {"BACKEND": "django.core.files.storage.FileSystemStorage"}

LOG_LEVEL = env("DJANGO_LOG_LEVEL", default="INFO").upper()
LOG_JSON = env.bool("DJANGO_LOG_JSON", default=True)

if LOG_JSON:
    base_formatter = {
        "format": (
            '{{"timestamp":"{asctime}",'
            '"level":"{levelname}",'
            '"logger":"{name}",'
            '"module":"{module}",'
            '"message":"{message}"}}'
        ),
        "style": "{",
    }
else:
    base_formatter = {
        "format": "[{asctime}] {levelname} {name}: {message}",
        "style": "{",
    }

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": base_formatter,
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {"handlers": ["console"], "level": LOG_LEVEL},
    "loggers": {
        "django": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
        "django.request": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        "apps": {"handlers": ["console"], "level": LOG_LEVEL, "propagate": False},
    },
}

SENTRY_DSN = env("SENTRY_DSN", default="").strip()
if SENTRY_DSN:
    if importlib.util.find_spec("sentry_sdk") is None:
        raise ImproperlyConfigured("SENTRY_DSN is set but sentry-sdk is not installed.")
    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=env("SENTRY_ENVIRONMENT", default="production"),
        release=env("SENTRY_RELEASE", default=""),
        traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
        profiles_sample_rate=env.float("SENTRY_PROFILES_SAMPLE_RATE", default=0.0),
        send_default_pii=False,
        integrations=[
            DjangoIntegration(),
            CeleryIntegration(),
            RedisIntegration(),
        ],
    )
