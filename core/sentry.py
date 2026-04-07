from __future__ import annotations

import importlib.util

from django.core.exceptions import ImproperlyConfigured


def initialize_sentry(*, env, default_environment):
    sentry_dsn = env("SENTRY_DSN", default="").strip()
    if not sentry_dsn:
        return

    if importlib.util.find_spec("sentry_sdk") is None:
        raise ImproperlyConfigured("SENTRY_DSN is set but sentry-sdk is not installed.")

    import sentry_sdk
    from sentry_sdk.integrations.celery import CeleryIntegration
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.redis import RedisIntegration

    sentry_sdk.init(
        dsn=sentry_dsn,
        environment=env("SENTRY_ENVIRONMENT", default=default_environment),
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
