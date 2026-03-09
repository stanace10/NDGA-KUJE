from __future__ import annotations


def _clean_list(values):
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _guidance_suffix(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return ""
    return f" Guidance: {text}"


def build_result_comment_bundle(
    *,
    student_name,
    average_score,
    attendance_percentage,
    fail_count,
    weak_subjects=None,
    predicted_score=None,
    risk_label=None,
    strongest_subjects=None,
    improvement_delta=None,
    teacher_guidance="",
    dean_guidance="",
    principal_guidance="",
):
    weak_subjects = _clean_list(weak_subjects)
    strongest_subjects = _clean_list(strongest_subjects)
    student_name = (student_name or "This student").strip()
    average_value = float(average_score or 0)
    attendance_value = float(attendance_percentage or 0)
    predicted_value = float(predicted_score or average_value)
    risk_text = (risk_label or "Low").strip()
    improvement_value = float(improvement_delta or 0)

    strengths = []
    cautions = []
    if average_value >= 75:
        strengths.append("shows strong analytical ability across subjects")
    elif average_value >= 60:
        strengths.append("is making steady academic progress")
    else:
        cautions.append("needs stronger academic support and follow-up")

    if strongest_subjects:
        strengths.append(f"is strongest in {', '.join(strongest_subjects[:2])}")

    if attendance_value >= 75:
        strengths.append("maintains dependable attendance")
    elif attendance_value < 60:
        cautions.append("must improve attendance urgently")
    else:
        cautions.append("should improve attendance consistency")

    if fail_count >= 3:
        cautions.append("recorded multiple subject failures this term")
    elif fail_count >= 1:
        cautions.append("has a few weak areas that need intervention")

    if weak_subjects:
        cautions.append(f"should prioritize {', '.join(weak_subjects[:2])}")

    if improvement_value > 0:
        strengths.append(f"improved by {improvement_value:.1f}% compared with the previous term")
    elif improvement_value < 0:
        cautions.append(f"dropped by {abs(improvement_value):.1f}% compared with the previous term")

    strengths_text = " and ".join(strengths) if strengths else "is still building stable performance"
    cautions_text = "; ".join(cautions) if cautions else "should maintain the current study discipline"

    watch_summary = ", ".join(weak_subjects[:3]) if weak_subjects else "No urgent watch subject flagged"
    strength_summary = ", ".join(strongest_subjects[:3]) if strongest_subjects else "No clear strength cluster yet"

    teacher_comment = (
        f"{student_name} {strengths_text}. "
        f"Next step: {cautions_text}. "
        f"Predicted next-term performance is around {predicted_value:.1f}%, so consistent classwork and CBT practice should remain the focus."
        f"{_guidance_suffix(teacher_guidance)}"
    )

    dean_comment = (
        f"Dean note for {student_name}: strengths currently show in {strength_summary}. "
        f"Priority intervention areas: {watch_summary}. "
        f"Department follow-up should target attendance, remediation, and submission discipline."
        f"{_guidance_suffix(dean_guidance)}"
    )

    principal_comment = (
        f"{student_name} completed the term with an average of {average_value:.1f}% and attendance of {attendance_value:.1f}%. "
        f"Risk level is {risk_text.lower()}. "
        f"Leadership recommendation: {cautions_text}."
        f"{_guidance_suffix(principal_guidance)}"
    )

    return {
        "teacher_comment": teacher_comment,
        "dean_comment": dean_comment,
        "principal_comment": principal_comment,
        "headline": f"Average {average_value:.1f}% | Attendance {attendance_value:.1f}% | Risk {risk_text}",
        "strength_summary": strength_summary,
        "watch_summary": watch_summary,
    }
