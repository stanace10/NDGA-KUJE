from dataclasses import dataclass

from apps.accounts.constants import (
    PORTAL_ROLE_ACCESS,
    ROLE_DEAN,
    ROLE_FORM_TEACHER,
    ROLE_IT_MANAGER,
    ROLE_PRINCIPAL,
    ROLE_SUBJECT_TEACHER,
    ROLE_VP,
)


class WorkflowState:
    DRAFT = "DRAFT"
    SUBMITTED_TO_DEAN = "SUBMITTED_TO_DEAN"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    COMPILED = "COMPILED"
    VP_APPROVED = "VP_APPROVED"
    PUBLISHED = "PUBLISHED"


class WorkflowAction:
    SUBMIT_TO_DEAN = "SUBMIT_TO_DEAN"
    APPROVE = "APPROVE"
    REJECT = "REJECT"
    COMPILE = "COMPILE"
    VP_APPROVE = "VP_APPROVE"
    PUBLISH = "PUBLISH"


WORKFLOW_ACTION_RULES = {
    WorkflowAction.SUBMIT_TO_DEAN: {
        ROLE_SUBJECT_TEACHER: {WorkflowState.DRAFT, WorkflowState.REJECTED}
    },
    WorkflowAction.APPROVE: {ROLE_DEAN: {WorkflowState.SUBMITTED_TO_DEAN}},
    WorkflowAction.REJECT: {
        ROLE_DEAN: {WorkflowState.SUBMITTED_TO_DEAN},
        ROLE_VP: {WorkflowState.COMPILED},
    },
    WorkflowAction.COMPILE: {ROLE_FORM_TEACHER: {WorkflowState.APPROVED}},
    WorkflowAction.VP_APPROVE: {ROLE_VP: {WorkflowState.COMPILED}},
    WorkflowAction.PUBLISH: {
        ROLE_VP: {WorkflowState.VP_APPROVED},
        ROLE_IT_MANAGER: {WorkflowState.VP_APPROVED},
        ROLE_PRINCIPAL: {WorkflowState.VP_APPROVED},
    },
}


def user_role_codes(user):
    if not getattr(user, "is_authenticated", False):
        return set()
    return user.get_all_role_codes()


def has_any_role(user, role_codes):
    return bool(user_role_codes(user) & set(role_codes))


def has_portal_access(user, portal_key):
    allowed_roles = PORTAL_ROLE_ACCESS.get(portal_key, set())
    return has_any_role(user, allowed_roles)


def can_perform_workflow_action(user, action, current_state):
    role_rules = WORKFLOW_ACTION_RULES.get(action, {})
    roles = user_role_codes(user)
    for role_code, allowed_states in role_rules.items():
        if role_code in roles and current_state in allowed_states:
            return True
    return False


def has_object_permission(user, permission_codename, obj):
    if not getattr(user, "is_authenticated", False):
        return False
    if obj is None:
        return False
    return user.has_perm(permission_codename, obj)


@dataclass(frozen=True)
class AssignmentAccessPolicy:
    owner_field: str = "teacher_id"


def can_access_assigned_object(user, obj, policy=AssignmentAccessPolicy()):
    if not getattr(user, "is_authenticated", False):
        return False
    if user.is_superuser or has_any_role(user, {ROLE_IT_MANAGER, ROLE_PRINCIPAL}):
        return True
    owner_id = getattr(obj, policy.owner_field, None)
    if owner_id is None:
        return False
    return owner_id == user.id

