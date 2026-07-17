"""Rebuild the three priority mathematics papers from the teachers' final files.

Papers:
* JS1 Mathematics (exam 1038)
* SS1 Mathematics (exam 1064)
* SS1 Further Mathematics (exam 1079)

Run:
    python manage.py shell < scripts/repair_priority_math_papers_20260703.py
"""

import re
from decimal import Decimal
from pathlib import Path

from django.core.files import File
from django.db import transaction

from apps.cbt.models import (
    CBTQuestionDifficulty,
    CBTQuestionType,
    CorrectAnswer,
    Exam,
    ExamQuestion,
    Option,
    Question,
)
from apps.cbt.workflow import _activation_snapshot_hash, _activation_snapshot_payload


ROOT = Path("/app")
SOURCE_DIR = ROOT / "assets" / "normalized-exam-sources"
IMAGE_DIR = ROOT / "assets" / "third-term-diagrams"

PAPERS = {
    1038: {
        "code": "JS1-MTH",
        "source": SOURCE_DIR / "js1-mathematics-final-20260703.txt",
        "objective_stop": "THEORY",
        "objective_count": 40,
        "instruction": "Answer any four (4) theory questions.",
    },
    1064: {
        "code": "SS1-MTH",
        "source": SOURCE_DIR / "ss1-mathematics-final-20260703.txt",
        "objective_stop": "SECTION B",
        "objective_count": 50,
        "instruction": "Answer Question 1 and any four (4) other theory questions.",
    },
    1079: {
        "code": "SS1-FTM",
        "source": SOURCE_DIR / "ss1-further-mathematics-final-20260703.txt",
        "objective_stop": "THEORY QUESTIONS",
        "objective_count": 51,
        "instruction": "Answer any four (4) theory questions.",
    },
}


OBJECTIVE_PATTERN = re.compile(
    r"(?ms)^\s*(\d+)\s*[\.\)]\s*(.*?)"
    r"\n\s*[Aa]\s*[\.\)]\s*(.*?)"
    r"\n\s*[Bb]\s*[\.\)]\s*(.*?)"
    r"\n\s*[Cc]\s*[\.\)]\s*(.*?)"
    r"\n\s*[Dd]\s*[\.\)]\s*(.*?)"
    r"\n\s*ANSWER\s*[:=]\s*([ABCD])\s*(?=\n|$)"
)


