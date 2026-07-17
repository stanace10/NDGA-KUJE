from __future__ import annotations

import base64
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

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


TITLE = "TUE 11:00-12:10 JS3 CCA Second Term Exam"
DESCRIPTION = "JSS3 CULTURAL AND CREATIVE ARTS SECOND TERM EXAMINATION"
BANK_NAME = "JS3 CCA Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Choose the correct option in Section A. In Section B, answer any four questions. "
    "Objective carries 20 marks after normalization. Theory carries 40 marks after marking. "
    "Timer is 60 minutes. Exam window closes at 12:10 PM WAT on Tuesday, March 24, 2026."
)
IMAGE_PATHS = {
    "no 1 objective cca js3.jpg": Path("/tmp/no_1_objective_cca_js3.jpg"),
    "no 2 cca objective js3.jpg": Path("/tmp/no_2_cca_objective_js3.jpg"),
    "no 59 and no 60 js3 cca objective.jpg": Path("/tmp/no_59_and_no_60_js3_cca_objective.jpg"),
}

OBJECTIVES = [
    {"stem": "The figure above represents ______.", "options": {"A": "Igbo ukwu", "B": "Nok bronze", "C": "Nok terracotta", "D": "Ife head"}, "answer": "C", "image": "no 1 objective cca js3.jpg", "caption": "Figure A"},
    {"stem": "The figure above is a representation of ______.", "options": {"A": "Benin bronze head", "B": "Ife bronze mask", "C": "Ife terracotta", "D": "Benin ivory mask"}, "answer": "D", "image": "no 2 cca objective js3.jpg", "caption": "Figure B"},
    {"stem": "Another name for terracotta is ______.", "options": {"A": "fired clay", "B": "burnt clay", "C": "sculptural clay", "D": "fried clay"}, "answer": "A"},
    {"stem": "The oldest museum in Nigeria is that of ______.", "options": {"A": "Kaduna museum", "B": "Lagos museum", "C": "Esie museum", "D": "Jos museum"}, "answer": "C"},
    {"stem": "Who among these artists was a print maker?", "options": {"A": "Akinola Lasekan", "B": "Bruce Onabrakpeye", "C": "Lamidi Fakeye", "D": "Demas Nwoko"}, "answer": "B"},
    {"stem": "Good spacing is essential in lettering for ______.", "options": {"A": "Economy of paper", "B": "Judicious use of paper", "C": "Decoration", "D": "Legibility"}, "answer": "D"},
    {"stem": "Another word for calligraphy is ______.", "options": {"A": "type face", "B": "handwriting", "C": "hieroglyphics", "D": "pen lettering"}, "answer": "D"},
    {"stem": "The first Nigerian trained artist to teach art was ______.", "options": {"A": "Late Chief Akinola Lasekan", "B": "Late Chief Aina Onabolu", "C": "Prof. Ben Enwonwu", "D": "Prof. Latunde Lawal"}, "answer": "B"},
    {"stem": "Upper case in lettering is also known as ______.", "options": {"A": "capital letter", "B": "medium letter", "C": "small letter", "D": "types of letter"}, "answer": "A"},
    {"stem": "Chiaroscuro is the Italian word for ______.", "options": {"A": "painting", "B": "perspective", "C": "tinted light", "D": "light and shade"}, "answer": "D"},
    {"stem": "______ is the activity that involves special skills.", "options": {"A": "carving", "B": "craft", "C": "design", "D": "drawing"}, "answer": "B"},
    {"stem": "A large hall where art works especially painting are displayed and sold to the public is called ______.", "options": {"A": "studio", "B": "gallery", "C": "museum", "D": "market"}, "answer": "B"},
    {"stem": "The outline or shape of an object painted with one colour without details or features is called ______.", "options": {"A": "caption", "B": "drawing", "C": "chiaroscuro", "D": "silhouette"}, "answer": "D"},
    {"stem": "Which of the following is a way of showcasing artworks?", "options": {"A": "selling", "B": "auction", "C": "hawking", "D": "exhibition"}, "answer": "D"},
    {"stem": "Embroidery is a form of ______ decoration.", "options": {"A": "wall", "B": "fabric", "C": "house", "D": "wall paper"}, "answer": "B"},
    {"stem": "Non-repeat design is also called ______.", "options": {"A": "accidental", "B": "leaf print", "C": "yam print", "D": "pattern"}, "answer": "A"},
    {"stem": "The fine lines that adorned most Ife heads are called ______.", "options": {"A": "vertical lines", "B": "tattoos", "C": "scarifications", "D": "incision"}, "answer": "C"},
    {"stem": "The two major classes of clay are ______.", "options": {"A": "hard and soft clay", "B": "wet and dry clay", "C": "primary and residential clay", "D": "primary and secondary clay"}, "answer": "D"},
    {"stem": "Which of these artists is a renowned potter?", "options": {"A": "Bruce Onabrakpeya", "B": "Funke Ifeta", "C": "David Dele", "D": "Ladi Kwali"}, "answer": "D"},
    {"stem": "Shading by which an artist indicates dots on a drawn object is referred to as ______.", "options": {"A": "blurring", "B": "cross hatching", "C": "pointillism", "D": "hatch"}, "answer": "C"},
    {"stem": "Each artwork in an exhibition is called ______.", "options": {"A": "an exhibit", "B": "a show", "C": "a display", "D": "an item"}, "answer": "A"},
    {"stem": "In art, the expression 'Art in the round' means art work that ______.", "options": {"A": "are round", "B": "can be sold", "C": "are circular", "D": "can be viewed from all sides"}, "answer": "D"},
    {"stem": "The basic material for pottery is ______.", "options": {"A": "mud", "B": "clay", "C": "wax", "D": "paper"}, "answer": "B"},
    {"stem": "All parallel lines in a perspective drawing meet at a point called ______.", "options": {"A": "line of vision", "B": "vanishing point", "C": "sky limit", "D": "boundary point"}, "answer": "B"},
    {"stem": "The purest form of clay is ______.", "options": {"A": "ball clay", "B": "grey clay", "C": "kaolin", "D": "Indian clay"}, "answer": "C"},
    {"stem": "A painting done in many shades of a single colour is called ______.", "options": {"A": "fresco", "B": "polychrome", "C": "monochrome", "D": "impasto"}, "answer": "C"},
    {"stem": "Which acronym is used to represent the colours of the rainbow?", "options": {"A": "ROGBIVY", "B": "GBIVROY", "C": "GBIVORY", "D": "ROYGBIV"}, "answer": "D"},
    {"stem": "Esie figure is mainly executed in ______.", "options": {"A": "clay", "B": "metal", "C": "plaster of Paris", "D": "soap stone"}, "answer": "D"},
    {"stem": "The qualities of good lettering are ______.", "options": {"A": "small, legibility, spacing", "B": "simplicity, legibility, spacing", "C": "bold, legibility, spacing", "D": "scattered, legibility, spacing"}, "answer": "B"},
    {"stem": "The process of mixing and removing some particles from clay is called ______.", "options": {"A": "picking", "B": "casting", "C": "plastering", "D": "kneading"}, "answer": "D"},
    {"stem": "Johannes Gutenberg was the first person to invent ______ machine.", "options": {"A": "sewing", "B": "ATM", "C": "printing", "D": "photocopy"}, "answer": "C"},
    {"stem": "A painting that involves thick application of colour or paint is ______.", "options": {"A": "fresco", "B": "impasto", "C": "etching", "D": "tempera"}, "answer": "B"},
    {"stem": "What is another word for art materials?", "options": {"A": "newsprints", "B": "media", "C": "form", "D": "radio and newspaper"}, "answer": "B"},
    {"stem": "An officer that oversees artifacts kept in a museum is known as a ______.", "options": {"A": "ceramist", "B": "curator", "C": "painter", "D": "rector"}, "answer": "B"},
    {"stem": "Pinching technique is associated with ______.", "options": {"A": "blacksmithing", "B": "calabash decoration", "C": "leather product", "D": "pottery"}, "answer": "D"},
    {"stem": "Primary colours consist of ______, ______ and ______.", "options": {"A": "red, green, blue", "B": "red, blue, yellow", "C": "white, black, blue", "D": "violet, orange, purple"}, "answer": "B"},
    {"stem": "Balance, variety and proportion are some examples of ______.", "options": {"A": "graphic design", "B": "elements design", "C": "textile design", "D": "principles of design"}, "answer": "D"},
    {"stem": "Another name for abstract is ______.", "options": {"A": "regular shapes", "B": "irregular shapes", "C": "geometric shapes", "D": "non-representational art"}, "answer": "D"},
    {"stem": "The place where pots are fired is called ______.", "options": {"A": "an oven", "B": "a stove", "C": "fire house", "D": "a kiln"}, "answer": "D"},
    {"stem": "______ is associated with rope pot and snail shell artworks.", "options": {"A": "Ife", "B": "Nok", "C": "Esie", "D": "Igbo ukwu"}, "answer": "B"},
    {"stem": "Additive method is to modeling as ______ method is to carving.", "options": {"A": "cutting", "B": "subtractive", "C": "addition", "D": "moulding"}, "answer": "B"},
    {"stem": "A design done on fabric with wax and dye is called ______.", "options": {"A": "Mosaic", "B": "batik", "C": "tie dyeing", "D": "designing"}, "answer": "B"},
    {"stem": "Traditional skill in craft is acquired through ______.", "options": {"A": "apprenticeship", "B": "examination", "C": "lectures", "D": "seminars"}, "answer": "A"},
    {"stem": "Tjanting is a tool used to ______.", "options": {"A": "carve wood", "B": "remove wax from cloth", "C": "apply wax on cloth", "D": "carve stone"}, "answer": "C"},
    {"stem": "The following are elements of art EXCEPT ______.", "options": {"A": "form", "B": "line", "C": "texture", "D": "colour"}, "answer": "D"},
    {"stem": "Motif can be obtained from the following EXCEPT ______.", "options": {"A": "animal", "B": "object", "C": "fruits", "D": "water"}, "answer": "D"},
    {"stem": "Crocheting is craft in which fabric is formed with ______ and ______.", "options": {"A": "bag and ball", "B": "thread and hook", "C": "bowl and hook", "D": "needle and thread"}, "answer": "B"},
    {"stem": "When white is added to a colour it is called ______.", "options": {"A": "tint", "B": "grey", "C": "light", "D": "shade"}, "answer": "A"},
    {"stem": "The visual illusion of depth on a flat surface is ______.", "options": {"A": "Pointillism", "B": "foreshortening", "C": "perspective", "D": "directive"}, "answer": "C"},
    {"stem": "Tsoede figures originated from ______ village in Niger State.", "options": {"A": "Suleja", "B": "Tada", "C": "Kontagora", "D": "Paiko"}, "answer": "B"},
    {"stem": "Example of nature painting is ______.", "options": {"A": "painting of table", "B": "painting of flower", "C": "painting of bowl", "D": "painting of houses"}, "answer": "B"},
    {"stem": "A poster design without a centre of interest does not show the principle of ______.", "options": {"A": "harmony", "B": "balance", "C": "dominance", "D": "rhythm"}, "answer": "C"},
    {"stem": "An example of still life painting is ______.", "options": {"A": "painting of mountain", "B": "painting of trees", "C": "painting of objects made by man", "D": "painting of figures"}, "answer": "C"},
    {"stem": "Painting on wall is ______.", "options": {"A": "abstract", "B": "mural", "C": "high painting", "D": "wash"}, "answer": "B"},
    {"stem": "FESTAC 77 mask represents ______.", "options": {"A": "Queen mother Idia of Benin", "B": "Queen Ida of Atta", "C": "Queen Amina of Zaria", "D": "Queen mother Jemilla of Nupe"}, "answer": "A"},
    {"stem": "A liquid substance used in joining clay works is called ______.", "options": {"A": "slip", "B": "mud", "C": "pop", "D": "adhesive"}, "answer": "A"},
    {"stem": "Designing done on wrappers to protect products are ______.", "options": {"A": "passaging", "B": "package", "C": "design", "D": "package design"}, "answer": "D"},
    {"stem": "Cire-perdue technique of casting is also known as ______.", "options": {"A": "mosaic", "B": "tie and dye", "C": "batik", "D": "lost wax"}, "answer": "D"},
    {"stem": "The diagram above represents ______.", "options": {"A": "Nok terracotta", "B": "Benin bronze head", "C": "Igbo ukwu", "D": "Ife bronze"}, "answer": "B", "image": "no 59 and no 60 js3 cca objective.jpg", "caption": "Diagram for questions on Benin bronze head"},
    {"stem": "Which of the following is true about the above diagram?", "options": {"A": "very detailed and naturalistic", "B": "triangular eye sockets", "C": "highly decorated with bead", "D": "pierced eyes"}, "answer": "C", "image": "no 59 and no 60 js3 cca objective.jpg", "caption": "Diagram for questions on Benin bronze head"},
]

