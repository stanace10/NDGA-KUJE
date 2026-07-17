from __future__ import annotations

from collections import defaultdict

DAY_LABELS = {
    "MONDAY": "Monday",
    "TUESDAY": "Tuesday",
    "WEDNESDAY": "Wednesday",
    "THURSDAY": "Thursday",
    "FRIDAY": "Friday",
}


def generate_timetable_preview(*, assignments, days, periods_per_day, periods_per_assignment=2, room_prefix="Room"):
    days = [day for day in days if day in DAY_LABELS]
    periods_per_day = max(int(periods_per_day or 0), 1)
    periods_per_assignment = max(int(periods_per_assignment or 0), 1)
    slots = [(day, period) for day in days for period in range(1, periods_per_day + 1)]

    teacher_busy = defaultdict(set)
    class_busy = defaultdict(set)
    class_subject_day = defaultdict(set)
    teacher_daily_load = defaultdict(int)
    class_daily_load = defaultdict(int)

    expanded = []
    teacher_load = defaultdict(int)
    class_load = defaultdict(int)
    for assignment in assignments:
        teacher_load[assignment.teacher_id] += 1
        class_load[assignment.academic_class_id] += 1
    for assignment in assignments:
        for slot_index in range(periods_per_assignment):
            expanded.append((teacher_load[assignment.teacher_id] + class_load[assignment.academic_class_id], slot_index, assignment))
    expanded.sort(key=lambda row: (-row[0], row[2].academic_class.code, row[2].subject.name, row[2].teacher.username))

    placed = []
    unplaced = []
    for _, slot_index, assignment in expanded:
        chosen_slot = None
        for day, period in slots:
            teacher_slot_key = (assignment.teacher_id, day, period)
            class_slot_key = (assignment.academic_class_id, day, period)
            daily_subject_key = (assignment.academic_class_id, day)
            if teacher_slot_key in teacher_busy[assignment.teacher_id]:
                continue
            if class_slot_key in class_busy[assignment.academic_class_id]:
                continue
            if assignment.subject_id in class_subject_day[daily_subject_key] and periods_per_day > 1:
                continue
            chosen_slot = (day, period)
            break
        if chosen_slot is None:
            unplaced.append(
                {
                    "class_code": assignment.academic_class.code,
                    "subject": assignment.subject.name,
                    "teacher": assignment.teacher.get_full_name() or assignment.teacher.username,
                    "reason": "No conflict-free slot remained.",
                }
            )
            continue
        day, period = chosen_slot
        teacher_busy[assignment.teacher_id].add((assignment.teacher_id, day, period))
        class_busy[assignment.academic_class_id].add((assignment.academic_class_id, day, period))
        class_subject_day[(assignment.academic_class_id, day)].add(assignment.subject_id)
        teacher_daily_load[(assignment.teacher_id, day)] += 1
        class_daily_load[(assignment.academic_class_id, day)] += 1
        placed.append(
            {
                "day": day,
                "day_label": DAY_LABELS[day],
                "period": period,
                "class_code": assignment.academic_class.code,
                "subject": assignment.subject.name,
                "teacher": assignment.teacher.get_full_name() or assignment.teacher.username,
                "room": f"{room_prefix} {assignment.academic_class.code}",
            }
        )

    placed.sort(key=lambda row: (days.index(row["day"]), row["class_code"], row["period"], row["subject"].lower()))

    by_class = defaultdict(list)
    for row in placed:
        by_class[row["class_code"]].append(row)

    class_tables = []
    for class_code, rows in sorted(by_class.items()):
        grid = {day: {period: None for period in range(1, periods_per_day + 1)} for day in days}
        for row in rows:
            grid[row["day"]][row["period"]] = row
        class_tables.append(
            {
                "class_code": class_code,
                "days": [
                    {
                        "day": day,
                        "label": DAY_LABELS[day],
                        "periods": [grid[day][period] for period in range(1, periods_per_day + 1)],
                    }
                    for day in days
                ],
            }
        )

    return {
        "days": [{"code": day, "label": DAY_LABELS[day]} for day in days],
        "period_numbers": list(range(1, periods_per_day + 1)),
        "placed_rows": placed,
        "class_tables": class_tables,
        "unplaced_rows": unplaced,
        "summary": {
            "assignment_count": len(assignments),
            "requested_slots": len(expanded),
            "placed_slots": len(placed),
            "unplaced_slots": len(unplaced),
        },
    }
