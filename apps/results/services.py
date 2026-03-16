from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from django.conf import settings
from django.core.exceptions import ValidationError

from apps.accounts.constants import ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.academics.models import GradeScale

CA_MAX = Decimal("10")
TOTAL_CA_MAX = Decimal("40")
OBJECTIVE_MAX = Decimal("40")
THEORY_MAX = Decimal("60")
TOTAL_EXAM_MAX = Decimal("100")
GRAND_TOTAL_MAX = Decimal("100")
ZERO = Decimal("0")


@dataclass
class GradeComputationResult:
    ca1: Decimal
    ca2: Decimal
    ca3: Decimal
    ca4: Decimal
    objective: Decimal
    theory: Decimal
    total_ca: Decimal
    total_exam: Decimal
    grand_total: Decimal
    grade: str
    violations: dict


def to_decimal(value):
    try:
        if value is None or value == "":
            return Decimal("0.00")
        return Decimal(str(value)).quantize(Decimal("0.01"))
    except (InvalidOperation, TypeError):
        raise ValidationError("Invalid numeric score value.")


def _has_elevated_override_role(actor):
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    role_codes = actor.get_all_role_codes()
    return bool(role_codes & {ROLE_DEAN, ROLE_VP, ROLE_PRINCIPAL, ROLE_IT_MANAGER})


def _collect_violations(*, ca1, ca2, ca3, ca4, objective, theory):
    violations = {}
    ca_scores = [ca1, ca2, ca3, ca4]
    for idx, value in enumerate(ca_scores, start=1):
        if value < ZERO:
            violations[f"ca{idx}"] = "CA score cannot be negative."
        if value > CA_MAX:
            violations[f"ca{idx}"] = "CA score cannot exceed 10."

    if objective < ZERO:
        violations["objective"] = "Objective score cannot be negative."
    if objective > OBJECTIVE_MAX:
        violations["objective"] = "Objective score cannot exceed 40."
    if theory < ZERO:
        violations["theory"] = "Theory score cannot be negative."
    if theory > THEORY_MAX:
        violations["theory"] = "Theory score cannot exceed 60."

    total_ca = ca1 + ca2 + ca3 + ca4
    total_exam = objective + theory
    grand_total = total_ca + total_exam

    if total_ca > TOTAL_CA_MAX:
        violations["total_ca"] = "Total CA cannot exceed 40."
    if total_exam > TOTAL_EXAM_MAX:
        violations["total_exam"] = "Total exam cannot exceed 100."
    if grand_total > GRAND_TOTAL_MAX:
        violations["grand_total"] = "Grand total cannot exceed 100."

    return violations, total_ca, total_exam, grand_total


def resolve_grade_for_total(total):
    bounded_total = min(max(total, ZERO), GRAND_TOTAL_MAX)
    scales = list(GradeScale.objects.filter(is_default=True).order_by("sort_order"))
    if not scales:
        GradeScale.ensure_default_scale()
        scales = list(GradeScale.objects.filter(is_default=True).order_by("sort_order"))
    for scale in scales:
        if Decimal(scale.min_score) <= bounded_total <= Decimal(scale.max_score):
            return scale.grade
    return ""


def compute_grade_payload(
    *,
    ca1,
    ca2,
    ca3,
    ca4,
    objective,
    theory,
    allow_override=False,
    override_reason="",
    actor=None,
    require_elevated_override=None,
):
    ca1_d = to_decimal(ca1)
    ca2_d = to_decimal(ca2)
    ca3_d = to_decimal(ca3)
    ca4_d = to_decimal(ca4)
    objective_d = to_decimal(objective)
    theory_d = to_decimal(theory)

    violations, total_ca, total_exam, grand_total = _collect_violations(
        ca1=ca1_d,
        ca2=ca2_d,
        ca3=ca3_d,
        ca4=ca4_d,
        objective=objective_d,
        theory=theory_d,
    )

    if violations:
        if not allow_override:
            raise ValidationError(violations)
        if not (override_reason or "").strip():
            raise ValidationError({"override_reason": "Override reason is required."})

        if require_elevated_override is None:
            require_elevated_override = settings.RESULTS_POLICY.get(
                "GRADE_OVERRIDE_REQUIRES_ELEVATED_APPROVAL",
                False,
            )
        if require_elevated_override and not _has_elevated_override_role(actor):
            raise ValidationError(
                {
                    "__all__": (
                        "Override requires Dean, VP, Principal, or IT Manager approval."
                    )
                }
            )

    grade = resolve_grade_for_total(grand_total)
    return GradeComputationResult(
        ca1=ca1_d,
        ca2=ca2_d,
        ca3=ca3_d,
        ca4=ca4_d,
        objective=objective_d,
        theory=theory_d,
        total_ca=total_ca.quantize(Decimal("0.01")),
        total_exam=total_exam.quantize(Decimal("0.01")),
        grand_total=grand_total.quantize(Decimal("0.01")),
        grade=grade,
        violations=violations,
    )
