from decimal import Decimal, InvalidOperation, ROUND_FLOOR


NDGA_GRADE_SCALE = (
    {"grade": "A1", "min_score": 90, "max_score": 100, "sort_order": 1, "remark": "Star Distinction (A*)", "color": "Black", "css_class": "legend-black"},
    {"grade": "B2", "min_score": 80, "max_score": 89, "sort_order": 2, "remark": "Distinction (A)", "color": "Black", "css_class": "legend-black"},
    {"grade": "B3", "min_score": 75, "max_score": 79, "sort_order": 3, "remark": "High Merit (B)", "color": "Green", "css_class": "legend-green"},
    {"grade": "C4", "min_score": 70, "max_score": 74, "sort_order": 4, "remark": "Merit (C)", "color": "Green", "css_class": "legend-green"},
    {"grade": "C5", "min_score": 65, "max_score": 69, "sort_order": 5, "remark": "Standard Pass (D)", "color": "Blue", "css_class": "legend-blue"},
    {"grade": "C6", "min_score": 60, "max_score": 64, "sort_order": 6, "remark": "Pass (E)", "color": "Blue", "css_class": "legend-blue"},
    {"grade": "D7", "min_score": 55, "max_score": 59, "sort_order": 7, "remark": "Below Pass", "color": "Red", "css_class": "legend-red"},
    {"grade": "E8", "min_score": 50, "max_score": 54, "sort_order": 8, "remark": "Marginal Pass", "color": "Red", "css_class": "legend-red"},
    {"grade": "F9", "min_score": 0, "max_score": 49, "sort_order": 9, "remark": "Fail (Ungraded)", "color": "Red", "css_class": "legend-red"},
)


NDGA_GRADE_REMARKS = {row["grade"]: row["remark"] for row in NDGA_GRADE_SCALE}
NDGA_GRADE_COLORS = {row["grade"]: row["color"] for row in NDGA_GRADE_SCALE}
NDGA_GRADE_CSS_CLASSES = {row["grade"]: row["css_class"] for row in NDGA_GRADE_SCALE}


def grade_metadata_for_grade(grade):
    label = str(grade or "").strip().upper()
    for row in NDGA_GRADE_SCALE:
        if row["grade"] == label:
            return row.copy()
    return NDGA_GRADE_SCALE[-1].copy()


def grade_metadata_for_score(score):
    try:
        value = Decimal(str(score or 0))
    except (InvalidOperation, TypeError, ValueError):
        value = Decimal("0")
    bounded = min(max(value, Decimal("0")), Decimal("100"))
    band_score = bounded.to_integral_value(rounding=ROUND_FLOOR)
    for row in NDGA_GRADE_SCALE:
        if Decimal(row["min_score"]) <= band_score <= Decimal(row["max_score"]):
            return row.copy()
    return NDGA_GRADE_SCALE[-1].copy()


def remark_for_score(score, grade=None):
    if grade:
        return grade_metadata_for_grade(grade)["remark"]
    return grade_metadata_for_score(score)["remark"]


def is_failing_grade(grade):
    return str(grade or "").strip().upper() == "F9"
