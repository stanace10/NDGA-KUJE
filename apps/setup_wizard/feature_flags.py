from __future__ import annotations

import sys

from django.conf import settings
from django.core.cache import cache
from django.db.utils import OperationalError, ProgrammingError

from apps.setup_wizard.models import RuntimeFeatureFlags


FLAG_FIELD_MAP = {
    "CBT_ENABLED": "cbt_enabled",
    "ELECTION_ENABLED": "election_enabled",
    "OFFLINE_MODE_ENABLED": "offline_mode_enabled",
    "LOCKDOWN_ENABLED": "lockdown_enabled",
}


def get_runtime_feature_flags():
    cache_key = "setup_wizard:runtime_feature_flags:v1"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached
    flags = dict(settings.FEATURE_FLAGS)
    if "test" in sys.argv:
        return flags
    try:
        row = RuntimeFeatureFlags.get_solo()
    except (OperationalError, ProgrammingError):
        return flags
    for key, field_name in FLAG_FIELD_MAP.items():
        flags[key] = bool(getattr(row, field_name))
    cache.set(cache_key, flags, 3)
    return flags


def get_feature_flag(flag_name, default=False):
    return bool(get_runtime_feature_flags().get(flag_name, default))
