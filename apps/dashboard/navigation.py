from __future__ import annotations

from typing import Iterable
from apps.accounts.constants import (
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_STUDENT,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)
from apps.tenancy.utils import (
    cloud_staff_operations_lan_only_enabled,
    lan_runtime_restrictions_enabled,
    user_has_lan_only_operation_roles,
)


PORTAL_TITLES = {
    "portal": "Portal Access",
    "student": "Student Portal",
    "staff": "Staff Portal",
    "it": "IT Manager Portal",
    "bursar": "Bursar Portal",
    "vp": "Vice Principal Portal",
    "principal": "Principal Portal",
    "cbt": "CBT Portal",
    "election": "Election Portal",
    "landing": "NDGA Platform",
}


def _nav_item(
    *,
    label: str,
    url: str,
    request_path: str,
    matches: Iterable[str] | None = None,
    section: str = "",
    children: list[dict] | None = None,
    icon: str = "",
):
    prefixes = tuple(matches or (url,))

    def _is_match(prefix: str):
        if prefix == "/":
            return request_path == "/"
        if prefix.endswith("$"):
            return request_path == prefix[:-1]
        return request_path.startswith(prefix)

    child_rows = children or []
    direct_is_active = any(_is_match(prefix) for prefix in prefixes)
    child_is_active = any(bool(child.get("active")) for child in child_rows)
    return {
        "label": label,
        "url": url,
        "active": direct_is_active or child_is_active,
        "direct_active": direct_is_active,
        "section": section,
        "children": child_rows,
        "icon": icon or _default_icon_for_label(label),
    }


def _default_icon_for_label(label: str):
    name = (label or "").strip().lower()
    keyword_map = [
        ("logout", "logout"),
        ("setting", "settings"),
        ("account", "settings"),
        ("profile", "user"),
        ("student", "user"),
        ("staff", "user"),
        ("attendance", "attendance"),
        ("calendar", "attendance"),
        ("result", "results"),
        ("score", "results"),
        ("publish", "results"),
        ("approval", "results"),
        ("dean", "results"),
        ("transcript", "transcript"),
        ("subject", "subjects"),
        ("academic", "subjects"),
        ("question", "subjects"),
        ("exam", "subjects"),
        ("cbt", "subjects"),
        ("election", "subjects"),
        ("vote", "subjects"),
        ("finance", "finance"),
        ("charge", "finance"),
        ("payment", "finance"),
        ("expense", "finance"),
        ("salary", "finance"),
        ("notification", "notification"),
        ("message", "notification"),
        ("challenge", "results"),
        ("teaser", "results"),
        ("audit", "transcript"),
        ("sync", "settings"),
        ("backup", "settings"),
        ("dashboard", "home"),
        ("home", "home"),
    ]
    for keyword, icon in keyword_map:
        if keyword in name:
            return icon
    return "home"


