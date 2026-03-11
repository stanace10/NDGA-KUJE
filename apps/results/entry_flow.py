from __future__ import annotations

from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError

from apps.results.cbt_policy import normalize_result_cbt_policies, policy_fields, policy_lock_keys
from apps.results.services import compute_grade_payload

DECIMAL_2 = Decimal("0.01")
ZERO = Decimal("0.00")
POLICY_LIMITS = {
    "ca1": Decimal("10.00"),
    "ca23": Decimal("20.00"),
    "ca4": Decimal("10.00"),
    "exam": Decimal("60.00"),
}
POLICY_LABELS = {
    "ca1": "CA1",
    "ca23": "CA2 / CA3 Joint",
    "ca4": "CA4",
    "exam": "Exam",
}


def decimal_value(value, fallback=ZERO):
    try:
        if value in (None, ""):
            return Decimal(str(fallback)).quantize(DECIMAL_2)
        return Decimal(str(value)).quantize(DECIMAL_2)
    except (InvalidOperation, TypeError, ValueError):
        return Decimal(str(fallback)).quantize(DECIMAL_2)


def decimal_text(value):
    return str(decimal_value(value))


def sheet_policy_state(sheet):
    return normalize_result_cbt_policies(getattr(sheet, "cbt_component_policies", {}))


def _existing_split_theory(score, field_name):
    if score is None:
        return ZERO
    stored = score.breakdown_value(f"{field_name}_theory")
    if stored > ZERO:
        return stored
    objective = score.breakdown_value(f"{field_name}_objective")
    total = decimal_value(getattr(score, field_name, ZERO))
    if objective > ZERO and total >= objective:
        return (total - objective).quantize(DECIMAL_2)
    return ZERO


def _existing_locked_or_value(score, breakdown_key, field_name):
    if score is None:
        return ZERO
    breakdown = score.breakdown_value(breakdown_key)
    if breakdown > ZERO:
        return breakdown
    return decimal_value(getattr(score, field_name, ZERO))


def row_component_state(score, policies):
    ca1_objective = _existing_locked_or_value(score, "ca1_objective", "ca1")
    ca4_objective = _existing_locked_or_value(score, "ca4_objective", "ca4")
    ca2_objective = _existing_locked_or_value(score, "ca2_objective", "ca2")
    objective_auto = _existing_locked_or_value(score, "objective_auto", "objective")
    return {
        "ca1": {
            "enabled": bool(policies["ca1"]["enabled"]),
            "objective": decimal_text(ca1_objective),
            "theory": decimal_text(_existing_split_theory(score, "ca1")),
            "total": decimal_text(score.ca1 if score else ZERO),
            "objective_max": policies["ca1"]["objective_max"],
            "theory_max": policies["ca1"]["theory_max"],
            "locked": ca1_objective > ZERO or bool(score and score.is_component_locked("ca1")),
        },
        "ca23": {
            "enabled": bool(policies["ca23"]["enabled"]),
            "objective": decimal_text(ca2_objective),
            "theory": decimal_text(score.ca3 if score else ZERO),
            "objective_max": policies["ca23"]["objective_max"],
            "theory_max": policies["ca23"]["theory_max"],
            "locked": (ca2_objective > ZERO) or bool(score and score.is_component_locked("ca2")),
        },
        "ca4": {
            "enabled": bool(policies["ca4"]["enabled"]),
            "objective": decimal_text(ca4_objective),
            "theory": decimal_text(_existing_split_theory(score, "ca4")),
            "total": decimal_text(score.ca4 if score else ZERO),
            "objective_max": policies["ca4"]["objective_max"],
            "theory_max": policies["ca4"]["theory_max"],
            "locked": ca4_objective > ZERO or bool(score and score.is_component_locked("ca4")),
        },
        "exam": {
            "enabled": bool(policies["exam"]["enabled"]),
            "objective": decimal_text(objective_auto),
            "theory": decimal_text(score.theory if score else ZERO),
            "objective_max": policies["exam"]["objective_max"],
            "theory_max": policies["exam"]["theory_max"],
            "locked": (objective_auto > ZERO) or bool(score and score.is_component_locked("objective")),
        },
    }


def policy_locked_for_scores(policy_key, scores):
    keys = policy_lock_keys(policy_key)
    for score in scores:
        for key in keys:
            if score.breakdown_value(key) > ZERO:
                return True
        if policy_key == "ca1" and score.is_component_locked("ca1"):
            return True
        if policy_key == "ca23" and score.is_component_locked("ca2"):
            return True
        if policy_key == "ca4" and score.is_component_locked("ca4"):
            return True
        if policy_key == "exam" and score.is_component_locked("objective"):
            return True
    return False


def read_sheet_policies_from_post(sheet, post, existing_scores):
    policies = sheet_policy_state(sheet)
    warnings = []
    changed = False
    for key, label in policy_fields():
        requested = bool(post.get(f"policy_{key}_enabled"))
        locked = policy_locked_for_scores(key, existing_scores)
        objective_max = decimal_value(post.get(f"policy_{key}_objective_max"), policies[key]["objective_max"])
        theory_max = decimal_value(post.get(f"policy_{key}_theory_max"), policies[key]["theory_max"])
        if objective_max <= ZERO:
            objective_max = decimal_value(policies[key]["objective_max"])
        if theory_max < ZERO:
            theory_max = decimal_value(policies[key]["theory_max"])
        if locked and not requested:
            requested = True
            warnings.append(f"{label} CBT cannot be turned off after scores have been written.")
        if (objective_max + theory_max) > POLICY_LIMITS[key]:
            objective_max = decimal_value(policies[key]["objective_max"])
            theory_max = decimal_value(policies[key]["theory_max"])
            warnings.append(f"{label} split must stay within {POLICY_LIMITS[key]} marks.")
        new_section = {
            "enabled": bool(requested),
            "objective_max": decimal_text(objective_max),
            "theory_max": decimal_text(theory_max),
        }
        if policies.get(key) != new_section:
            changed = True
            policies[key] = new_section
    return policies, warnings, changed


