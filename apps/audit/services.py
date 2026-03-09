from apps.audit.models import AuditCategory, AuditEvent, AuditStatus


def get_client_ip(request):
    if not request:
        return None
    forwarded_for = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def log_event(
    *,
    category,
    event_type,
    status,
    actor=None,
    actor_identifier="",
    message="",
    request=None,
    metadata=None,
):
    metadata = metadata or {}
    path = request.path if request else ""
    return AuditEvent.objects.create(
        actor=actor if getattr(actor, "is_authenticated", False) else None,
        actor_identifier=actor_identifier,
        category=category,
        event_type=event_type,
        status=status,
        message=message,
        path=path,
        ip_address=get_client_ip(request),
        metadata=metadata,
    )


def log_permission_denied_redirect(*, actor, request, destination, reason):
    return log_event(
        category=AuditCategory.PERMISSION,
        event_type="PERMISSION_DENIED_REDIRECT",
        status=AuditStatus.DENIED,
        actor=actor,
        request=request,
        message=reason,
        metadata={"destination": destination},
    )


def log_login_success(*, actor, request):
    return log_event(
        category=AuditCategory.AUTH,
        event_type="LOGIN_SUCCESS",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        message="User authenticated successfully.",
    )


def log_login_failed(*, request, username):
    return log_event(
        category=AuditCategory.AUTH,
        event_type="LOGIN_FAILED",
        status=AuditStatus.FAILURE,
        actor_identifier=username or "",
        request=request,
        message="Invalid credentials.",
    )


def log_password_change(*, actor, request):
    return log_event(
        category=AuditCategory.AUTH,
        event_type="PASSWORD_CHANGE",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        message="Password changed by account owner.",
    )


def log_password_change_denied(*, actor, request, reason):
    return log_event(
        category=AuditCategory.AUTH,
        event_type="PASSWORD_CHANGE_DENIED",
        status=AuditStatus.DENIED,
        actor=actor,
        request=request,
        message=reason,
    )


def log_credentials_reset(*, actor, target_user, request, reset_mode):
    return log_event(
        category=AuditCategory.AUTH,
        event_type="CREDENTIALS_RESET",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        message="Credentials reset by IT Manager.",
        metadata={"target_user_id": str(target_user.id), "mode": reset_mode},
    )


def log_results_edit(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.RESULTS,
        event_type="RESULTS_EDIT",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_results_approval(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.RESULTS,
        event_type="RESULTS_APPROVAL",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_cbt_config_edit(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.CBT,
        event_type="CBT_CONFIG_EDIT",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_election_vote(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.ELECTION,
        event_type="ELECTION_VOTE",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_finance_transaction(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.FINANCE,
        event_type="FINANCE_TRANSACTION",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_lockdown_violation(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.LOCKDOWN,
        event_type="LOCKDOWN_VIOLATION",
        status=AuditStatus.DENIED,
        actor=actor,
        request=request,
        metadata=metadata,
    )


def log_pdf_generation(*, actor, request, metadata=None):
    return log_event(
        category=AuditCategory.SYSTEM,
        event_type="PDF_GENERATED",
        status=AuditStatus.SUCCESS,
        actor=actor,
        request=request,
        metadata=metadata,
    )
