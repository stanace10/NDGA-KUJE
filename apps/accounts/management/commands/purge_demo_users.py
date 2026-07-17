from django.core.management.base import BaseCommand

from apps.accounts.models import User


DEMO_USERNAME_PREFIXES = (
    'workshop.',
    'demo.',
    'analytics-',
    'hub-',
)
DEMO_USERNAME_SUFFIXES = (
    '-dash',
    '-stage3',
)
DEMO_EXACT_USERNAMES = {
    'principal-settings',
    'it-dash',
    'teacher-dash',
    'student-dash',
}
DEMO_STAFF_PREFIXES = ('WKS-',)
DEMO_STUDENT_PREFIXES = ('WKS-',)


class Command(BaseCommand):
    help = 'Delete known demo, workshop, and test users created during development or workshop prep.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Show users that would be deleted without deleting them.')

    def handle(self, *args, **options):
        dry_run = bool(options['dry_run'])
        users = list(User.objects.exclude(username='AnonymousUser').select_related('staff_profile', 'student_profile'))
        victims = []
        for user in users:
            username = (user.username or '').strip().lower()
            staff_id = (getattr(getattr(user, 'staff_profile', None), 'staff_id', '') or '').strip().upper()
            student_number = (getattr(getattr(user, 'student_profile', None), 'student_number', '') or '').strip().upper()

            username_match = username in DEMO_EXACT_USERNAMES or any(username.startswith(prefix) for prefix in DEMO_USERNAME_PREFIXES) or any(username.endswith(suffix) for suffix in DEMO_USERNAME_SUFFIXES)
            staff_match = bool(staff_id) and any(staff_id.startswith(prefix) for prefix in DEMO_STAFF_PREFIXES)
            student_match = bool(student_number) and any(student_number.startswith(prefix) for prefix in DEMO_STUDENT_PREFIXES)

            if username_match or staff_match or student_match:
                victims.append(user)

        if not victims:
            self.stdout.write(self.style.SUCCESS('No demo or workshop users found.'))
            return

        for user in victims:
            role_code = user.primary_role.code if user.primary_role else ''
            self.stdout.write(f'{user.username} [{role_code}]')

        if dry_run:
            self.stdout.write(self.style.WARNING(f'Dry run only. {len(victims)} user(s) would be deleted.'))
            return

        count = len(victims)
        for user in victims:
            user.delete()
        self.stdout.write(self.style.SUCCESS(f'Deleted {count} demo/workshop user(s).'))
