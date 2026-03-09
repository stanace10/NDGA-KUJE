from __future__ import annotations

import sys

from django.conf import settings
from django.db.utils import OperationalError, ProgrammingError

from apps.setup_wizard.models import RuntimeFeatureFlags


FLAG_FIELD_MAP = {
    "CBT_ENABLED": "cbt_enabled",
    "ELECTION_ENABLED": "election_enabled",
    "OFFLINE_MODE_ENABLED": "offline_mode_enabled",
    "LOCKDOWN_ENABLED": "lockdown_enabled",
}


def get_runtime_feature_flags():
    flags = dict(settings.FEATURE_FLAGS)
    if "test" in sys.argv:
        return flags
    try:
        row = RuntimeFeatureFlags.get_solo()
    except (OperationalError, ProgrammingError):
        return flags
    for key, field_name in FLAG_FIELD_MAP.items():
        flags[key] = bool(getattr(row, field_name))
    return flags


def get_feature_flag(flag_name, default=False):
    return bool(get_runtime_feature_flags().get(flag_name, default))
