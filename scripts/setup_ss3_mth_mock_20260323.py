import base64
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicClass, AcademicSession, Subject, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)


TITLE = "MON 8:00-10:00 SS3 Mathematics Mock Examination"
DESCRIPTION = "MOCK EXAMINATION 2026/2027 CLASS: SS3 SUBJECT: MATHEMATICS"
BANK_NAME = "SS3 Mathematics Mock Examination 2026/2027"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer all questions in Part 1 and any five questions from Part 2. "
    "Timer is 90 minutes. Exam window closes at 10:00 AM WAT on Monday, March 23, 2026."
)

NAIRA = "\u20a6"

OBJECTIVES = [
    {"stem": "1. Express, correct to three significant figures, 0.003592", "options": {"A": "0.359", "B": "0.004", "C": "0.00360", "D": "0.00359"}, "answer": "D"},
    {"stem": "2. Evaluate (0.064)⁻¹⁄³", "options": {"A": "5⁄2", "B": "2⁄5", "C": "−2⁄5", "D": "−5⁄2"}, "answer": "A"},
    {"stem": "3. Solve (y + 1)⁄2 − (2y − 1)⁄3 = 4", "options": {"A": "y = 19", "B": "y = −19", "C": "y = −29", "D": "y = 29"}, "answer": "B"},
    {"stem": "4. Simplify, correct to three significant figures, (27.63)² − (12.37)²", "options": {"A": "614", "B": "612", "C": "611", "D": "610"}, "answer": "D"},
    {"stem": "5. If 7 + y ≡ 4 (mod 8), find the least value of y, 10 ≤ y ≤ 30", "options": {"A": "11", "B": "13", "C": "19", "D": "21"}, "answer": "B"},
    {"stem": "6. If T = {prime numbers} and M = {odd numbers} are subsets of \u03bc = {x: 0 < x < 10, and x is an integer}, find (T\u2032 \u2229 M\u2032)", "options": {"A": "{4, 6, 8}", "B": "{1, 4, 6, 8, 10}", "C": "{1, 2, 4, 6, 8, 10}", "D": "{1, 2, 3, 5, 7, 8, 9}"}, "answer": "A"},
    {"stem": "7. Evaluate: (log₃ 9 − log₂ 8)⁄log₃ 9", "options": {"A": "−1⁄3", "B": "1⁄2", "C": "1⁄3", "D": "−1⁄2"}, "answer": "D"},
    {"stem": "8. If 23y = 1111₂, find the value of y", "options": {"A": "4", "B": "5", "C": "6", "D": "7"}, "answer": "C"},
    {"stem": "9. If 6, p and 14 are consecutive terms in an Arithmetic Progression (A.P), find the value of p", "options": {"A": "9", "B": "10", "C": "6", "D": "8"}, "answer": "B"},
    {"stem": "10. Evaluate 2√28 − 3√50 + √72", "options": {"A": "4√7 − 21√2", "B": "4√7 − 11√2", "C": "4√7 − 9√2", "D": "4√7 − √2"}, "answer": "C"},
    {"stem": "11. If m : n = 2 : 1, evaluate ((3m)² − (2n)²)⁄(m² + mn)", "options": {"A": "4⁄3", "B": "5⁄3", "C": "3⁄4", "D": "3⁄5"}, "answer": "B"},
    {"stem": "12. H varies directly as p and inversely as the square of y. If H = 1, p = 8 and y = 2, find H in terms of p and y", "options": {"A": "H = p⁄(4y)²", "B": "H = 2p⁄y²", "C": "H = p⁄(2y)²", "D": "H = p⁄y²"}, "answer": "C"},
    {"stem": "13. Solve 4x² − 16x + 15 = 0", "options": {"A": "x = 11⁄2 or x = −21⁄2", "B": "x = 11⁄2 or x = 21⁄2", "C": "x = 11⁄2 or x = −11⁄2", "D": "x = −11⁄2 or x = −21⁄2"}, "answer": "B"},
    {"stem": "14. Evaluate (0.42 × 2.5)⁄(0.5 × 2.95), leaving the answer in standard form", "options": {"A": "1.639 × 10²", "B": "7.12 × 10¹", "C": "1.639 × 10⁻¹", "D": "1.639 × 10⁻²"}, "answer": "B"},
    {"stem": "15. Simplify log₁₀ 6 − 3log₁₀ 3 + 2⁄3 log₁₀ 27", "options": {"A": "3log₁₀ 2", "B": "log₁₀ 2", "C": "log₁₀ 3", "D": "2log₁₀ 3"}, "answer": "B"},
    {"stem": f"16. Bala sold an article for {NAIRA}6,900.00 and made a profit of 15%. Calculate his percentage profit if he had sold it for {NAIRA}6,600.00", "options": {"A": "5%", "B": "10%", "C": "12%", "D": "13%"}, "answer": "B"},
    {"stem": "17. If 3p = 4q and 9p = 8q − 12, find the value of pq", "options": {"A": "12", "B": "7", "C": "−7", "D": "−12"}, "answer": "A"},
    {"stem": "18. If (0.25)ʸ = 32, find the value of y", "options": {"A": "y = −5⁄2", "B": "y = −3⁄2", "C": "y = 3⁄2", "D": "y = 5⁄2"}, "answer": "A"},
    {"stem": "19. There are 8 boys and 4 girls in a lift. What is the probability that the first person who steps out of the lift will be a boy?", "options": {"A": "1⁄6", "B": "1⁄4", "C": "2⁄3", "D": "1⁄2"}, "answer": "C"},
    {"stem": "20. Simplify (x² − 5x − 14)⁄(x² − 9x + 14)", "options": {"A": "(x − 7)⁄(x + 7)", "B": "(x + 7)⁄(x − 7)", "C": "(x − 2)⁄(x + 4)", "D": "(x + 2)⁄(x − 2)"}, "answer": "D"},
    {"stem": "21. The total surface area of a solid is 165 cm³. If the base diameter is 7 cm, calculate its height. [Take π = 22⁄7]", "options": {"A": "7.5 cm", "B": "4.5 cm", "C": "4.0 cm", "D": "2.0 cm"}, "answer": "C"},
    {"stem": "22. If logₓ 2 = 0.3, evaluate logₓ 2", "options": {"A": "2.4", "B": "1.2", "C": "0.3", "D": "0.6"}, "answer": "C"},
    {"stem": "23. An arc subtends an angle of 72° at the centre of a circle. Find the length of the arc if the radius of the circle is 3.5 cm. [Take π = 22⁄7]", "options": {"A": "6.6 cm", "B": "8.8 cm", "C": "4.4 cm", "D": "2.2 cm"}, "answer": "C"},
    {"stem": "24. Make b the subject of the relation lb = 1⁄2 (a + b)h", "options": {"A": "b = ah⁄(2l − h)", "B": "b = (2l − h)⁄al", "C": "b = al⁄(2l − h)", "D": "b = al⁄(2 − h)"}, "answer": "A"},
    {"stem": "25. Eric sold his house through an agent who charged 8% commission on the selling price. If Eric received $117,760.00 after the sale, what was the selling price of the house?", "options": {"A": "$130,000.00", "B": "$128,000.00", "C": "$125,000.00", "D": "$120,000.00"}, "answer": "B"},
    {"stem": "26. Find the angle which an arc of length 22 cm subtends at the centre of a circle of radius 15 cm. [Take π = 22⁄7]", "options": {"A": "70°", "B": "84°", "C": "96°", "D": "156°"}, "answer": "B"},
    {"stem": "27. A rectangular board has length 15 cm and width x cm. If its sides are doubled, find its new area", "options": {"A": "60x cm²", "B": "45x cm²", "C": "30x cm²", "D": "15x cm²"}, "answer": "A"},
    {"stem": "28. Factorize completely (2x + 2y)(x − y) + (2x − 2y)(x + y)", "options": {"A": "4(x − y)(x + y)", "B": "4(x − y)", "C": "2(x − y)(x + y)", "D": "2(x − y)"}, "answer": "A"},
    {"stem": "29. The interior angles of a polygon are 3x°, 2x°, 4x°, 3x° and 6x°. Find the size of the smallest angle of the polygon", "options": {"A": "80°", "B": "60°", "C": "40°", "D": "30°"}, "answer": "B"},
    {"stem": "30. A box contains 2 white and 3 blue identical balls. If two balls are picked at random from the box, one after the other with replacement, what is the probability that they are of different colours?", "options": {"A": "2⁄3", "B": "3⁄5", "C": "7⁄20", "D": "12⁄25"}, "answer": "D"},
    {"stem": "31. Find the equation of a straight line passing through the point (1, −5) and having a gradient of 3⁄4", "options": {"A": "3x + 4y − 23 = 0", "B": "3x + 4y + 23 = 0", "C": "3x − 4y + 23 = 0", "D": "3x − 4y − 23 = 0"}, "answer": "D"},
    {"stem": "32. The foot of a ladder is 6 m from the base of an electric pole. The top of the ladder rests against the pole at a point 8 m above the ground. How long is the ladder?", "options": {"A": "14 m", "B": "12 m", "C": "10 m", "D": "7 m"}, "answer": "C"},
    {"stem": "33. If tan x = 3⁄4, 0 < x < 90°, evaluate cos x⁄(2 sin x)", "options": {"A": "8⁄3", "B": "3⁄2", "C": "4⁄3", "D": "2⁄3"}, "answer": "D"},
    {"stem": "34. The fourth term of an Arithmetic Progression (A.P) is 37 and the first term is −20. Find the common difference", "options": {"A": "63", "B": "57", "C": "19", "D": "17"}, "answer": "C"},
    {"stem": "35. A box contains 5 red, 6 green and 7 yellow pencils of the same size. What is the probability of picking a green pencil at random?", "options": {"A": "1⁄6", "B": "1⁄4", "C": "1⁄3", "D": "1⁄2"}, "answer": "C"},
    {"stem": "36. Find x if 81ˣ = 243⁵", "options": {"A": "5", "B": "9", "C": "8", "D": "7"}, "answer": "B"},
    {"stem": "37. Convert 0.00248 to standard form", "options": {"A": "2.48 × 10⁻¹", "B": "2.48 × 10⁻²", "C": "2.48 × 10⁻³", "D": "2.48 × 10⁻⁴"}, "answer": "C"},
    {"stem": "38. Convert 2345 to standard form", "options": {"A": "2.345 × 10¹", "B": "2.345 × 10²", "C": "2.345 × 10³", "D": "2.345 × 10⁴"}, "answer": "C"},
    {"stem": "39. Round off 365049 to the nearest 1000", "options": {"A": "364000", "B": "365000", "C": "3650000", "D": "375000"}, "answer": "B"},
    {"stem": "40. Round off 54.7283 to 2 decimal places", "options": {"A": "54.73", "B": "54.74", "C": "53.84", "D": "52.84"}, "answer": "A"},
    {"stem": "41. Round off 46.057 to 3 significant figures", "options": {"A": "46.3", "B": "46.1", "C": "46.8", "D": "50.1"}, "answer": "B"},
    {"stem": "42. A peg of length 1.75 m was measured as 1.80 m. Find the percentage error of measurement", "options": {"A": "2.8%", "B": "2.7%", "C": "2.84%", "D": "2.86%"}, "answer": "D"},
    {"stem": "43. Simplify (b² + 3b)⁄(b² + 10b + 21)", "options": {"A": "1⁄(b + 7)", "B": "b⁄(b + 7)", "C": "(b + 1)⁄(b + 7)", "D": "(b + 2)⁄(b + 5)"}, "answer": "B"},
    {"stem": "44. Calculate the angle at the centre of a circle, subtended by a chord 6 cm from the centre of the circle with radius 10 cm", "options": {"A": "106.30", "B": "107.20", "C": "107.40", "D": "108.50"}, "answer": "A"},
    {"stem": "45. A chord 12 cm long subtends an angle of 40° at the centre of the circle. Calculate the radius of the circle", "options": {"A": "17.5 cm", "B": "17.8 cm", "C": "17.54 cm", "D": "17.4 cm"}, "answer": "C"},
    {"stem": "46. Find the length of a chord which subtends an angle of 58° at the centre of a circle with radius 16 cm", "options": {"A": "13.2 cm", "B": "15.51 cm", "C": "13.4 cm", "D": "13.5 cm"}, "answer": "B"},
    {"stem": "47. The sum of squares of two consecutive even numbers is 52. Find the numbers", "options": {"A": "x = 4 or x = 6", "B": "x = −4 or x = −6", "C": "x = 4 or x = −6", "D": "x = −4 or x = 6"}, "answer": "C"},
    {"stem": "48. Find the 50th term of A.P. 3, 7, 11, …..", "options": {"A": "200", "B": "199", "C": "240", "D": "800"}, "answer": "B"},
    {"stem": "49. Find the 6th term of A.P. −2, −4, −6, ……", "options": {"A": "12", "B": "−12", "C": "13", "D": "−13"}, "answer": "B"},
    {"stem": "50. Solve x⁄3 + 5 = 2x", "options": {"A": "4", "B": "5", "C": "6", "D": "3"}, "answer": "D"},
]