THEORY = {
    1038: [
        (
            "With the aid of a pencil, protractor and ruler, draw the following angles:\n"
            "i. 46°\n"
            "ii. 109°\n"
            "iii. 160°\n"
            "iv. 34°"
        ),
        (
            "With the aid of diagrams, define the following types of angles:\n"
            "i. Acute angle\n"
            "ii. Reflex angle\n"
            "iii. Right angle\n"
            "iv. Obtuse angle"
        ),
        (
            "Find the values of the lettered angles a, b, c, g and h in the "
            "diagram of two parallel lines cut by a transversal."
        ),
        (
            "Draw each of the following three-dimensional shapes and state two "
            "properties of each:\n"
            "i. Cuboid\n"
            "ii. Cone\n"
            "iii. Cylinder"
        ),
        "Find the value of x in the diagram. The angles around the point are x, 2x, 3x and 3x.",
        (
            "Each of fifteen people named a favourite colour. The results are:\n"
            "Colour: Blue | Red | Green | Yellow | Black\n"
            "Frequency: 3 | 4 | 1 | 5 | 2\n\n"
            "i. Which is the most popular colour?\n"
            "ii. How many responses are there altogether?\n"
            "iii. Use tally marks to represent the frequencies.\n"
            "iv. Add the frequencies for yellow and blue."
        ),
    ],
    1064: [
        (
            "Using a ruler and a pair of compasses only, construct:\n"
            "i. Triangle PQR such that |PQ| = 10 cm, |QR| = 7 cm and ∠PQR = 90°.\n"
            "ii. The locus l₁ of points equidistant from Q and R.\n"
            "iii. The locus l₂ of points equidistant from P and Q.\n"
            "b. Locate the point O equidistant from P, Q and R.\n"
            "c. With O as centre, draw the circumcircle of triangle PQR.\n"
            "d. Measure the radius of the circumcircle."
        ),
        (
            "Given that sin x = 5/13 and 0° ≤ x ≤ 90°, evaluate:\n"
            "(cos x − 2 sin x) / (2 tan x)."
        ),
        (
            "The table shows the distribution of test scores in a class:\n"
            "Scores: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9 | 10\n"
            "Number of pupils: 1 | 1 | 5 | 3 | k | 6 | 2 | 2 | 3 | 4\n\n"
            "a. If the mean score is 6, find:\n"
            "i. k\n"
            "ii. the median score.\n"
            "b. Draw a bar chart for the distribution."
        ),
        (
            "Copy and complete the table of values for y = x² − 2x − 1, "
            "for −2 ≤ x ≤ 4:\n"
            "x: −2 | −1 | 0 | 1 | 2 | 3 | 4\n"
            "y: [blank] | [blank] | [blank] | [blank] | [blank] | [blank] | [blank]\n\n"
            "a. Using scales of 2 cm to 1 unit on both axes, draw the graph.\n"
            "b. Find the minimum value of y.\n"
            "c. Use the graph to find the roots of x² − 2x − 1 = 0.\n"
            "d. On the same axes, draw y = 2x − 3.\n"
            "e. Determine the roots of x² − 2x − 1 = 2x − 3."
        ),
        (
            "In the diagram, PQRS and SRYZ are parallelograms and P, Q, Y and Z "
            "lie on a straight line. If |QY| = 4 cm and |RS| = 5 cm:\n"
            "a. Find |PZ|.\n"
            "b. Given that 23ₙ = 1111₂, find n."
        ),
        (
            "If A = {multiples of 2}, B = {multiples of 3} and C = {factors of 6} "
            "are subsets of ε = {x : 1 ≤ x ≤ 10}, find A′ ∩ B′ ∩ C′."
        ),
        (
            "Draw the graph of y = 2 sin x + 3 cos x for 0° ≤ x ≤ 300°.\n"
            "i. Find the maximum value of y.\n"
            "ii. Find the root(s) of the equation.\n"
            "iii. Find the value(s) of x when 2 sin x + 3 cos x = 2.5."
        ),
    ],
    1079: [
        (
            "a. Show graphically the region represented by:\n"
            "i. x − 2y + 1 ≤ 0\n"
            "ii. x + y > 5\n"
            "b. Find the range of x satisfying 3x − 2 < 10 + x < 2 + 5x."
        ),
        (
            "a. Define operations research and list the steps involved.\n"
            "b. Solve 7x + 4 ≤ ½(4x + 3)."
        ),
        (
            "a. Define a flowchart and state five applications of flowcharts.\n"
            "b. Solve 7(x + 4) − ⅔(x − 6) ≤ 2[x − 3(x + 5)]."
        ),
        (
            "The lengths (cm) of fifty planks are:\n"
            "33, 49, 81, 58, 59, 71, 42, 88, 68, 91\n"
            "54, 32, 50, 59, 41, 55, 38, 56, 86, 62\n"
            "50, 69, 23, 84, 77, 33, 71, 42, 69, 93\n"
            "61, 51, 46, 76, 63, 96, 26, 70, 66, 80\n"
            "44, 52, 60, 33, 68, 39, 61, 71, 48, 66\n\n"
            "a. Using class intervals 21–30, 31–40, 41–50, …, construct a frequency table.\n"
            "b. Identify the median class.\n"
            "c. Estimate the median.\n"
            "d. Calculate the mode."
        ),
        (
            "The scores of 40 students in a physics test are:\n"
            "Scores: 1 | 2 | 3 | 4 | 5 | 6 | 7 | 8 | 9\n"
            "Frequency: 2 | 3 | 6 | 7 | 9 | 6 | 2 | 2 | 3\n\n"
            "Calculate:\n"
            "a. the arithmetic mean;\n"
            "b. the standard deviation;\n"
            "c. the coefficient of variation."
        ),
        (
            "a. Define binary operation.\n"
            "b. State the laws of binary operation and explain them.\n"
            "c. What is a mathematical model?"
        ),
    ],
}


IMAGE_MAP = {
    (1038, "objective", 28): "js1-math-obj-q28.png",
    (1038, "objective", 31): "js1-math-obj-q31.png",
    (1038, "objective", 34): "js1-math-obj-q34.png",
    (1038, "theory", 3): "js1-math-theory-q43.png",
    (1038, "theory", 5): "js1-math-theory-q45-46.png",
    (1064, "objective", 38): "ss1-math-obj-q38-40.png",
    (1064, "objective", 41): "ss1-math-obj-q41.png",
    (1064, "objective", 42): "ss1-math-obj-q42.png",
    (1064, "objective", 43): "ss1-math-obj-q43-44.png",
    (1064, "theory", 1): "ss1-math-theory-q1-2.png",
    (1064, "theory", 3): "ss1-math-theory-q3.png",
    (1064, "theory", 4): "ss1-math-theory-q4.png",
    (1064, "theory", 5): "ss1-math-theory-q5.png",
    (1064, "theory", 6): "ss1-math-theory-q6-7.png",
    (1079, "objective", 4): "ss1-fmath-obj-q4-7.png",
}


