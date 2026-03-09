from __future__ import annotations


def build_result_comment_bundle(*, student_name, average_score, attendance_percentage, fail_count, weak_subjects=None, predicted_score=None, risk_label=None):
    weak_subjects = [subject for subject in (weak_subjects or []) if subject]
    student_name = (student_name or "This student").strip()
    average_value = float(average_score or 0)
    attendance_value = float(attendance_percentage or 0)
    predicted_value = float(predicted_score or average_value)
    risk_text = (risk_label or "Low").strip()

    strengths = []
    cautions = []
    if average_value >= 75:
        strengths.append("shows strong analytical ability across subjects")
    elif average_value >= 60:
        strengths.append("is making steady academic progress")
    else:
        cautions.append("needs stronger academic support and follow-up")

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

    strengths_text = " and ".join(strengths) if strengths else "is still building stable performance"
    cautions_text = "; ".join(cautions) if cautions else "should maintain the current study discipline"

    teacher_comment = (
        f"{student_name} {strengths_text}. "
        f"Next step: {cautions_text}. "
        f"Predicted next-term performance is around {predicted_value:.1f}%, so consistent classwork and CBT practice should remain the focus."
    )

    principal_comment = (
        f"{student_name} completed the term with an average of {average_value:.1f}% and attendance of {attendance_value:.1f}%. "
        f"Risk level is {risk_text.lower()}. "
        f"Leadership recommendation: {cautions_text}."
    )

    return {
        "teacher_comment": teacher_comment,
        "principal_comment": principal_comment,
        "headline": f"Average {average_value:.1f}% | Attendance {attendance_value:.1f}% | Risk {risk_text}",
    }