THEORY = [
    {"stem": "1. (a) Given that 110ₓ = 40₅, find the value of x\n   (b) Simplify 15⁄√75 + √108 + √432 in the form a√b, where a and b are positive integers", "marks": Decimal("10.00")},
    {"stem": "2. (a) Find the equation of the line which passes through the points A(−2, 7) and B(2, −3)\n   (b) Given that (5b − a)⁄(8b + 3a) = 1⁄5, find, correct to two decimal places, the value of a⁄b", "marks": Decimal("10.00")},
    {"stem": f"3. (a) Ali, Misha and Yusif shared {NAIRA}42,000.00 in the ratio 3 : 5 : 8 respectively. Find the sum of Ali and Yusif’s shares\n   (b) Solve: 2((1⁄3)ˣ) = 32ˣ⁻¹", "marks": Decimal("10.00")},
    {"stem": "4. In the diagram, PQRS is a quadrilateral, ∠PQR = ∠PRS = 90°, |PQ| = 3 cm, |QR| = 4 cm and |PS| = 13 cm. Find the area of the quadrilateral", "marks": Decimal("10.00"), "image": "4 theory ss3 maths.png", "caption": "Quadrilateral diagram for theory question 4"},
    {"stem": "5. Three red balls, five green balls and a number of blue balls are put together in a sack. One ball is picked at random from the sack. If the probability of picking a red ball is 1⁄6, find:\n   (a) the number of blue balls in the sack\n   (b) the probability of picking a green ball", "marks": Decimal("10.00")},
    {"stem": "6. (a) Copy and complete the table of values for y = 2 cos x + 3 sin x, for 0° ≤ x ≤ 360°\n   (b) Using a scale of 2 cm to 60° on the x-axis and 2 cm to 1 unit on the y-axis, draw the graph of y = 2 cos x + 3 sin x for 0° ≤ x ≤ 360°\n   (c) Using the graph:\n       (i) Solve 2 cos x + 3 sin x = −1\n       (ii) Find, correct to one decimal place, the value of y when x = 342°", "marks": Decimal("10.00"), "image": "no 6 theory ss3 maths.png", "caption": "Value table for theory question 6(a)"},
    {"stem": "7. (a) The third and sixth terms of a Geometric Progression (G.P.) are 1⁄4 and 1⁄32 respectively. Find:\n       (i) the first term and the common ratio\n       (ii) the seventh term\n   (b) Given that 2 and −3 are the roots of the equation ax² + bx + c = 0, find the values of a, b and c", "marks": Decimal("10.00")},
    {"stem": "8. The table shows the distribution of marks obtained by students in an examination\n   (a) Construct a cumulative frequency table for the distribution\n   (b) Draw the cumulative frequency curve for the distribution\n   (c) Using the curve, find, correct to one decimal place:\n       (i) the median mark\n       (ii) the lowest mark for the distribution if 5% of the students pass with distinction", "marks": Decimal("10.00"), "image": "no 8 theory maths ss3.png", "caption": "Distribution table for theory question 8"},
    {"stem": "9. (a) Without using mathematical table or calculator, evaluate √((0.18 × 12.5)⁄(0.05 × 0.2))\n   (b) Simplify (8 − 4√18)⁄√50, leaving your answer in the form a + b√n where a and b are rational numbers and n is an integer\n   (c) x, y and z are related such that x varies directly as the cube root of y and inversely as the square of z. If x = 108 when y = 3 and z = 4, find z when x = 4000 and y = 10", "marks": Decimal("10.00")},
    {"stem": "10. Two towns K and Q are on the parallel of latitude 46°N. The longitude of town K is 130°W and that of town Q is 103°. A third town P, also on latitude 46°N, is on longitude 32°E. Calculate:\n    (i) the length of the parallel of latitude 46°N, to the nearest 100 km\n    (ii) the distance between K and Q, correct to the nearest 100 km\n    (iii) the distance between Q and P measured along the parallel of latitude, to the nearest 10 m\n    [Take π = 3.142, radius of the earth = 6400 km]", "marks": Decimal("10.00")},
    {"stem": "11. (a) Copy and complete the table of values for the relation y = 3x² − 5x − 7\n   (b) Using scales of 2 cm to 1 unit on the x-axis and 2 cm to 5 units on the y-axis, draw the graph of y = 3x² − 5x − 7 for −3 ≤ x ≤ 4\n   (c) From your graph:\n       (i) find the roots of the equation\n       (ii) estimate the minimum value of y\n       (iii) calculate the gradient of the curve at the point x = 2", "marks": Decimal("10.00"), "image": "no 11 theory maths ss3.png", "caption": "Value table for theory question 11(a)"},
    {"stem": "12. Using a ruler and a pair of compasses only:\n    (a) Construct:\n        (i) a △ABC such that |AB| = 5 cm, |AC| = 7.5 cm, and ∠CAB = 120°\n        (ii) the locus l₁ of points equidistant from A and B\n        (iii) the locus l₂ of points equidistant from |AB| and AC, which passes through triangle ABC\n    (b) Label the point P where l₁ and l₂ intersect\n    (c) Measure |CP|", "marks": Decimal("10.00")},
    {"stem": "13. In a class of 40 students, 25 speak Hausa, 16 speak Igbo, 21 speak Yoruba and each of the students speaks at least one of these three languages. If 8 speak Hausa and Igbo, 11 speak Hausa and Yoruba and 6 speak Igbo and Yoruba:\n    (a) Draw a Venn diagram to illustrate this information, using x to represent the number of students that speak all three\n    (b) Calculate the value of x", "marks": Decimal("10.00")},
    {"stem": "14. (a) The distribution of junior workers in an institution is as follows:\n        Clerks      78\n        Drivers     36\n        Typists     44\n        Messengers  52\n        Others      30\n\n        Represent the above information by a pie chart\n\n    (b) The table below shows the frequency distribution of marks scored by 30 candidates in an aptitude test\n\n        Marks              4   5   6   7   8   9\n        No. of students    5   8   5   6   4   2\n\n        Find the mean score to the nearest whole number", "marks": Decimal("10.00"), "image": "14b theory maths ss3.png", "caption": "Aptitude test table for theory question 14(b)"},
    {"stem": "15. (a) Given that 13x + 22y = 1610 and 32x + 12y = 2210, find the values of x and y\n    (b) Evaluate ∫ (x + 2)⁄(x² − 5x + 4) dx", "marks": Decimal("10.00")},
]


