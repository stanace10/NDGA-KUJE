from __future__ import annotations

from decimal import Decimal

from apps.academics.models import AcademicClass
from apps.finance.models import ChargeTargetType, StudentCharge


PIXPAY_SCHOOL_FEES_URL = "https://portal.pixpay.ng/ProspectiveFees"


def _money(value: str) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"))


PROSPECTUS_FEE_SCHEDULES = {
    "JUNIOR_NEW": {
        "label": "JSS 1-2 New Students",
        "grand_total": _money("726000"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "72000"),
            ("Registration", "30000"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship fee", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Bedding fees", "10000"),
            ("Classroom furniture", "5000"),
            ("Celebrations", "2000"),
            ("Uniform/other wear", "154000"),
            ("Christmas carol", "10000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
    "JUNIOR_RETURNING": {
        "label": "JSS 1-2 Returning Students",
        "grand_total": _money("525000"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "70000"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship fee", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Celebrations", "2000"),
            ("Christmas carol", "10000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
    "SENIOR_NEW": {
        "label": "SS1-2 New Students",
        "grand_total": _money("756000"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "72000"),
            ("Registration", "30000"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship fee", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Bedding fees", "10000"),
            ("Classroom furniture", "5000"),
            ("Celebrations", "2000"),
            ("Uniform/other wear", "154000"),
            ("Christmas carol", "10000"),
            ("SAT", "30000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
    "SENIOR_RETURNING": {
        "label": "SS1-2 Returning Students",
        "grand_total": _money("525000"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "40000"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship fee", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Celebrations", "2000"),
            ("Christmas carol", "10000"),
            ("SAT", "30000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
    "JUNIOR_EXTERNAL": {
        "label": "JSS3 Returning Students",
        "grand_total": _money("533500"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "48500"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Celebrations", "2000"),
            ("Christmas carol", "10000"),
            ("Practice Test", "30000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
    "SENIOR_EXTERNAL": {
        "label": "SS3 Returning Students",
        "grand_total": _money("564000"),
        "rows": [
            ("Tuition", "120000"),
            ("Boarding", "200000"),
            ("Text/exercise books", "39000"),
            ("ICT/Computer fees", "10000"),
            ("Examination fees", "5000"),
            ("First Aid (Medical fees)", "5000"),
            ("Maintenance fee", "5000"),
            ("Security levy", "10000"),
            ("Internet subscription", "3000"),
            ("Electricity levy", "3000"),
            ("Religious Service", "3000"),
            ("Entrepreneurship fee", "3000"),
            ("Library fees", "3000"),
            ("Music", "3000"),
            ("Games/Sports fees", "3000"),
            ("Sanitation levy", "2000"),
            ("Celebrations", "2000"),
            ("Christmas carol", "10000"),
            ("SAT", "30000"),
            ("Practice Test", "40000"),
            ("Students' pocket money/Tuck shop", "25000"),
            ("Chinese language", "15000"),
            ("PTA levy", "25000"),
        ],
    },
}


def normalized_class_code(value: str) -> str:
    code = "".join(ch for ch in (value or "").upper() if ch.isalnum())
    if code.startswith("JSS"):
        code = "JS" + code[3:]
    return code


def schedule_key_for_class_code(class_code: str, *, new_intake: bool = False) -> str:
    code = normalized_class_code(class_code)
    if code in {"JS1", "JS2"}:
        return "JUNIOR_NEW" if new_intake else "JUNIOR_RETURNING"
    if code == "JS3":
        return "JUNIOR_EXTERNAL"
    if code in {"SS1", "SS2"}:
        return "SENIOR_NEW" if new_intake else "SENIOR_RETURNING"
    if code == "SS3":
        return "SENIOR_EXTERNAL"
    return "SENIOR_RETURNING" if code.startswith("SS") else "JUNIOR_RETURNING"


def prospectus_for_class(class_code: str, *, new_intake: bool = False) -> dict:
    key = schedule_key_for_class_code(class_code, new_intake=new_intake)
    schedule = PROSPECTUS_FEE_SCHEDULES[key]
    rows = [
        {"title": title, "amount": _money(amount), "code": title.lower().replace("/", "-").replace(" ", "-")}
        for title, amount in schedule["rows"]
    ]
    return {
        "key": key,
        "label": schedule["label"],
        "rows": rows,
        "grand_total": schedule["grand_total"],
        "pixpay_url": PIXPAY_SCHOOL_FEES_URL,
    }


def core_student_fee_rows() -> list[dict]:
    titles = {}
    for schedule in PROSPECTUS_FEE_SCHEDULES.values():
        for title, amount in schedule["rows"]:
            titles.setdefault(
                title,
                {
                    "title": title,
                    "code": title.lower().replace("/", "-").replace(" ", "-"),
                    "summary": "Standard fee item from the 2026/2027 NDGA prospectus.",
                    "configured_amount": None,
                    "sample_amount": _money(amount),
                },
            )
    return list(titles.values())


def ensure_prospectus_charges(*, session, term, actor=None) -> dict:
    if session is None:
        return {"created": 0, "updated": 0, "classes": 0}
    created = 0
    updated = 0
    classes = 0
    rows = AcademicClass.objects.filter(is_active=True, base_class__isnull=True).order_by("code")
    for academic_class in rows:
        classes += 1
        prospectus = prospectus_for_class(academic_class.code, new_intake=False)
        for fee in prospectus["rows"]:
            description = f"{prospectus['label']} fee item from the official 2026/2027 prospectus."
            charge, was_created = StudentCharge.objects.get_or_create(
                session=session,
                term=term,
                target_type=ChargeTargetType.CLASS,
                academic_class=academic_class,
                item_name=fee["title"],
                defaults={
                    "description": description,
                    "amount": fee["amount"],
                    "student": None,
                    "due_date": None,
                    "created_by": actor,
                    "is_active": True,
                },
            )
            if was_created:
                created += 1
                continue
            changed_fields = []
            if charge.amount != fee["amount"]:
                charge.amount = fee["amount"]
                changed_fields.append("amount")
            if charge.description != description:
                charge.description = description
                changed_fields.append("description")
            if not charge.is_active:
                charge.is_active = True
                changed_fields.append("is_active")
            if changed_fields:
                changed_fields.append("updated_at")
                charge.save(update_fields=changed_fields)
                updated += 1
    return {"created": created, "updated": updated, "classes": classes}
