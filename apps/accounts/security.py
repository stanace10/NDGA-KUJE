import secrets
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.cache import cache
from django.core.mail import send_mail
from django.utils import timezone

_TWO_FACTOR_CACHE_PREFIX = "accounts.privileged_login_2fa"


def privileged_login_ttl_seconds():
    return max(int(getattr(settings, "PRIVILEGED_LOGIN_2FA_TTL_SECONDS", 600)), 60)


def privileged_login_target_email(user):
    email = (getattr(user, "two_factor_email", "") or getattr(user, "email", "") or "").strip()
    if email:
        return email
    username = (getattr(user, "username", "") or "").strip()
    if "@" in username:
        return username
    return ""


def mask_email_address(email):
    local_part, _, domain = (email or "").partition("@")
    if not local_part or not domain:
        return email
    visible_local = local_part[:2]
    masked_local = visible_local + ("*" * max(len(local_part) - len(visible_local), 1))
    domain_head, dot, domain_tail = domain.partition(".")
    if not domain_head:
        return f"{masked_local}@{domain}"
    masked_domain = domain_head[:1] + ("*" * max(len(domain_head) - 1, 1))
    if dot:
        return f"{masked_local}@{masked_domain}.{domain_tail}"
    return f"{masked_local}@{masked_domain}"


def _cache_key(challenge_id):
    return f"{_TWO_FACTOR_CACHE_PREFIX}.{challenge_id}"


def issue_privileged_login_challenge(*, user):
    target_email = privileged_login_target_email(user)
    if not target_email:
        raise ValueError("This privileged account needs a valid recovery email before sign-in.")

    ttl_seconds = privileged_login_ttl_seconds()
    code = f"{secrets.randbelow(1_000_000):06d}"
    challenge_id = secrets.token_urlsafe(24)
    expires_at = timezone.now() + timedelta(seconds=ttl_seconds)
    payload = {
        "user_id": int(user.id),
        "email": target_email,
        "code_hash": make_password(code),
        "expires_at": expires_at.isoformat(),
        "issued_at": timezone.now().isoformat(),
    }
    cache.set(_cache_key(challenge_id), payload, ttl_seconds)
    send_mail(
        subject="NDGA Privileged Login Verification Code",
        message=(
            f"Hello {user.get_full_name() or user.username},\n\n"
            f"Your NDGA privileged-login verification code is: {code}\n"
            f"This code expires in {max(ttl_seconds // 60, 1)} minute(s).\n\n"
            "If you did not initiate this sign-in, contact IT immediately."
        ),
        from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@ndgakuje.org"),
        recipient_list=[target_email],
        fail_silently=False,
    )
    return {
        "challenge_id": challenge_id,
        "email": target_email,
        "masked_email": mask_email_address(target_email),
        "expires_at": expires_at,
        "ttl_seconds": ttl_seconds,
    }


def get_privileged_login_challenge(challenge_id):
    if not challenge_id:
        return None
    return cache.get(_cache_key(challenge_id))


def clear_privileged_login_challenge(challenge_id):
    if challenge_id:
        cache.delete(_cache_key(challenge_id))


def verify_privileged_login_challenge(*, challenge_id, user, raw_code):
    payload = get_privileged_login_challenge(challenge_id)
    if not payload:
        return False
    if int(payload.get("user_id") or 0) != int(user.id):
        return False
    expires_at = datetime.fromisoformat(payload["expires_at"])
    if timezone.is_naive(expires_at):
        expires_at = timezone.make_aware(expires_at, timezone.get_current_timezone())
    if timezone.now() >= expires_at:
        clear_privileged_login_challenge(challenge_id)
        return False
    if not check_password((raw_code or "").strip(), payload.get("code_hash", "")):
        return False
    clear_privileged_login_challenge(challenge_id)
    return True