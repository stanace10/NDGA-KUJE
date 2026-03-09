from django.conf import settings
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.contrib.auth import get_user_model
from django.db.models.signals import post_migrate
from django.dispatch import receiver

from apps.audit.services import log_login_failed, log_login_success


@receiver(user_logged_in)
def capture_login_success(sender, request, user, **kwargs):
    log_login_success(actor=user, request=request)


@receiver(user_login_failed)
def capture_login_failure(sender, credentials, request, **kwargs):
    log_login_failed(request=request, username=credentials.get("username", ""))


@receiver(post_migrate)
def harden_anonymous_system_user(sender, **kwargs):
    user_model = get_user_model()
    try:
        anonymous_user = user_model.objects.get(username=settings.ANONYMOUS_USER_NAME)
    except user_model.DoesNotExist:
        return
    updates = []
    if anonymous_user.is_active:
        anonymous_user.is_active = False
        updates.append("is_active")
    if not anonymous_user.is_staff:
        anonymous_user.is_staff = True
        updates.append("is_staff")
    if updates:
        anonymous_user.save(update_fields=updates)
