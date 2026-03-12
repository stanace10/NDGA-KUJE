from django.urls import reverse

from apps.accounts.permissions import SCOPE_ISSUE_LOGIN_CODES, has_portal_access, has_scope
from apps.accounts.constants import ROLE_HOME_PORTAL
from apps.tenancy.utils import build_portal_url


def get_primary_role_code(user):
    if not user.primary_role_id:
        return None
    return user.primary_role.code


def resolve_role_home_url(user, request):
    preferred_portal = ""
    if hasattr(request, "session"):
        preferred_portal = (request.session.get("last_authenticated_portal") or "").strip().lower()
    special_portal_paths = {
        "cbt": reverse("cbt:home"),
        "election": reverse("elections:home"),
    }
    if preferred_portal in special_portal_paths and has_portal_access(user, preferred_portal):
        return build_portal_url(request, preferred_portal, special_portal_paths[preferred_portal])

    role_code = get_primary_role_code(user)
    portal_key = ROLE_HOME_PORTAL.get(role_code, "staff")
    return build_portal_url(request, portal_key, "/")


def apply_self_service_password_change(user, raw_password):
    user.set_password(raw_password)
    user.password_changed_count += 1
    user.must_change_password = False
    user.clear_login_code()
    user.save(
        update_fields=[
            "password",
            "password_changed_count",
            "must_change_password",
            "login_code_hash",
            "login_code_expires_at",
        ]
    )


def issue_login_code(actor, target_user):
    if not has_scope(actor, SCOPE_ISSUE_LOGIN_CODES):
        raise PermissionError("You do not have scope to issue login codes.")
    target_user.password_changed_count = 0
    target_user.must_change_password = False
    code = target_user.set_login_code()
    target_user.save(
        update_fields=[
            "password_changed_count",
            "must_change_password",
            "login_code_hash",
            "login_code_expires_at",
        ]
    )
    return code


def reset_password_by_it_manager(actor, target_user, temporary_password):
    if not has_scope(actor, SCOPE_ISSUE_LOGIN_CODES):
        raise PermissionError("You do not have scope to reset user passwords.")
    target_user.set_password(temporary_password)
    target_user.password_changed_count = 0
    target_user.must_change_password = False
    target_user.clear_login_code()
    target_user.save(
        update_fields=[
            "password",
            "password_changed_count",
            "must_change_password",
            "login_code_hash",
            "login_code_expires_at",
        ]
    )