SHARED_GROUPS = {
    1038: {
        "JS1-MTH-OBJ-28": [28],
        "JS1-MTH-OBJ-31": [31],
        "JS1-MTH-OBJ-34": [34],
        "JS1-MTH-THY-5-6": [5, 6],
    },
    1064: {
        "SS1-MTH-OBJ-38-40": [38, 39, 40],
        "SS1-MTH-OBJ-41": [41],
        "SS1-MTH-OBJ-42": [42],
        "SS1-MTH-OBJ-43-44": [43, 44],
        "SS1-MTH-THY-6-7": [6, 7],
    },
    1079: {
        "SS1-FTM-OBJ-4-7": [4, 5, 6, 7],
    },
}


def clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def parse_objectives(config):
    text = config["source"].read_text(encoding="utf-8-sig")
    objective_text = text.split(config["objective_stop"], 1)[0]
    rows = {}
    for match in OBJECTIVE_PATTERN.finditer(objective_text):
        number = int(match.group(1))
        rows[number] = {
            "stem": clean(match.group(2)),
            "options": {
                "A": clean(match.group(3)),
                "B": clean(match.group(4)),
                "C": clean(match.group(5)),
                "D": clean(match.group(6)),
            },
            "answer": match.group(7).upper(),
        }
    expected = list(range(1, config["objective_count"] + 1))
    if sorted(rows) != expected:
        missing = sorted(set(expected) - set(rows))
        raise RuntimeError(
            f"{config['code']} objective parse failed: found {len(rows)}, missing {missing}."
        )
    return rows


def apply_corrections(exam_id, rows):
    if exam_id == 1064:
        rows[1] = {
            "stem": "Without using tables, find sin 120°.",
            "options": {"A": "−√3/2", "B": "√3/2", "C": "1", "D": "1/2"},
            "answer": "B",
        }
        rows[5]["answer"] = "B"
        rows[6]["answer"] = "D"
        rows[9]["stem"] = "Find θ if sin θ = cos θ and 0° ≤ θ ≤ 90°."
        rows[10]["answer"] = "D"
        rows[11]["stem"] = "Solve sin 3θ = cos 2θ for an acute angle θ."
        rows[14]["options"] = {"A": "4%", "B": "5%", "C": "2%", "D": "10%"}
        rows[18]["options"] = {
            "A": "18,200",
            "B": "18,150",
            "C": "18,100",
            "D": "18,000",
        }
        for number, label in ((26, "sin x"), (27, "cos x"), (28, "sin x + cos x"), (29, "cos x − sin x")):
            rows[number]["stem"] = f"Given that tan x = 12/5 and x is acute, find {label}."
        rows[29]["options"]["B"] = "−7/13"
        rows[34]["stem"] = "Find x if 21ₓ = 7₁₀."
        rows[35]["stem"] = "If 23ₓ = 32₅, find x."
        rows[36]["stem"] = "Convert 111101₂ to base ten."
        rows[37]["stem"] = "Find x if 32₄ = 22ₓ."
        rows[38]["stem"] = "Use the diagram to find b."
        rows[39]["stem"] = "Use the diagram to find c."
        rows[40]["stem"] = "Use the diagram to find a."
        rows[47]["stem"] = "If cos 2θ = sin 19.35°, find θ to the nearest degree."
        rows[48] = {
            "stem": "Convert 1011₂ to base ten.",
            "options": {"A": "9", "B": "10", "C": "11", "D": "12"},
            "answer": "C",
        }
        rows[49]["stem"] = "Evaluate [64¹ᐟ² + 125¹ᐟ³]²."
        rows[50]["stem"] = "If 203₆ = p₁₀, find p."
    elif exam_id == 1038:
        rows[28]["stem"] = "In the right-angle diagram, one angle is 65°. Find y."
        rows[31]["stem"] = "In the straight-line diagram, one angle is 35°. Find y."
        rows[34]["stem"] = "In the triangle diagram, two angles are 74° and 52°. Find x."
    elif exam_id == 1079:
        rows[4]["stem"] = "Use the grouped-frequency table to find the lower class boundary of the modal class."
        rows[5]["stem"] = "Use the grouped-frequency table to find the midpoint of the median class."
        rows[6]["stem"] = "Use the grouped-frequency table to find the upper class boundary of the median class."
        rows[7]["stem"] = "Use the grouped-frequency table to find the midpoint of the modal class."
        rows[33]["answer"] = "A"
        rows[38]["stem"] = "Find the place value of the digit 5 in 107.485."
        rows[46]["stem"] = "If f(x) = x² − 4 for x ≥ 0, find f⁻¹(5)."
        rows[49]["options"]["C"] = "0.608"
    return rows


