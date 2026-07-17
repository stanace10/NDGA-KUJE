from django.db.models import Q


EXTERNAL_EXAM_CLASS_PREFIXES = ("JS3", "JSS3", "SS3")


def is_third_term(term):
    return (getattr(term, "name", "") or "").strip().upper() == "THIRD"


def external_exam_class_q(field_name="academic_class"):
    class_q = Q()
    path_prefix = "" if field_name in {"", "self", None} else f"{field_name}__"
    for class_prefix in EXTERNAL_EXAM_CLASS_PREFIXES:
        class_q |= Q(**{f"{path_prefix}code__istartswith": class_prefix})
        class_q |= Q(**{f"{path_prefix}base_class__code__istartswith": class_prefix})
    return class_q


def exclude_external_exam_classes_for_term(queryset, term, *, field_name="academic_class"):
    if not is_third_term(term):
        return queryset
    return queryset.exclude(external_exam_class_q(field_name))


def class_is_external_exam_class_for_term(academic_class, term):
    if not is_third_term(term) or academic_class is None:
        return False
    base_class = getattr(academic_class, "base_class", None) or academic_class
    code = (getattr(base_class, "code", "") or getattr(academic_class, "code", "") or "").strip().upper()
    return code.startswith(EXTERNAL_EXAM_CLASS_PREFIXES)