THEORY = [
    {"stem": "What is tie and dye?\n\nMention four methods of tying.\n\nName one difference and one similarity between tie dyeing and batik.", "marks": Decimal("10.00")},
    {"stem": "Define batik.\n\nDifferentiate between carving and weaving.\n\nEnumerate four major art cultures in Nigeria.", "marks": Decimal("10.00")},
    {"stem": "Write short notes on any six of the following:\nAbstract art\nmuseum\ndrawing\npolychrome painting\nperspective drawing\nfresco\ngraffiti", "marks": Decimal("10.00")},
    {"stem": "What is shading?\n\nList four methods of shading.\n\nState the meaning of curator.", "marks": Decimal("10.00")},
    {"stem": "What is craft?\n\nMention four local crafts.\n\nWhat is exhibition?", "marks": Decimal("10.00")},
    {"stem": "With the aid of a diagram, illustrate the branches or types of art.", "marks": Decimal("10.00")},
]


def _image_data_uri(image_name: str) -> str:
    path = IMAGE_PATHS.get(image_name)
    if path is None:
        raise FileNotFoundError(f"Missing image mapping for exam image: {image_name}")
    if not path.exists():
        raise FileNotFoundError(f"Missing exam image: {path}")
    encoded = base64.b64encode(path.read_bytes()).decode("ascii")
    suffix = path.suffix.lower()
    mime = "image/png" if suffix == ".png" else "image/jpeg"
    return f"data:{mime};base64,{encoded}"