def shared_key(exam_id, section, number):
    for key, numbers in SHARED_GROUPS.get(exam_id, {}).items():
        if number in numbers and (
            ("OBJ" in key and section == "objective")
            or ("THY" in key and section == "theory")
        ):
            return key
    return ""


def attach_image(question, filename):
    path = IMAGE_DIR / filename
    if not path.exists():
        raise RuntimeError(f"Missing image asset: {path}")
    question.stimulus_caption = "Teacher-supplied examination diagram"
    with path.open("rb") as handle:
        question.stimulus_image.save(filename, File(handle), save=False)
    question.save()


def create_objective(exam, number, row):
    question = Question.objects.create(
        question_bank=exam.question_bank,
        created_by=exam.created_by,
        subject=exam.subject,
        question_type=CBTQuestionType.OBJECTIVE,
        stem=row["stem"],
        topic="Third Term Examination",
        difficulty=CBTQuestionDifficulty.MEDIUM,
        marks=Decimal("1.00"),
        source_type=Question.SourceType.DOCUMENT,
        source_reference=f"FINAL-20260703-{exam.id}-OBJ-{number:02d}",
        shared_stimulus_key=shared_key(exam.id, "objective", number),
        is_active=True,
    )
    option_rows = {}
    for order, label in enumerate("ABCD", start=1):
        option_rows[label] = Option.objects.create(
            question=question,
            label=label,
            option_text=row["options"][label],
            sort_order=order,
        )
    answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
    answer.correct_options.set([option_rows[row["answer"]]])
    answer.full_clean()
    filename = IMAGE_MAP.get((exam.id, "objective", number))
    if filename:
        attach_image(question, filename)
    return question


def create_theory(exam, number, text):
    question = Question.objects.create(
        question_bank=exam.question_bank,
        created_by=exam.created_by,
        subject=exam.subject,
        question_type=CBTQuestionType.SHORT_ANSWER,
        stem=text,
        topic="Theory: Third Term Examination",
        difficulty=CBTQuestionDifficulty.MEDIUM,
        marks=Decimal("10.00"),
        source_type=Question.SourceType.DOCUMENT,
        source_reference=f"FINAL-20260703-{exam.id}-THY-{number:02d}",
        shared_stimulus_key=shared_key(exam.id, "theory", number),
        is_active=True,
    )
    filename = IMAGE_MAP.get((exam.id, "theory", number))
    if filename:
        attach_image(question, filename)
    return question


def objective_mark_values(count):
    cents = 2000
    base, remainder = divmod(cents, count)
    return [
        Decimal(base + (1 if index < remainder else 0)) / Decimal("100")
        for index in range(count)
    ]


