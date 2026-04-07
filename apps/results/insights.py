from __future__ import annotations


def _clean_list(values):
    return [str(value).strip() for value in (values or []) if str(value).strip()]


def _guidance_suffix(raw_text):
    text = (raw_text or "").strip()
    if not text:
        return ""
    return f" Guidance: {text}"


def _sentence(text):
    clean = (text or "").strip()
    if not clean:
        return ""
    return clean if clean.endswith((".", "!", "?")) else f"{clean}."


def _join_natural(items):
    rows = [str(item).strip() for item in (items or []) if str(item).strip()]
    if not rows:
        return ""
    if len(rows) == 1:
        return rows[0]
    if len(rows) == 2:
        return f"{rows[0]} and {rows[1]}"
    return f"{', '.join(rows[:-1])}, and {rows[-1]}"


def _short_support_focus(*, weak_subjects, fail_count, attendance_value):
    focus = []
    if weak_subjects:
        focus.append(f"closer support in {_join_natural(weak_subjects[:2])}")
    if fail_count >= 3:
        focus.append("structured remediation")
    elif fail_count >= 1:
        focus.append("follow-up on failed subjects")
    if attendance_value < 70:
        focus.append("better attendance")
    return _join_natural(focus) or "steady effort"


def _teacher_suggestions(*, student_name, average_value, attendance_value, strongest_subjects, weak_subjects, fail_count):
    strong_text = _join_natural(strongest_subjects[:2])
    support_focus = _short_support_focus(
        weak_subjects=weak_subjects,
        fail_count=fail_count,
        attendance_value=attendance_value,
    )
    suggestions = []
    if average_value >= 70:
        suggestions.append(
            f"{student_name} had a strong term. Please maintain this effort and keep building on {strong_text or 'the present strengths'}."
        )
    elif average_value >= 50:
        suggestions.append(
            f"{student_name} made fair progress this term. More consistency is needed, especially in { _join_natural(weak_subjects[:2]) or 'the weaker subjects' }."
        )
    else:
        suggestions.append(
            f"{student_name} needs closer academic support next term. Immediate attention should go to { _join_natural(weak_subjects[:2]) or 'the weakest subjects' }."
        )
    suggestions.append(
        f"Attendance was {attendance_value:.0f}%. Continued support at home and in school will help {student_name} stay more consistent."
    )
    suggestions.append(
        f"Next term focus should be on {support_focus}. With steady guidance, better results are achievable."
    )
    return suggestions[:3]


