from django.conf import settings
from django.core.cache import cache
from django.core.management.base import BaseCommand, CommandError
from django.db import connection


class Command(BaseCommand):
    help = "Verify Stage 0 runtime dependencies and static build output."

    def handle(self, *args, **options):
        failures = []

        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            self.stdout.write(self.style.SUCCESS("PostgreSQL connection: OK"))
        except Exception as exc:  # pragma: no cover - runtime environment check
            failures.append(f"PostgreSQL connection failed: {exc}")

        try:
            cache.set("ndga_stage0_ping", "ok", timeout=15)
            response = cache.get("ndga_stage0_ping")
            if response != "ok":
                raise RuntimeError("unexpected cache response")
            self.stdout.write(self.style.SUCCESS("Redis cache connection: OK"))
        except Exception as exc:  # pragma: no cover - runtime environment check
            failures.append(f"Redis connection failed: {exc}")

        css_path = settings.ROOT_DIR / "static" / "css" / "styles.css"
        if css_path.exists():
            self.stdout.write(self.style.SUCCESS("Tailwind CSS output: OK"))
        else:
            failures.append(f"Missing CSS build output: {css_path}")

        if failures:
            for failure in failures:
                self.stderr.write(self.style.ERROR(failure))
            raise CommandError("Stage 0 verification failed.")

        self.stdout.write(self.style.SUCCESS("Stage 0 verification passed."))