@transaction.atomic
def rebuild_exam(exam_id, config):
    exam = Exam.objects.select_for_update().get(pk=exam_id)
    exam = Exam.objects.select_related(
        "question_bank",
        "blueprint",
        "subject",
        "academic_class",
    ).get(pk=exam.id)
    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam_id} already has attempts and was not changed.")
    rows = apply_corrections(exam_id, parse_objectives(config))
    old_links = list(exam.exam_questions.values_list("question_id", flat=True))
    exam.exam_questions.all().delete()

    marks = objective_mark_values(config["objective_count"])
    sort_order = 1
    for number in range(1, config["objective_count"] + 1):
        question = create_objective(exam, number, rows[number])
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=marks[number - 1],
        )
        sort_order += 1

    for number, text in enumerate(THEORY[exam_id], start=1):
        question = create_theory(exam, number, text)
        ExamQuestion.objects.create(
            exam=exam,
            question=question,
            sort_order=sort_order,
            marks=Decimal("10.00"),
        )
        sort_order += 1

    blueprint = exam.blueprint
    section_config = dict(blueprint.section_config or {})
    section_config.update(
        {
            "flow_type": "OBJECTIVE_THEORY",
            "objective_count": config["objective_count"],
            "theory_count": len(THEORY[exam_id]),
            "question_count": config["objective_count"] + len(THEORY[exam_id]),
            "objective_target_max": "20.00",
            "theory_target_max": "30.00",
            "theory_response_mode": "PAPER",
            "manual_score_split": True,
            "calculator_mode": "BASIC",
            "review_seconds": 30,
            "theory_instructions": config["instruction"],
            "source_validation": "TEACHER_FINAL_REBUILT_AND_AUDITED_20260703",
            "seb_required": True,
            "seb_test_mode": False,
        }
    )
    blueprint.section_config = section_config
    blueprint.theory_enabled = True
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = (
        "Answer all objective questions. When the objective section is complete, "
        "open the theory section and follow the theory instruction displayed at the top."
    )
    blueprint.save(
        update_fields=[
            "section_config",
            "theory_enabled",
            "shuffle_questions",
            "shuffle_options",
            "instructions",
            "updated_at",
        ]
    )

    exam.activation_snapshot = _activation_snapshot_payload(exam)
    exam.activation_snapshot_hash = _activation_snapshot_hash(exam.activation_snapshot)
    exam.activation_comment = (
        f"{exam.activation_comment}\n"
        "Teacher final plain text and diagrams rebuilt and audited 03 Jul 2026."
    ).strip()
    exam.save(
        update_fields=[
            "activation_snapshot",
            "activation_snapshot_hash",
            "activation_comment",
            "updated_at",
        ]
    )
    Question.objects.filter(id__in=old_links, exam_links__isnull=True).delete()
    return exam


def audit(exam):
    links = list(
        exam.exam_questions.select_related("question", "question__correct_answer")
        .prefetch_related("question__options", "question__correct_answer__correct_options")
        .order_by("sort_order")
    )
    objective = [
        row for row in links if row.question.question_type == CBTQuestionType.OBJECTIVE
    ]
    theory = [
        row for row in links if row.question.question_type != CBTQuestionType.OBJECTIVE
    ]
    problems = []
    stems = set()
    for index, link in enumerate(objective, start=1):
        question = link.question
        options = list(question.options.all())
        normalized = [clean(option.option_text).casefold() for option in options]
        correct = list(question.correct_answer.correct_options.all())
        if len(options) != 4:
            problems.append(f"objective {index}: {len(options)} options")
        if len(set(normalized)) != 4:
            problems.append(f"objective {index}: duplicate option")
        if len(correct) != 1 or not question.correct_answer.is_finalized:
            problems.append(f"objective {index}: invalid answer key")
        if "??" in question.stem or any("??" in option.option_text for option in options):
            problems.append(f"objective {index}: placeholder")
        stem_key = clean(question.stem).casefold()
        if stem_key in stems:
            problems.append(f"objective {index}: repeated stem")
        stems.add(stem_key)
    expected_images = len(
        [
            key
            for key in IMAGE_MAP
            if key[0] == exam.id
        ]
    )
    actual_images = sum(bool(link.question.stimulus_image) for link in links)
    config = exam.blueprint.section_config
    if config.get("objective_count") != len(objective):
        problems.append("objective count/config mismatch")
    if config.get("theory_count") != len(theory):
        problems.append("theory count/config mismatch")
    if actual_images != expected_images:
        problems.append(f"image count {actual_images}/{expected_images}")
    if sum((link.marks for link in objective), Decimal("0.00")) != Decimal("20.00"):
        problems.append("objective marks do not total 20")
    if problems:
        raise RuntimeError(f"{exam.id} audit failed: {'; '.join(problems)}")
    return {
        "exam_id": exam.id,
        "class": exam.academic_class.code,
        "subject": exam.subject.code,
        "objective": len(objective),
        "theory": len(theory),
        "images": actual_images,
        "objective_marks": str(
            sum((link.marks for link in objective), Decimal("0.00"))
        ),
        "shuffle_questions": exam.blueprint.shuffle_questions,
        "shuffle_options": exam.blueprint.shuffle_options,
        "snapshot": exam.activation_snapshot_hash[:12],
        "status": "READY",
    }


results = []
for target_exam_id, target_config in PAPERS.items():
    results.append(audit(rebuild_exam(target_exam_id, target_config)))
for result in results:
    print(result)