def _principal_suggestions(*, student_name, average_value, attendance_value, strongest_subjects, weak_subjects, risk_text):
    strength_text = strong_text = _join_natural(strongest_subjects[:2]) or "the present areas of strength"
    weak_text = _join_natural(weak_subjects[:2]) or "the weaker subjects"
    suggestions = [
        f"{student_name} completed the term with an average of {average_value:.1f}%. Commendable effort was shown in {strength_text}.",
        f"Attendance stood at {attendance_value:.1f}%. Continued discipline and closer attention to {weak_text} are advised.",
        f"Overall review level is {risk_text.lower()}. With focused support next term, {student_name} can make stronger progress.",
    ]
    return suggestions[:3]


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

    strength_summary = _join_natural(strongest_subjects[:3]) or "no single dominant strength cluster yet"
    watch_summary = _join_natural(weak_subjects[:3]) or "no urgent watch subject flagged"

    performance_line = ""
    if average_value >= 80:
        performance_line = f"{student_name} had an excellent term and worked with strong confidence across most subjects."
    elif average_value >= 70:
        performance_line = f"{student_name} had a very good term and maintained solid academic performance."
    elif average_value >= 60:
        performance_line = f"{student_name} made good progress this term and has a stable academic foundation."
    elif average_value >= 50:
        performance_line = f"{student_name} achieved a fair result this term but still needs closer support in weaker areas."
    else:
        performance_line = f"{student_name} needs serious academic support and closer monitoring next term."

    strengths_line = ""
    if strongest_subjects:
        strengths_line = f"Areas of strength were { _join_natural(strongest_subjects[:2]) }."

    attendance_line = ""
    if attendance_value >= 85:
        attendance_line = "Attendance was very good and supported steady classroom participation."
    elif attendance_value >= 70:
        attendance_line = "Attendance was fair, but it can still improve for stronger consistency."
    else:
        attendance_line = "Attendance was low and needs urgent improvement."

    improvement_line = ""
    if improvement_value > 0:
        improvement_line = f"There was an improvement of {improvement_value:.1f}% compared with the previous term."
    elif improvement_value < 0:
        improvement_line = f"There was a drop of {abs(improvement_value):.1f}% compared with the previous term."

    support_targets = []
    if weak_subjects:
        support_targets.append(f"extra attention should go to { _join_natural(weak_subjects[:2]) }")
    if fail_count >= 3:
        support_targets.append("structured remediation is strongly recommended")
    elif fail_count >= 1:
        support_targets.append("closer follow-up is needed in the failed subjects")
    if attendance_value < 70:
        support_targets.append("attendance must improve")

    if not support_targets:
        support_targets.append("the current effort should be maintained")

    next_step_line = f"Next step: { _join_natural(support_targets) }."
    prediction_line = (
        f"With sustained effort, the next-term outlook is around {predicted_value:.1f}%."
        if predicted_value
        else ""
    )

    teacher_comment = " ".join(
        part
        for part in [
            _sentence(performance_line),
            _sentence(strengths_line),
            _sentence(attendance_line),
            _sentence(improvement_line),
            _sentence(next_step_line),
            _sentence(prediction_line),
        ]
        if part
    ) + _guidance_suffix(teacher_guidance)

    dean_comment = " ".join(
        part
        for part in [
            _sentence(
                f"Department review for {student_name}: current strength profile is {strength_summary}"
            ),
            _sentence(
                f"Priority support areas are {watch_summary}"
            ),
            _sentence(
                f"Risk level for oversight is {risk_text.lower()}, and follow-up should focus on attendance, remediation, and consistency"
            ),
        ]
        if part
    ) + _guidance_suffix(dean_guidance)

    principal_comment = " ".join(
        part
        for part in [
            _sentence(
                f"{student_name} completed the term with an average of {average_value:.1f}% and attendance of {attendance_value:.1f}%"
            ),
            _sentence(strengths_line),
            _sentence(
                f"Leadership attention should focus on {watch_summary}" if weak_subjects else "Leadership attention should focus on maintaining the present progress"
            ),
            _sentence(
                f"Overall risk level is {risk_text.lower()}"
            ),
        ]
        if part
    ) + _guidance_suffix(principal_guidance)

    teacher_suggestions = [
        suggestion + (_guidance_suffix(teacher_guidance) if index == 0 and teacher_guidance else "")
        for index, suggestion in enumerate(
            _teacher_suggestions(
                student_name=student_name,
                average_value=average_value,
                attendance_value=attendance_value,
                strongest_subjects=strongest_subjects,
                weak_subjects=weak_subjects,
                fail_count=fail_count,
            )
        )
    ]
    principal_suggestions = [
        suggestion + (_guidance_suffix(principal_guidance) if index == 0 and principal_guidance else "")
        for index, suggestion in enumerate(
            _principal_suggestions(
                student_name=student_name,
                average_value=average_value,
                attendance_value=attendance_value,
                strongest_subjects=strongest_subjects,
                weak_subjects=weak_subjects,
                risk_text=risk_text,
            )
        )
    ]

    return {
        "teacher_comment": teacher_suggestions[0] if teacher_suggestions else teacher_comment,
        "teacher_suggestions": teacher_suggestions,
        "dean_comment": dean_comment,
        "principal_comment": principal_suggestions[0] if principal_suggestions else principal_comment,
        "principal_suggestions": principal_suggestions,
        "headline": f"Average {average_value:.1f}% | Attendance {attendance_value:.1f}% | Risk {risk_text}",
        "strength_summary": strength_summary,
        "watch_summary": watch_summary,
    }