def _rich_stem_with_image(stem: str, *, image_name: str, caption: str = "") -> str:
    body = "<br>".join(line.strip() for line in stem.splitlines() if line.strip())
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


def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    subject = Subject.objects.get(code="CCA")
    academic_class = AcademicClass.objects.get(code="JS3")
    teacher = User.objects.get(username="abel@ndgakuje.org")
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher=teacher,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        is_active=True,
    )

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 24, 11, 0, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 24, 12, 10, tzinfo=lagos)

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
            "dean_review_comment": "Approved for Tuesday late morning paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Tuesday, March 24, 2026 11:00 AM WAT.",
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
    exam.dean_review_comment = "Approved for Tuesday late morning paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Tuesday, March 24, 2026 11:00 AM WAT."
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
        rich_stem = ""
        if item.get("image"):
            rich_stem = _rich_stem_with_image(item["stem"], image_name=item["image"], caption=item.get("caption", ""))
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=item["stem"],
            rich_stem=rich_stem,
            marks=Decimal("1.00"),
            source_reference=f"JS3-CCA-20260324-OBJ-{index:02d}",
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
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            marks=item["marks"],
            source_reference=f"JS3-CCA-20260324-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 60
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "JS3-CCA-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "20.00",
        "theory_target_max": "40.00",
        "rich_stem_objective_rows": [index for index, item in enumerate(OBJECTIVES, start=1) if item.get("image")],
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
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration": blueprint.duration_minutes,
            "image_rows": [index for index, item in enumerate(OBJECTIVES, start=1) if item.get("image")],
        }
    )


main()
