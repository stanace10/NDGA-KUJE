"""Annual cumulative subject-slot normalization.

Term reports keep the exact subject a student offered in that term.

Annual/cumulative reports must also keep dropped/swapped subjects visible as
their own rows.  Each annual subject row is averaged only across terms where
that subject slot actually has scores.  The narrow exception is curriculum
renaming/merging, such as JS1 Basic Science + Basic Technology becoming a
single Intermediate Science annual slot.
"""

from __future__ import annotations

from decimal import Decimal, InvalidOperation


def normalize_subject_name(value: str | None) -> str:
    return " ".join(str(value or "").lower().replace("&", " and ").split())


def normalize_admission(value: str | None) -> str:
    return str(value or "").strip().lower().replace("\\", "/")


GENERIC_ANNUAL_SUBJECT_ALIASES = {
    "basic science": "Intermediate Science",
    "basic technology": "Intermediate Science",
    "intermediate science": "Intermediate Science",
    "computer studies": "Digital Technology",
    "computer science": "Digital Technology",
    "digital technology": "Digital Technology",
    "english literature": "Literature",
    "literature": "Literature",
    "fashion": "Garment Making Theory",
    "fashion design": "Garment Making Theory",
    "fashion and garment making": "Garment Making Theory",
    "fashion design and garment making": "Garment Making Theory",
    "garment making": "Garment Making Theory",
    "garment making theory": "Garment Making Theory",
}

BEST_OF_DUPLICATE_ANNUAL_SLOTS = {
    # Historical imports can contain an old CBT theory-only row and a full
    # legacy report-card row for the same Garment subject. For annual reports,
    # the full-score row must win; averaging the two would unfairly reduce the
    # child. Other merged subjects such as Basic Science + Basic Technology are
    # intentionally averaged, so this rule is narrowly scoped.
    "Garment Making Theory",
}


_DATA_PROCESSING_TO_LIVESTOCK = {
    "ndgak/22/253",
    "ndgak/25/412",
    "ndgak/23/283",
    "ndgak/22/225",
    "ndgak/22/228",
    "ndgak/22/250",
    "ndgak/22/243",
    "ndgak/25/413",
    "ndgak/22/252",
    "ndgak/22/247",
    "ndgak/24/339",
    "ndgak/25/410",
    "ndgak/22/219",
    "ndgak/22/249",
    "ndgak/25/407",
    "ndgak/22/242",
}

_FRENCH_TO_LIVESTOCK = {
    "ndgak/22/230",
    "ndgak/22/218",
    "ndgak/22/221",
    "ndgak/24/334",
    "ndgak/23/280",
    "ndgak/23/282",
    "ndgak/25/409",
}

_FISHERY_TO_LIVESTOCK = {
    "ndgak/25/411",
    "ndgak/25/408",
    "ndgak/25/415",
}

_AGRIC_TO_LIVESTOCK = {
    "ndgak/25/406",
}

_VISUAL_ART_TO_LIVESTOCK = {
    "ndgak/25/405",
}


def _student_admission_key(student) -> str:
    profile = getattr(student, "student_profile", None)
    return normalize_admission(
        getattr(profile, "student_number", None)
        or getattr(student, "username", None)
    )


def _student_specific_switches(student) -> dict[str, str]:
    # Final school policy: unrelated subject changes must remain separate on
    # the annual subject table.  Examples include Geography/Biology,
    # Visual Art/French, Data Processing/Livestock, Fishery/Livestock, and
    # Igbo/Hausa.  The overall cumulative average already uses exact term
    # averages, so these switches do not need to be merged to protect the
    # student.  Keep this hook returning an empty mapping to avoid resurrecting
    # old admission-specific merge rules.
    return {}


def annual_subject_label(subject_name, *, student=None) -> str:
    raw = str(subject_name or "").strip()
    normalized = normalize_subject_name(raw)
    if student is not None:
        switched = _student_specific_switches(student).get(normalized)
        if switched:
            return switched
    return GENERIC_ANNUAL_SUBJECT_ALIASES.get(normalized, raw)