def _exam_assets_root():
    return Path.cwd() / "EXAM"


def _image_data_uri(image_name):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _rich_stem_with_image(stem, *, image_name, caption=""):
    body = "<br>".join(stem.splitlines())
    image_url = _image_data_uri(image_name)
    caption_html = (
        f"<figcaption style=\"margin-top:8px;font-size:0.9rem;color:#475569;\">{caption}</figcaption>"
        if caption
        else ""
    )
    return (
        f"<div>{body}</div>"
        f"<figure class=\"cbt-inline-figure\" style=\"margin-top:12px;\">"
        f"<img src=\"{image_url}\" alt=\"Question diagram\" "
        f"style=\"max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:12px;padding:8px;background:#fff;\">"
        f"{caption_html}"
        f"</figure>"
    )


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="MTH")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="emmanuel@ndgakuje.org",
        academic_class=academic_class,
        subject=subject,
        session=session,
        term=term,
        is_active=True,
    )
    teacher = assignment.teacher
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 23, 8, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 23, 10, 0, tzinfo=lagos)

    bank, _ = QuestionBank.objects.get_or_create(
        owner=teacher,
        name=BANK_NAME,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={"description": DESCRIPTION, "assignment": assignment, "is_active": True},
    )
    bank.description = DESCRIPTION
    bank.assignment = assignment
    bank.is_active = True
    bank.save()

    exam, created = Exam.objects.get_or_create(
        title=TITLE,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={
            "description": DESCRIPTION,
            "exam_type": CBTExamType.EXAM,
            "status": CBTExamStatus.ACTIVE,
            "created_by": teacher,
            "assignment": assignment,
            "question_bank": bank,
            "dean_reviewed_by": dean_user,
            "dean_reviewed_at": timezone.now(),
            "dean_review_comment": "Approved for Monday morning mock paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Monday, March 23, 2026 8:00 AM WAT.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts. Refusing to overwrite live content.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for Monday morning mock paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Monday, March 23, 2026 8:00 AM WAT."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    ExamQuestion.objects.filter(exam=exam).delete()
    bank.questions.all().delete()

    sort_order = 1
    for index, item in enumerate(OBJECTIVES, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            marks=Decimal("1.00"),
            source_reference=f"SS3-MTH-MOCK-20260323-OBJ-{index:02d}",
            is_active=True,
        )
        option_map = {}
        for option_index, label in enumerate(("A", "B", "C", "D"), start=1):
            option_map[label] = Option.objects.create(
                question=question,
                label=label,
                option_text=item["options"][label],
                sort_order=option_index,
            )
        answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.add(option_map[item["answer"]])
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=Decimal("1.00"))
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        rich_stem = ""
        if item.get("image"):
            rich_stem = _rich_stem_with_image(item["stem"], image_name=item["image"], caption=item.get("caption", ""))
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=item["marks"],
            source_reference=f"SS3-MTH-MOCK-20260323-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 90
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-MTH-MOCK-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "40.00",
        "theory_target_max": "60.00",
    }
    blueprint.passing_score = Decimal("0.00")
    blueprint.objective_writeback_target = CBTWritebackTarget.OBJECTIVE
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.THEORY
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()

    print(
        {
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "status": exam.status,
            "schedule_start": exam.schedule_start.isoformat() if exam.schedule_start else "",
            "schedule_end": exam.schedule_end.isoformat() if exam.schedule_end else "",
            "duration_minutes": blueprint.duration_minutes,
            "objective_questions": len(OBJECTIVES),
            "theory_questions": len(THEORY),
            "rich_stem_theory_rows": [index for index, item in enumerate(THEORY, start=1) if item.get("image")],
            "shuffle_questions": blueprint.shuffle_questions,
            "shuffle_options": blueprint.shuffle_options,
        }
    )


main()
