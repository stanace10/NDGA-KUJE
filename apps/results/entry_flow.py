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


def _component_has_cbt_score(score, breakdown_key, field_name):
    if score is None:
        return False
    return score.breakdown_value(breakdown_key) > ZERO or score.is_component_locked(field_name)


def _validate_manual_total(*, policy_key, total_score, policies):
    total_limit = (
        decimal_value(policies[policy_key]["objective_max"])
        + decimal_value(policies[policy_key]["theory_max"])
    ).quantize(DECIMAL_2)
    label = POLICY_LABELS[policy_key]
    if total_score < ZERO or total_score > total_limit:
        raise ValidationError(
            {policy_key: f"{label} score must be between 0 and {total_limit}."}
        )


def row_component_state(score, policies):
    ca1_objective = _existing_locked_or_value(score, "ca1_objective", "ca1")
    ca1_theory = _existing_split_theory(score, "ca1")
    ca4_objective = _existing_locked_or_value(score, "ca4_objective", "ca4")
    ca4_theory = _existing_split_theory(score, "ca4")
    ca2_objective = _existing_locked_or_value(score, "ca2_objective", "ca2")
    objective_auto = _existing_locked_or_value(score, "objective_auto", "objective")
    exam_theory = decimal_value(score.theory if score else ZERO)
    ca1_objective_locked = _component_has_cbt_score(score, "ca1_objective", "ca1")
    ca23_objective_locked = _component_has_cbt_score(score, "ca2_objective", "ca2")
    ca23_locked = ca23_objective_locked or bool(
        score and score.is_component_locked("ca3")
    )
    ca4_objective_locked = _component_has_cbt_score(score, "ca4_objective", "ca4")
    exam_objective_locked = _component_has_cbt_score(score, "objective_auto", "objective")
    return {
        "ca1": {
            "enabled": bool(policies["ca1"]["enabled"]),
            "objective": decimal_text(ca1_objective),
            "theory": decimal_text(ca1_theory),
            "total": decimal_text(score.ca1 if score else ZERO),
            "objective_max": policies["ca1"]["objective_max"],
            "theory_max": policies["ca1"]["theory_max"],
            "locked": ca1_objective_locked,
            "objective_locked": ca1_objective_locked,
        },
        "ca23": {
            "enabled": bool(policies["ca23"]["enabled"]),
            "objective": decimal_text(ca2_objective),
            "theory": decimal_text(score.ca3 if score else ZERO),
            "objective_max": policies["ca23"]["objective_max"],
            "theory_max": policies["ca23"]["theory_max"],
            "locked": ca23_locked,
            "objective_locked": ca23_objective_locked,
        },
        "ca4": {
            "enabled": bool(policies["ca4"]["enabled"]),
            "objective": decimal_text(ca4_objective),
            "theory": decimal_text(ca4_theory),
            "total": decimal_text(score.ca4 if score else ZERO),
            "objective_max": policies["ca4"]["objective_max"],
            "theory_max": policies["ca4"]["theory_max"],
            "locked": ca4_objective_locked,
            "objective_locked": ca4_objective_locked,
        },
        "exam": {
            "enabled": bool(policies["exam"]["enabled"]),
            "objective": decimal_text(objective_auto),
            "theory": decimal_text(exam_theory),
            "objective_max": policies["exam"]["objective_max"],
            "theory_max": policies["exam"]["theory_max"],
            "locked": exam_objective_locked,
            "objective_locked": exam_objective_locked,
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


def _policy_limit_for_sheet(policy_key, sheet):
    if policy_key == "exam":
        class_code = (
            getattr(getattr(sheet, "academic_class", None), "code", "") or ""
        ).strip().upper()
        if class_code.startswith("SS3"):
            return Decimal("100.00")
    return POLICY_LIMITS[policy_key]


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
        limit = _policy_limit_for_sheet(key, sheet)
        if (objective_max + theory_max) > limit:
            objective_max = decimal_value(policies[key]["objective_max"])
            theory_max = decimal_value(policies[key]["theory_max"])
            warnings.append(f"{label} split must stay within {limit} marks.")
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
    total_limit = (objective_max + theory_max).quantize(DECIMAL_2)
    label = POLICY_LABELS[policy_key]
    errors = {}
    if objective_score < ZERO or objective_score > objective_max:
        errors[policy_key] = f"{label} objective score must be between 0 and {objective_max}."
    if theory_score < ZERO or theory_score > theory_max:
        errors[f"{policy_key}_theory"] = f"{label} theory score must be between 0 and {theory_max}."
    if (objective_score + theory_score) > total_limit:
        errors[f"{policy_key}_total"] = f"{label} total must not exceed {total_limit}."
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
        if _component_has_cbt_score(current_score, "ca1_objective", "ca1"):
            objective_score = _existing_locked_or_value(current_score, "ca1_objective", "ca1")
            theory_score = decimal_value(
                post.get(f"ca1_theory_{student_id}"),
                _existing_split_theory(current_score, "ca1"),
            )
            _validate_split_scores(policy_key="ca1", objective_score=objective_score, theory_score=theory_score, policies=policies)
            posted_scores["ca1"] = (objective_score + theory_score).quantize(DECIMAL_2)
            breakdown_updates["ca1_objective"] = objective_score
            breakdown_updates["ca1_theory"] = theory_score
        else:
            manual_total = decimal_value(
                post.get(f"ca1_{student_id}"),
                getattr(current_score, "ca1", ZERO) if current_score else ZERO,
            )
            _validate_manual_total(policy_key="ca1", total_score=manual_total, policies=policies)
            posted_scores["ca1"] = manual_total
            breakdown_updates["ca1_objective"] = ZERO
            breakdown_updates["ca1_theory"] = ZERO
    elif "ca1" in locked_fields and current_score is not None:
        posted_scores["ca1"] = decimal_value(current_score.ca1)

    if policies["ca23"]["enabled"]:
        if _component_has_cbt_score(current_score, "ca2_objective", "ca2"):
            objective_score = _existing_locked_or_value(current_score, "ca2_objective", "ca2")
        else:
            objective_score = decimal_value(
                post.get(f"ca2_{student_id}"),
                getattr(current_score, "ca2", ZERO) if current_score else ZERO,
            )
        theory_score = decimal_value(
            post.get(f"ca3_{student_id}"),
            current_score.ca3 if current_score else ZERO,
        )
        _validate_split_scores(policy_key="ca23", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["ca2"] = objective_score
        posted_scores["ca3"] = theory_score
        breakdown_updates["ca2_objective"] = (
            objective_score if _component_has_cbt_score(current_score, "ca2_objective", "ca2") else ZERO
        )
        breakdown_updates["ca3_theory"] = theory_score
    else:
        if "ca2" in locked_fields and current_score is not None:
            posted_scores["ca2"] = decimal_value(current_score.ca2)

    if policies["ca4"]["enabled"]:
        if _component_has_cbt_score(current_score, "ca4_objective", "ca4"):
            objective_score = _existing_locked_or_value(current_score, "ca4_objective", "ca4")
            theory_score = decimal_value(
                post.get(f"ca4_theory_{student_id}"),
                _existing_split_theory(current_score, "ca4"),
            )
            _validate_split_scores(policy_key="ca4", objective_score=objective_score, theory_score=theory_score, policies=policies)
            posted_scores["ca4"] = (objective_score + theory_score).quantize(DECIMAL_2)
            breakdown_updates["ca4_objective"] = objective_score
            breakdown_updates["ca4_theory"] = theory_score
        else:
            manual_total = decimal_value(
                post.get(f"ca4_{student_id}"),
                getattr(current_score, "ca4", ZERO) if current_score else ZERO,
            )
            _validate_manual_total(policy_key="ca4", total_score=manual_total, policies=policies)
            posted_scores["ca4"] = manual_total
            breakdown_updates["ca4_objective"] = ZERO
            breakdown_updates["ca4_theory"] = ZERO
    elif "ca4" in locked_fields and current_score is not None:
        posted_scores["ca4"] = decimal_value(current_score.ca4)

    if policies["exam"]["enabled"]:
        if _component_has_cbt_score(current_score, "objective_auto", "objective"):
            objective_score = _existing_locked_or_value(current_score, "objective_auto", "objective")
        else:
            objective_score = decimal_value(
                post.get(f"objective_{student_id}"),
                getattr(current_score, "objective", ZERO) if current_score else ZERO,
            )
        theory_score = decimal_value(
            post.get(f"theory_{student_id}"),
            current_score.theory if current_score else ZERO,
        )
        _validate_split_scores(policy_key="exam", objective_score=objective_score, theory_score=theory_score, policies=policies)
        posted_scores["objective"] = objective_score
        posted_scores["theory"] = theory_score
        breakdown_updates["objective_auto"] = (
            objective_score if _component_has_cbt_score(current_score, "objective_auto", "objective") else ZERO
        )
    else:
        if "objective" in locked_fields and current_score is not None:
            posted_scores["objective"] = decimal_value(current_score.objective)

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