def _validate_split_scores(*, policy_key, objective_score, theory_score, policies):
    objective_max = decimal_value(policies[policy_key]["objective_max"])
    theory_max = decimal_value(policies[policy_key]["theory_max"])
    label = POLICY_LABELS[policy_key]
    errors = {}
    if objective_score < ZERO or objective_score > objective_max:
        errors[policy_key] = f"{label} objective score must be between 0 and {objective_max}."
    if theory_score < ZERO or theory_score > theory_max:
        errors[f"{policy_key}_theory"] = f"{label} theory score must be between 0 and {theory_max}."
    if (objective_score + theory_score) > POLICY_LIMITS[policy_key]:
        errors[f"{policy_key}_total"] = f"{label} total must not exceed {POLICY_LIMITS[policy_key]}."
    if errors:
        raise ValidationError(errors)


def build_posted_score_bundle(*, current_score, post, student_id, policies, actor):
    locked_fields = set(current_score.normalized_locked_fields() if current_score else [])
    posted_scores = {
        "ca1": decimal_value(post.get(f"ca1_{student_id}"), getattr(current_score, "ca1", ZERO) if current_score else ZERO),
        "ca2": decimal_value(post.get(f"ca2_{student_id}"), getattr(current_score, "ca2", ZERO) if current_score else ZERO),
        "ca3": decimal_value(post.get(f"ca3_{student_id}"), getattr(current_score, "ca3", ZERO) if current_score else ZERO),
        "ca4": decimal_value(post.get(f"ca4_{student_id}"), getattr(current_score, "ca4", ZERO) if current_score else ZERO),
        "objective": decimal_value(post.get(f"objective_{student_id}"), getattr(current_score, "objective", ZERO) if current_score else ZERO),
        "theory": decimal_value(post.get(f"theory_{student_id}"), getattr(current_score, "theory", ZERO) if current_score else ZERO),
    }
    breakdown_updates = {}

    if policies["ca1"]["enabled"]:
        objective_score = _existing_locked_or_value(current_score, "ca1_objective", "ca1")
        theory_score = decimal_value(post.get(f"ca1_theory_{student_id}"), _existing_split_theory(current_score, "ca1"))
        _validate_split_scores(policy_key="ca1", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["ca1"] = (objective_score + theory_score).quantize(DECIMAL_2)
        breakdown_updates["ca1_objective"] = objective_score
        breakdown_updates["ca1_theory"] = theory_score
    elif "ca1" in locked_fields and current_score is not None:
        posted_scores["ca1"] = decimal_value(current_score.ca1)

    if policies["ca23"]["enabled"]:
        objective_score = _existing_locked_or_value(current_score, "ca2_objective", "ca2")
        theory_score = decimal_value(post.get(f"ca3_{student_id}"), current_score.ca3 if current_score else ZERO)
        _validate_split_scores(policy_key="ca23", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["ca2"] = objective_score
        posted_scores["ca3"] = theory_score
        breakdown_updates["ca2_objective"] = objective_score
        breakdown_updates["ca3_theory"] = theory_score
    else:
        if "ca2" in locked_fields and current_score is not None:
            posted_scores["ca2"] = decimal_value(current_score.ca2)
        if "ca3" in locked_fields and current_score is not None:
            posted_scores["ca3"] = decimal_value(current_score.ca3)

    if policies["ca4"]["enabled"]:
        objective_score = _existing_locked_or_value(current_score, "ca4_objective", "ca4")
        theory_score = decimal_value(post.get(f"ca4_theory_{student_id}"), _existing_split_theory(current_score, "ca4"))
        _validate_split_scores(policy_key="ca4", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["ca4"] = (objective_score + theory_score).quantize(DECIMAL_2)
        breakdown_updates["ca4_objective"] = objective_score
        breakdown_updates["ca4_theory"] = theory_score
    elif "ca4" in locked_fields and current_score is not None:
        posted_scores["ca4"] = decimal_value(current_score.ca4)

    if policies["exam"]["enabled"]:
        objective_score = _existing_locked_or_value(current_score, "objective_auto", "objective")
        theory_score = decimal_value(post.get(f"theory_{student_id}"), current_score.theory if current_score else ZERO)
        _validate_split_scores(policy_key="exam", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["objective"] = objective_score
        posted_scores["theory"] = theory_score
        breakdown_updates["objective_auto"] = objective_score
        breakdown_updates["theory_manual"] = theory_score
    else:
        if "objective" in locked_fields and current_score is not None:
            posted_scores["objective"] = decimal_value(current_score.objective)
        if "theory" in locked_fields and current_score is not None:
            posted_scores["theory"] = decimal_value(current_score.theory)

    payload = compute_grade_payload(
        ca1=posted_scores["ca1"],
        ca2=posted_scores["ca2"],
        ca3=posted_scores["ca3"],
        ca4=posted_scores["ca4"],
        objective=posted_scores["objective"],
        theory=posted_scores["theory"],
        allow_override=False,
        override_reason="",
        actor=actor,
    )
    return {
        "payload": payload,
        "locked_fields": sorted(locked_fields),
        "breakdown_updates": breakdown_updates,
    }