def _row_class_code(row) -> str:
    result_sheet = None
    if isinstance(row, dict):
        result_sheet = row.get("result_sheet")
    else:
        result_sheet = getattr(row, "result_sheet", None)
    academic_class = getattr(result_sheet, "academic_class", None)
    instructional = getattr(academic_class, "instructional_class", academic_class)
    return str(getattr(instructional, "code", "") or getattr(academic_class, "code", "") or "").upper()


def generic_annual_subject_label(subject_name, *, row=None) -> str:
    raw = str(subject_name or "").strip()
    if _row_class_code(row) == "JS2" and normalize_subject_name(raw) in {
        "basic science",
        "basic technology",
        "intermediate science",
    }:
        # JS2 kept Basic Science and Basic Technology as separate subjects for
        # this imported session. The Basic->Intermediate merge applies to JS1,
        # not to JS2.
        return raw
    return GENERIC_ANNUAL_SUBJECT_ALIASES.get(normalize_subject_name(raw), raw)


def _row_total(row) -> Decimal:
    if isinstance(row, dict):
        value = row.get("total") or row.get("grand_total") or row.get("score") or 0
    else:
        value = getattr(row, "grand_total", None)
        if value in (None, ""):
            value = getattr(row, "total", None)
    try:
        return Decimal(str(value or 0))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _append_slot_row(slots, *, label: str, term_key: str, row, reason: str, diagnostics: list[dict]):
    term_rows = slots.setdefault(label, {}).setdefault(term_key, [])
    if label in BEST_OF_DUPLICATE_ANNUAL_SLOTS and term_rows:
        incoming_total = _row_total(row)
        existing_best = max((_row_total(existing) for existing in term_rows), default=Decimal("0.00"))
        if incoming_total > existing_best:
            diagnostics.append(
                {
                    "term": term_key,
                    "subject": label,
                    "reason": "duplicate_slot_replaced_with_higher_total",
                    "old_total": str(existing_best),
                    "new_total": str(incoming_total),
                }
            )
            slots[label][term_key] = [row]
        else:
            diagnostics.append(
                {
                    "term": term_key,
                    "subject": label,
                    "reason": "duplicate_slot_lower_total_ignored",
                    "old_total": str(existing_best),
                    "new_total": str(incoming_total),
                }
            )
        return
    term_rows.append(row)
    if reason != "direct":
        diagnostics.append({"term": term_key, "subject": label, "reason": reason, "total": str(_row_total(row))})


def _choose_dynamic_target(*, source_subject: str, source_label: str, missing_labels: list[str]) -> str | None:
    # Dynamic retargeting is intentionally disabled.  Annual subject rows must
    # show the exact subject that carried the score in that term, except for
    # explicit curriculum aliases handled by generic_annual_subject_label().
    return None


def build_annual_subject_slots(term_subject_rows: dict[str, list[tuple[str, object]]], *, student=None):
    """Build annual subject slots for one student.

    The cumulative report is not allowed to punish a child with zero for a
    subject that was not offered in a term, and it must not hide old subjects
    that the child genuinely wrote.  Therefore:

    - every real term score is kept in an annual subject slot;
    - each slot divides only by the number of terms with scores;
    - known curriculum aliases/merges are grouped by
      :func:`generic_annual_subject_label` (for example JS1 Basic Science and
      Basic Technology become one Intermediate Science slot);
    - student-specific course switches are not folded into the new subject.
      Dropped and picked-up subjects remain visible as separate annual rows.
    """

    diagnostics: list[dict] = []
    slots: dict[str, dict[str, list[object]]] = {}

    for term_key in ("FIRST", "SECOND", "THIRD"):
        for subject, row in term_subject_rows.get(term_key, []):
            label = generic_annual_subject_label(subject, row=row)
            if not label:
                continue
            _append_slot_row(
                slots,
                label=label,
                term_key=term_key,
                row=row,
                reason="direct",
                diagnostics=diagnostics,
            )

    return slots, diagnostics
