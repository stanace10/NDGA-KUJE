"""Shared rules for assessed subjects excluded from official results."""

from __future__ import annotations

from django.db.models import Q


NON_RESULT_SUBJECT_CODES = frozenset({"CHN", "SGL", "GER"})
NON_RESULT_SUBJECT_NAMES = frozenset({"CHINESE", "SIGN LANGUAGE", "GERMAN LANGUAGE"})


def subject_is_excluded_from_results(subject) -> bool:
    if subject is None:
        return False
    code = str(getattr(subject, "code", "") or "").strip().upper()
    name = str(getattr(subject, "name", "") or "").strip().upper()
    return code in NON_RESULT_SUBJECT_CODES or name in NON_RESULT_SUBJECT_NAMES


def result_subject_q(*, field_name="subject"):
    return ~(
        Q(**{f"{field_name}__code__in": tuple(NON_RESULT_SUBJECT_CODES)})
        | Q(**{f"{field_name}__name__in": tuple(NON_RESULT_SUBJECT_NAMES)})
    )


def exclude_non_result_subjects(queryset, *, field_name="subject"):
    return queryset.filter(result_subject_q(field_name=field_name))