def build_portal_navigation(*, portal_key: str, role_codes: set[str], request_path: str, setup_is_ready: bool):
    items = []
    lan_runtime_restricted = lan_runtime_restrictions_enabled()
    cloud_staff_admin_restricted = (
        cloud_staff_operations_lan_only_enabled() and user_has_lan_only_operation_roles(role_codes)
    )

    if portal_key == "it":
        if cloud_staff_admin_restricted:
            items.append(
                _nav_item(
                    label="Dashboard",
                    url="/portal/it/",
                    request_path=request_path,
                    matches=("/", "/portal/it/$"),
                )
            )
            items.append(
                _nav_item(
                    label="Admissions Applicants",
                    url="/portal/it/admissions/",
                    request_path=request_path,
                    matches=("/portal/it/admissions/",),
                )
            )
            items.append(
                _nav_item(
                    label="Audit Logs",
                    url="/audit/events/",
                    request_path=request_path,
                    matches=("/audit/events/",),
                )
            )
            items.append(
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                )
            )
            items.append(
                _nav_item(
                    label="Account Security",
                    url="/portal/account/security/",
                    request_path=request_path,
                    matches=("/portal/account/security/",),
                )
            )
            items.append(
                _nav_item(
                    label="Logout",
                    url="/auth/logout/",
                    request_path=request_path,
                    matches=("/auth/logout/",),
                )
            )
            return items
        if lan_runtime_restricted:
            items.append(
                _nav_item(
                    label="Dashboard",
                    url="/portal/it/",
                    request_path=request_path,
                    matches=("/", "/portal/it/$"),
                )
            )
            items.append(
                _nav_item(
                    label="Messaging Center",
                    url="/notifications/media/",
                    request_path=request_path,
                    matches=("/notifications/media/",),
                )
            )
            items.append(
                _nav_item(
                    label="CBT Setup",
                    url="/cbt/it/activation/",
                    request_path=request_path,
                    matches=("/cbt/it/",),
                )
            )
            items.append(
                _nav_item(
                    label="Election Setup",
                    url="/elections/it/manage/",
                    request_path=request_path,
                    matches=("/elections/it/manage/", "/elections/"),
                )
            )
            items.append(
                _nav_item(
                    label="Audit Logs",
                    url="/audit/events/",
                    request_path=request_path,
                    matches=("/audit/events/",),
                )
            )
            items.append(
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                )
            )
            items.append(
                _nav_item(
                    label="Account Security",
                    url="/portal/account/security/",
                    request_path=request_path,
                    matches=("/portal/account/security/",),
                )
            )
            items.append(
                _nav_item(
                    label="Logout",
                    url="/auth/logout/",
                    request_path=request_path,
                    matches=("/auth/logout/",),
                )
            )
            return items
        items.append(
            _nav_item(
                label="Dashboard",
                url="/portal/it/",
                request_path=request_path,
                matches=("/", "/portal/it/$"),
            )
        )
        items.append(
            _nav_item(
                label="Admissions Applicants",
                url="/portal/it/admissions/",
                request_path=request_path,
                matches=("/portal/it/admissions/",),
            )
        )
        items.append(
            _nav_item(
                label="Staff Management",
                url="/auth/it/user-provisioning/staff/directory/",
                request_path=request_path,
                matches=(
                    "/auth/it/user-provisioning/staff/directory/",
                    "/auth/it/user-provisioning/staff/",
                    "/auth/it/staff/",
                ),
            )
        )
        items.append(
            _nav_item(
                label="Student Management",
                url="/auth/it/user-provisioning/students/directory/",
                request_path=request_path,
                matches=(
                    "/auth/it/user-provisioning/students/directory/",
                    "/auth/it/user-provisioning/students/",
                    "/auth/it/student/",
                ),
            )
        )
        items.append(
            _nav_item(
                label="Result Management",
                url="/results/approval/",
                request_path=request_path,
                matches=("/results/approval/",),
            )
        )
        items.append(
            _nav_item(
                label="Performance Report",
                url="/results/report/performance/",
                request_path=request_path,
                matches=("/results/report/",),
            )
        )
        items.append(
            _nav_item(
                label="Messaging Center",
                url="/notifications/media/",
                request_path=request_path,
                matches=("/notifications/media/",),
            )
        )
        items.append(
            _nav_item(
                label="CBT Setup",
                url="/cbt/it/activation/",
                request_path=request_path,
                matches=("/cbt/it/",),
            )
        )
        items.append(
            _nav_item(
                label="Election Setup",
                url="/elections/it/manage/",
                request_path=request_path,
                matches=("/elections/it/manage/", "/elections/"),
            )
        )
        settings_url = "/setup/wizard/" if not setup_is_ready else "/setup/session-term/"
        items.append(
            _nav_item(
                label="Session & Calendar",
                url=settings_url,
                request_path=request_path,
                matches=("/setup/", "/attendance/calendar/"),
            )
        )
        items.append(
            _nav_item(
                label="School Settings",
                url="/results/settings/",
                request_path=request_path,
                matches=("/results/settings/",),
            )
        )
        items.append(
            _nav_item(
                label="Audit Logs",
                url="/audit/events/",
                request_path=request_path,
                matches=("/audit/events/",),
            )
        )
        items.append(
            _nav_item(
                label="Notifications",
                url="/notifications/center/",
                request_path=request_path,
                matches=("/notifications/",),
            )
        )
        items.append(
            _nav_item(
                label="Account Security",
                url="/portal/account/security/",
                request_path=request_path,
                matches=("/portal/account/security/",),
            )
        )
        items.append(
            _nav_item(
                label="Logout",
                url="/auth/logout/",
                request_path=request_path,
                matches=("/auth/logout/",),
            )
        )
        return items

    if portal_key == "staff":
        if cloud_staff_admin_restricted:
            items.append(_nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/staff/$")))
            items.append(
                _nav_item(
                    label="Results Overview",
                    url="/portal/staff/results-overview/",
                    request_path=request_path,
                    matches=("/portal/staff/results-overview/",),
                )
            )
            if ROLE_FORM_TEACHER in role_codes:
                items.append(
                    _nav_item(
                        label="Attendance Overview",
                        url="/portal/staff/attendance-overview/",
                        request_path=request_path,
                        matches=("/portal/staff/attendance-overview/",),
                    )
                )
            items.append(
                _nav_item(
                    label="Profile",
                    url="/portal/staff/profile/",
                    request_path=request_path,
                    matches=("/portal/staff/profile/",),
                )
            )
            if role_codes & {ROLE_DEAN, ROLE_FORM_TEACHER}:
                items.append(
                    _nav_item(
                        label="Performance Report",
                        url="/results/report/performance/",
                        request_path=request_path,
                        matches=("/results/report/",),
                    )
                )
            items.append(
                _nav_item(
                    label="Settings",
                    url="/portal/staff/settings/",
                    request_path=request_path,
                    matches=("/portal/staff/settings/",),
                )
            )
            items.append(
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                )
            )
            items.append(_nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)))
            return items
        if lan_runtime_restricted:
            items.append(_nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/staff/$")))
            items.append(
                _nav_item(
                    label="Profile",
                    url="/portal/staff/profile/",
                    request_path=request_path,
                    matches=("/portal/staff/profile/",),
                )
            )
            if ROLE_FORM_TEACHER in role_codes:
                items.append(
                    _nav_item(
                        label="Attendance",
                        url="/attendance/form/mark/",
                        request_path=request_path,
                        matches=("/attendance/form/",),
                    )
                )
            if role_codes & {ROLE_SUBJECT_TEACHER, ROLE_DEAN, ROLE_FORM_TEACHER}:
                items.append(
                    _nav_item(
                        label="Result Entry",
                        url="/results/grade-entry/?view=scores",
                        request_path=request_path,
                        matches=("/results/grade-entry/",),
                    )
                )
                items.append(
                    _nav_item(
                        label="CBT Entry",
                        url="/cbt/authoring/",
                        request_path=request_path,
                        matches=("/cbt/authoring/", "/cbt/authoring"),
                    )
                )
                items.append(
                    _nav_item(
                        label="Lesson Planner",
                        url="/portal/staff/lesson-planner/",
                        request_path=request_path,
                        matches=("/portal/staff/lesson-planner/",),
                    )
                )
                items.append(
                    _nav_item(
                        label="Classroom LMS",
                        url="/portal/staff/lms/",
                        request_path=request_path,
                        matches=("/portal/staff/lms/",),
                    )
                )
            if ROLE_DEAN in role_codes:
                items.append(
                    _nav_item(
                        label="Academic Approval",
                        url="/results/dean/review/results/",
                        request_path=request_path,
                        matches=("/results/dean/", "/cbt/dean/"),
                    )
                )
            if role_codes & {ROLE_DEAN, ROLE_FORM_TEACHER}:
                items.append(
                    _nav_item(
                        label="Performance Report",
                        url="/results/report/performance/",
                        request_path=request_path,
                        matches=("/results/report/",),
                    )
                )
            if ROLE_DEAN in role_codes:
                items.append(
                    _nav_item(
                        label="Messaging Center",
                        url="/notifications/media/",
                        request_path=request_path,
                        matches=("/notifications/media/",),
                    )
                )
            items.append(
                _nav_item(
                    label="Settings",
                    url="/portal/staff/settings/",
                    request_path=request_path,
                    matches=("/portal/staff/settings/",),
                )
            )
            items.append(
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                )
            )
            items.append(_nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)))
            return items
        compact_teaching_menu = bool(
            ROLE_FORM_TEACHER in role_codes
            and ROLE_SUBJECT_TEACHER in role_codes
            and ROLE_DEAN not in role_codes
            and ROLE_VP not in role_codes
            and ROLE_PRINCIPAL not in role_codes
            and ROLE_IT_MANAGER not in role_codes
        )
        items.append(_nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/staff/$")))
        items.append(
            _nav_item(
                label="Profile",
                url="/portal/staff/profile/",
                request_path=request_path,
                matches=("/portal/staff/profile/",),
            )
        )
        if ROLE_FORM_TEACHER in role_codes:
            items.append(
                _nav_item(
                    label="Attendance",
                    url="/attendance/form/mark/",
                    request_path=request_path,
                    matches=("/attendance/form/",),
                )
            )
        if role_codes & {ROLE_SUBJECT_TEACHER, ROLE_DEAN, ROLE_FORM_TEACHER}:
            items.append(
                _nav_item(
                    label="Result Entry",
                    url="/results/grade-entry/?view=scores",
                    request_path=request_path,
                    matches=("/results/grade-entry/",),
                )
            )
            items.append(
                _nav_item(
                    label="CBT Entry",
                    url="/cbt/authoring/",
                    request_path=request_path,
                    matches=("/cbt/authoring/", "/cbt/authoring"),
                )
            )
            items.append(
                _nav_item(
                    label="Lesson Planner",
                    url="/portal/staff/lesson-planner/",
                    request_path=request_path,
                    matches=("/portal/staff/lesson-planner/",),
                )
            )
            items.append(
                _nav_item(
                    label="Classroom LMS",
                    url="/portal/staff/lms/",
                    request_path=request_path,
                    matches=("/portal/staff/lms/",),
                )
            )
        if ROLE_DEAN in role_codes:
            items.append(
                _nav_item(
                    label="Academic Approval",
                    url="/results/dean/review/results/",
                    request_path=request_path,
                    matches=("/results/dean/", "/cbt/dean/"),
                    children=[
                        _nav_item(
                            label="Result Review",
                            url="/results/dean/review/results/",
                            request_path=request_path,
                            matches=("/results/dean/",),
                        ),
                        _nav_item(
                            label="Exam Review",
                            url="/results/dean/review/exams/",
                            request_path=request_path,
                            matches=("/results/dean/", "/cbt/dean/"),
                        ),
                    ],
                )
            )
        if role_codes & {ROLE_DEAN, ROLE_FORM_TEACHER}:
            items.append(
                _nav_item(
                    label="Performance Report",
                    url="/results/report/performance/",
                    request_path=request_path,
                    matches=("/results/report/",),
                )
            )
        if ROLE_DEAN in role_codes:
            items.append(
                _nav_item(
                    label="Messaging Center",
                    url="/notifications/media/",
                    request_path=request_path,
                    matches=("/notifications/media/",),
                )
            )
        items.append(
            _nav_item(
                label="Settings",
                url="/portal/staff/settings/",
                request_path=request_path,
                matches=("/portal/staff/settings/",),
            )
        )
        items.append(
            _nav_item(
                label="Notifications",
                url="/notifications/center/",
                request_path=request_path,
                matches=("/notifications/",),
            )
        )
        items.append(_nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)))
        return items

    if portal_key == "vp":
        if cloud_staff_admin_restricted:
            items.extend(
                [
                    _nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/vp/$")),
                    _nav_item(
                        label="Profile",
                        url="/portal/staff/profile/",
                        request_path=request_path,
                        matches=("/portal/staff/profile/",),
                    ),
                    _nav_item(
                        label="Performance Report",
                        url="/results/report/performance/",
                        request_path=request_path,
                        matches=("/results/report/",),
                    ),
                    _nav_item(
                        label="Admissions Applicants",
                        url="/portal/vp/admissions/",
                        request_path=request_path,
                        matches=("/portal/vp/admissions/",),
                    ),
                    _nav_item(
                        label="Notifications",
                        url="/notifications/center/",
                        request_path=request_path,
                        matches=("/notifications/",),
                    ),
                    _nav_item(
                        label="Settings",
                        url="/portal/staff/settings/",
                        request_path=request_path,
                        matches=("/portal/staff/settings/",),
                    ),
                    _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
                ]
            )
            return items
        if lan_runtime_restricted:
            items.extend(
                [
                    _nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/vp/$")),
                    _nav_item(
                        label="Profile",
                        url="/portal/staff/profile/",
                        request_path=request_path,
                        matches=("/portal/staff/profile/",),
                    ),
                    _nav_item(
                        label="Class Management",
                        url="/attendance/form/classes/",
                        request_path=request_path,
                        matches=("/attendance/form/",),
                    ),
                    _nav_item(
                        label="Staff Management",
                        url="/auth/it/user-provisioning/staff/directory/",
                        request_path=request_path,
                        matches=(
                            "/auth/it/user-provisioning/staff/directory/",
                            "/auth/it/user-provisioning/staff/",
                            "/auth/it/staff/",
                        ),
                    ),
                    _nav_item(
                        label="Student Management",
                        url="/auth/it/user-provisioning/students/directory/",
                        request_path=request_path,
                        matches=(
                            "/auth/it/user-provisioning/students/directory/",
                            "/auth/it/user-provisioning/students/",
                            "/auth/it/student/",
                        ),
                    ),
                    _nav_item(
                        label="Result Management",
                        url="/results/approval/",
                        request_path=request_path,
                        matches=("/results/approval/",),
                    ),
                    _nav_item(
                        label="Messaging Center",
                        url="/notifications/media/",
                        request_path=request_path,
                        matches=("/notifications/media/",),
                    ),
                    _nav_item(
                        label="Performance Report",
                        url="/results/report/performance/",
                        request_path=request_path,
                        matches=("/results/report/",),
                    ),
                    _nav_item(
                        label="Notifications",
                        url="/notifications/center/",
                        request_path=request_path,
                        matches=("/notifications/",),
                    ),
                    _nav_item(
                        label="Settings",
                        url="/portal/staff/settings/",
                        request_path=request_path,
                        matches=("/portal/staff/settings/",),
                    ),
                    _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
                ]
            )
            return items
        items.extend(
            [
                _nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/vp/$")),
                _nav_item(
                    label="Profile",
                    url="/portal/staff/profile/",
                    request_path=request_path,
                    matches=("/portal/staff/profile/",),
                ),
                _nav_item(
                    label="Class Management",
                    url="/attendance/form/classes/",
                    request_path=request_path,
                    matches=("/attendance/form/",),
                ),
                _nav_item(
                    label="Admissions Applicants",
                    url="/portal/vp/admissions/",
                    request_path=request_path,
                    matches=("/portal/vp/admissions/",),
                ),
                _nav_item(
                    label="Staff Management",
                    url="/auth/it/user-provisioning/staff/directory/",
                    request_path=request_path,
                    matches=(
                        "/auth/it/user-provisioning/staff/directory/",
                        "/auth/it/user-provisioning/staff/",
                        "/auth/it/staff/",
                    ),
                ),
                _nav_item(
                    label="Student Management",
                    url="/auth/it/user-provisioning/students/directory/",
                    request_path=request_path,
                    matches=(
                        "/auth/it/user-provisioning/students/directory/",
                        "/auth/it/user-provisioning/students/",
                        "/auth/it/student/",
                    ),
                ),
                _nav_item(
                    label="Result Management",
                    url="/results/approval/",
                    request_path=request_path,
                    matches=("/results/approval/",),
                ),
                _nav_item(
                    label="Messaging Center",
                    url="/notifications/media/",
                    request_path=request_path,
                    matches=("/notifications/media/",),
                ),
                _nav_item(
                    label="Performance Report",
                    url="/results/report/performance/",
                    request_path=request_path,
                    matches=("/results/report/",),
                ),
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                ),
                _nav_item(
                    label="Settings",
                    url="/portal/staff/settings/",
                    request_path=request_path,
                    matches=("/portal/staff/settings/",),
                ),
                _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
            ]
        )
        return items


    if portal_key == "principal":
        if cloud_staff_admin_restricted:
            items.extend(
                [
                    _nav_item(
                        label="Dashboard",
                        url="/",
                        request_path=request_path,
                        matches=("/", "/portal/principal/$"),
                    ),
                    _nav_item(
                        label="Performance Report",
                        url="/results/report/performance/",
                        request_path=request_path,
                        matches=("/results/report/",),
                    ),
                    _nav_item(
                        label="Admissions Applicants",
                        url="/portal/principal/admissions/",
                        request_path=request_path,
                        matches=("/portal/principal/admissions/",),
                    ),
                    _nav_item(
                        label="Notifications",
                        url="/notifications/center/",
                        request_path=request_path,
                        matches=("/notifications/",),
                    ),
                    _nav_item(
                        label="Account Security",
                        url="/portal/account/security/",
                        request_path=request_path,
                        matches=("/portal/account/security/",),
                    ),
                    _nav_item(
                        label="Settings",
                        url="/portal/principal/settings/",
                        request_path=request_path,
                        matches=("/portal/principal/settings/",),
                    ),
                    _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
                ]
            )
            return items
        if lan_runtime_restricted:
            items.extend(
                [
                    _nav_item(
                        label="Dashboard",
                        url="/",
                        request_path=request_path,
                        matches=("/", "/portal/principal/$"),
                    ),
                    _nav_item(
                        label="Election Center",
                        url="/elections/",
                        request_path=request_path,
                        matches=("/elections/",),
                    ),
                    _nav_item(
                        label="Account Security",
                        url="/portal/account/security/",
                        request_path=request_path,
                        matches=("/portal/account/security/",),
                    ),
                    _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
                ]
            )
            return items
        items.extend(
            [
                _nav_item(
                    label="Dashboard",
                    url="/",
                    request_path=request_path,
                    matches=("/", "/portal/principal/$"),
                ),
                _nav_item(
                    label="Admissions Applicants",
                    url="/portal/principal/admissions/",
                    request_path=request_path,
                    matches=("/portal/principal/admissions/",),
                ),
                _nav_item(
                    label="Staff Management",
                    url="/auth/it/user-provisioning/staff/directory/",
                    request_path=request_path,
                    matches=(
                        "/auth/it/user-provisioning/staff/directory/",
                        "/auth/it/user-provisioning/staff/",
                        "/auth/it/staff/",
                    ),
                ),
                _nav_item(
                    label="Student Management",
                    url="/auth/it/user-provisioning/students/directory/",
                    request_path=request_path,
                    matches=(
                        "/auth/it/user-provisioning/students/directory/",
                        "/auth/it/user-provisioning/students/",
                        "/auth/it/student/",
                    ),
                ),
                _nav_item(
                    label="Result Management",
                    url="/results/approval/",
                    request_path=request_path,
                    matches=("/results/approval/",),
                ),
                _nav_item(
                    label="Performance Report",
                    url="/results/report/performance/",
                    request_path=request_path,
                    matches=("/results/report/",),
                ),
                _nav_item(
                    label="Finance Oversight",
                    url="/finance/summary/",
                    request_path=request_path,
                    matches=("/finance/summary/",),
                ),
                _nav_item(
                    label="Messaging Center",
                    url="/notifications/media/",
                    request_path=request_path,
                    matches=("/notifications/media/",),
                ),
                _nav_item(
                    label="Account Security",
                    url="/portal/account/security/",
                    request_path=request_path,
                    matches=("/portal/account/security/",),
                ),
                _nav_item(
                    label="Settings",
                    url="/portal/principal/settings/",
                    request_path=request_path,
                    matches=("/portal/principal/settings/",),
                ),
                _nav_item(
                    label="Election Live",
                    url="/portal/principal/election-live/",
                    request_path=request_path,
                    matches=("/elections/", "/portal/principal/election-live/"),
                ),
                _nav_item(
                    label="Document Vault",
                    url="/portal/principal/documents/",
                    request_path=request_path,
                    matches=("/portal/principal/documents/",),
                ),
                _nav_item(
                    label="Weekly Challenge",
                    url="/portal/it/weekly-challenge/",
                    request_path=request_path,
                    matches=("/portal/it/weekly-challenge/",),
                ),
                _nav_item(
                    label="Clubs & Societies",
                    url="/portal/clubs/",
                    request_path=request_path,
                    matches=("/portal/clubs/",),
                ),
                _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
            ]
        )
        return items


    if portal_key == "student":
        result_children = [
            _nav_item(
                label="Term Results",
                url="/pdfs/student/reports/",
                request_path=request_path,
                matches=("/pdfs/student/reports/",),
            ),
            _nav_item(
                label="Transcript",
                url="/portal/student/transcript/",
                request_path=request_path,
                matches=("/portal/student/transcript/",),
            ),
        ]
        items.extend(
            [
                _nav_item(label="Dashboard", url="/", request_path=request_path, matches=("/", "/portal/student/$")),
                _nav_item(
                    label="Profile",
                    url="/portal/student/profile/",
                    request_path=request_path,
                    matches=("/portal/student/profile/",),
                ),
                _nav_item(
                    label="Attendance",
                    url="/portal/student/attendance/",
                    request_path=request_path,
                    matches=("/portal/student/attendance/",),
                ),
                _nav_item(
                    label="Results",
                    url="/pdfs/student/reports/",
                    request_path=request_path,
                    matches=("/pdfs/student/", "/portal/student/transcript/"),
                    children=result_children,
                ),
                _nav_item(
                    label="Subjects",
                    url="/portal/student/subjects/",
                    request_path=request_path,
                    matches=("/portal/student/subjects/",),
                ),
                _nav_item(
                    label="Learning Hub",
                    url="/portal/student/learning-hub/",
                    request_path=request_path,
                    matches=("/portal/student/learning-hub/",),
                ),
                _nav_item(
                    label="LMS Classroom",
                    url="/portal/student/lms/",
                    request_path=request_path,
                    matches=("/portal/student/lms/",),
                ),
                _nav_item(
                    label="Weekly Challenge",
                    url="/portal/student/weekly-challenge/",
                    request_path=request_path,
                    matches=("/portal/student/weekly-challenge/",),
                ),
                _nav_item(
                    label="Digital ID",
                    url="/portal/student/id-card/",
                    request_path=request_path,
                    matches=("/portal/student/id-card/",),
                ),
                _nav_item(
                    label="Documents",
                    url="/portal/student/documents/",
                    request_path=request_path,
                    matches=("/portal/student/documents/",),
                ),
                _nav_item(
                    label="Finance",
                    url="/finance/student/overview/",
                    request_path=request_path,
                    matches=("/finance/student/overview/",),
                ),
                _nav_item(
                    label="Settings",
                    url="/portal/student/settings/",
                    request_path=request_path,
                    matches=("/portal/student/settings/",),
                ),
                _nav_item(
                    label="Notifications",
                    url="/notifications/center/",
                    request_path=request_path,
                    matches=("/notifications/",),
                ),
                _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
            ]
        )
        return items

    if portal_key == "bursar":
        if cloud_staff_admin_restricted:
            items.extend(
                [
                    _nav_item(
                        label="Dashboard",
                        url="/finance/bursar/dashboard/",
                        request_path=request_path,
                        matches=("/", "/portal/bursar/$", "/finance/bursar/dashboard/"),
                    ),
                    _nav_item(
                        label="Applicant Fees",
                        url="/portal/bursar/admissions/",
                        request_path=request_path,
                        matches=("/portal/bursar/admissions/",),
                    ),
                    _nav_item(
                        label="Notifications",
                        url="/notifications/center/",
                        request_path=request_path,
                        matches=("/notifications/",),
                    ),
                    _nav_item(
                        label="Account Security",
                        url="/portal/account/security/",
                        request_path=request_path,
                        matches=("/portal/account/security/",),
                    ),
                    _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
                ]
            )
            return items
        items.extend(
            [
                _nav_item(
                    label="Dashboard",
                    url="/finance/bursar/dashboard/",
                    request_path=request_path,
                    matches=("/", "/portal/bursar/$", "/finance/bursar/dashboard/"),
                ),
                _nav_item(
                    label="Applicant Fees",
                    url="/portal/bursar/admissions/",
                    request_path=request_path,
                    matches=("/portal/bursar/admissions/",),
                ),
                _nav_item(
                    label="Fees",
                    url="/finance/bursar/fees/",
                    request_path=request_path,
                    matches=("/finance/bursar/fees/", "/finance/bursar/payments/", "/finance/bursar/fees/student/"),
                ),
                _nav_item(
                    label="Debtors",
                    url="/finance/bursar/debtors/",
                    request_path=request_path,
                    matches=("/finance/bursar/debtors/",),
                ),
                _nav_item(
                    label="Expenses",
                    url="/finance/bursar/expenses/",
                    request_path=request_path,
                    matches=("/finance/bursar/expenses/",),
                ),
                _nav_item(
                    label="Staff Payments",
                    url="/finance/bursar/staff-payments/",
                    request_path=request_path,
                    matches=("/finance/bursar/staff-payments/", "/finance/bursar/salaries/"),
                ),
                _nav_item(
                    label="Assets",
                    url="/finance/bursar/assets/",
                    request_path=request_path,
                    matches=("/finance/bursar/assets/",),
                ),
                _nav_item(
                    label="Messaging",
                    url="/finance/bursar/messaging/",
                    request_path=request_path,
                    matches=("/finance/bursar/messaging/",),
                ),
                _nav_item(
                    label="Performance Report",
                    url="/results/report/performance/",
                    request_path=request_path,
                    matches=("/results/report/",),
                ),
                _nav_item(
                    label="Account Security",
                    url="/portal/account/security/",
                    request_path=request_path,
                    matches=("/portal/account/security/",),
                ),
                _nav_item(
                    label="Settings",
                    url="/finance/bursar/settings/",
                    request_path=request_path,
                    matches=("/finance/bursar/settings/", "/finance/bursar/charges/"),
                ),
                _nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)),
            ]
        )
        return items

    if portal_key == "cbt":
        if ROLE_STUDENT in role_codes:
            items.append(
                _nav_item(
                    label="Available Exams",
                    url="/cbt/exams/available/",
                    request_path=request_path,
                    matches=("/cbt/exams/", "/cbt/attempts/"),
                )
            )
        else:
            if role_codes & {ROLE_SUBJECT_TEACHER, ROLE_FORM_TEACHER, ROLE_DEAN, ROLE_PRINCIPAL, ROLE_IT_MANAGER}:
                items.append(
                    _nav_item(
                        label="CBT Authoring",
                        url="/cbt/authoring/",
                        request_path=request_path,
                        matches=("/cbt/authoring/",),
                    )
                )
            if role_codes & {ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL}:
                items.append(
                    _nav_item(
                        label="Dean Workspace",
                        url="/results/dean/review/",
                        request_path=request_path,
                        matches=("/results/dean/", "/cbt/dean/"),
                    )
                )
            if role_codes & {ROLE_SUBJECT_TEACHER, ROLE_FORM_TEACHER, ROLE_DEAN, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP}:
                items.append(
                    _nav_item(
                        label="Theory Marking",
                        url="/cbt/marking/theory/",
                        request_path=request_path,
                        matches=("/cbt/marking/",),
                    )
                )
                items.append(
                    _nav_item(
                        label="Simulation Marking",
                        url="/cbt/marking/simulations/",
                        request_path=request_path,
                        matches=("/cbt/marking/simulations/",),
                    )
                )
            if ROLE_IT_MANAGER in role_codes:
                items.append(
                    _nav_item(
                        label="IT Activation",
                        url="/cbt/it/activation/",
                        request_path=request_path,
                        matches=("/cbt/it/activation/",),
                    )
                )
                items.append(
                    _nav_item(
                        label="Simulation Registry",
                        url="/cbt/it/simulations/",
                        request_path=request_path,
                        matches=("/cbt/it/simulations/",),
                    )
                )
                items.append(
                    _nav_item(
                        label="Lockdown Controls",
                        url="/cbt/it/lockdown/",
                        request_path=request_path,
                        matches=("/cbt/it/lockdown/",),
                    )
                )
        items.append(_nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)))
        return items

    if portal_key == "election":
        items.append(
            _nav_item(
                label="Home",
                url="/",
                request_path=request_path,
                matches=("/", "/portal/election/$"),
            )
        )
        items.append(
            _nav_item(
                label="Vote",
                url="/elections/",
                request_path=request_path,
                matches=("/elections/",),
            )
        )
        if ROLE_IT_MANAGER in role_codes:
            items.append(
                _nav_item(
                    label="Election Setup",
                    url="/elections/it/manage/",
                    request_path=request_path,
                    matches=("/elections/it/manage/",),
                )
            )
        if role_codes & {ROLE_IT_MANAGER, ROLE_PRINCIPAL}:
            items.append(
                _nav_item(
                    label="Live Analytics",
                    url="/elections/",
                    request_path=request_path,
                    matches=("/elections/analytics/", "/elections/"),
                )
            )
        items.append(_nav_item(label="Logout", url="/auth/logout/", request_path=request_path, matches=("/auth/logout/",)))
        return items

    return items
