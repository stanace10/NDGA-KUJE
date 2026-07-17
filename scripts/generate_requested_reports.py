import os
import sys
from pathlib import Path

import django


APP_ROOT = Path(__file__).resolve().parents[1]
if str(APP_ROOT) not in sys.path:
    sys.path.insert(0, str(APP_ROOT))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "core.settings")
django.setup()

from django.contrib.auth import get_user_model
from django.test import RequestFactory

from apps.academics.models import AcademicClass, AcademicSession, Term
from apps.results.views import CA1ClassReportPDFView, CA1ClassSubjectLeadersPDFView


base = Path("/app/SCHOOL FOLDER/report")
base.mkdir(parents=True, exist_ok=True)

rf = RequestFactory()
User = get_user_model()
user = User.objects.filter(is_superuser=True).first() or User.objects.filter(is_staff=True).first() or User.objects.first()

session = AcademicSession.objects.get(name="2025/2026")
third = Term.objects.get(session=session, name="THIRD")
classes = list(AcademicClass.objects.filter(code__in=["JS1", "JS2", "SS1", "SS2"]).order_by("code"))

exports = [
    ("academic-cumulative.pdf", CA1ClassReportPDFView, "cumulative"),
    ("highest-in-each-subject-cumulative.pdf", CA1ClassSubjectLeadersPDFView, "cumulative"),
    ("third-term-overall.pdf", CA1ClassReportPDFView, "overall"),
]

written = []
for cls in classes:
    folder = base / cls.code.lower()
    folder.mkdir(parents=True, exist_ok=True)
    for filename, view_cls, ca in exports:
        request = rf.get(
            f"/results/report/academic-performance/class/{cls.id}/export.pdf",
            {"session_id": str(session.id), "term_id": str(third.id), "ca": ca},
            HTTP_HOST="192.168.10.10",
            secure=True,
        )
        request.user = user
        view = view_cls()
        view.setup(request, class_id=cls.id)
        response = view.get(request, class_id=cls.id)
        if response.status_code != 200:
            raise RuntimeError(f"{cls.code} {filename} failed with {response.status_code}")
        out = folder / filename
        out.write_bytes(response.content)
        written.append(str(out))

print("\n".join(written))
