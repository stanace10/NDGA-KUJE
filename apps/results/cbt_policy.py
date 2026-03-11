from __future__ import annotations

from copy import deepcopy
from decimal import Decimal, InvalidOperation

DEFAULT_RESULT_CBT_POLICIES = {
    "ca1": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
    "ca23": {"enabled": False, "objective_max": "10.00", "theory_max": "10.00"},
    "ca4": {"enabled": False, "objective_max": "5.00", "theory_max": "5.00"},
    "exam": {"enabled": False, "objective_max": "40.00", "theory_max": "20.00"},
}


def _decimal_string(value, fallback):
    try:
        return str(Decimal(str(value)).quantize(Decimal("0.01")))
    except (InvalidOperation, TypeError, ValueError):
        return str(Decimal(str(fallback)).quantize(Decimal("0.01")))


def normalize_result_cbt_policies(raw):
    policies = deepcopy(DEFAULT_RESULT_CBT_POLICIES)
    if not isinstance(raw, dict):
        return policies
    for key, defaults in DEFAULT_RESULT_CBT_POLICIES.items():
        section = raw.get(key)
        if not isinstance(section, dict):
            continue
        policies[key]["enabled"] = bool(section.get("enabled"))
        policies[key]["objective_max"] = _decimal_string(section.get("objective_max"), defaults["objective_max"])
        policies[key]["theory_max"] = _decimal_string(section.get("theory_max"), defaults["theory_max"])
    return policies


def policy_fields():
    return (
        ("ca1", "CA1"),
        ("ca23", "CA2 / CA3 Joint"),
        ("ca4", "CA4"),
        ("exam", "Exam"),
    )


def policy_lock_keys(policy_key):
    mapping = {
        "ca1": ("ca1_objective",),
        "ca23": ("ca2_objective",),
        "ca4": ("ca4_objective",),
        "exam": ("objective_auto",),
    }
    return mapping.get(policy_key, ())


def merge_policy_from_blueprint(policies, blueprint):
    merged = normalize_result_cbt_policies(policies)
    if blueprint is None:
        return merged
    section_config = getattr(blueprint, "section_config", {}) or {}
    if not bool(section_config.get("manual_score_split")):
        return merged
    flow_type = (section_config.get("flow_type") or "").strip()
    if flow_type == "SIMULATION":
        return merged
    ca_target = (section_config.get("ca_target") or "").strip()
    if ca_target == "CA1":
        key = "ca1"
    elif ca_target == "CA2":
        key = "ca23"
    elif ca_target == "CA4":
        key = "ca4"
    elif getattr(blueprint.exam, "exam_type", "") == "EXAM":
        key = "exam"
    else:
        key = ""
    if not key:
        return merged
    merged[key]["enabled"] = True
    merged[key]["objective_max"] = _decimal_string(section_config.get("objective_target_max"), merged[key]["objective_max"])
    merged[key]["theory_max"] = _decimal_string(section_config.get("theory_target_max"), merged[key]["theory_max"])
    return merged
