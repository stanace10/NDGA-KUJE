"""Replace generic Draft notes with exact paper-specific blockers."""

from apps.cbt.models import CBTExamStatus, Exam


ISSUES = {
    1043: "40 objective questions but only 39 source answer markers; one answer key cannot be independently verified.",
    1041: "Four repeated objective questions in the supplied Digital Technology source; teacher must provide four replacements.",
    1045: "38 safe objective blocks from 39 source answer markers; one French question block was not safely recoverable.",
    1038: "39 safe questions from 40 answer markers; PDF extraction also corrupted mathematical expressions and truncated stems.",
    1039: "39 safe questions from 40 source answer markers; one Music question is missing.",
    1048: "Yoruba source produced 82 answer markers but only 78 safe questions; malformed trailing/language blocks require teacher correction.",
    1057: "47 safe Basic Science questions from 50 source answer markers; three questions are missing.",
    1059: "39 safe French questions from 40 source answer markers; one question is missing.",
    1063: "Igbo source is heavily merged: 61 parsed questions versus 78 answer markers, two duplicates, and malformed text around Question 23.",
    1049: "49 safe questions from 50 answer markers, three duplicate stems, and a truncated algebraic expression in the PDF extraction.",
    1051: "39 safe Music questions from 40 source answer markers; one question is missing and several source endings need teacher confirmation.",
    1077: "48 CRS questions but only 47 explicit source answer markers; at least one answer key is not independently verifiable.",
    1078: "48 safe Economics questions from 50 source answer markers; two questions are missing.",
    1071: "49 safe Food & Nutrition questions from 50 markers; one question is missing and Question 48 is truncated in the source text.",
    1081: "French source has ambiguous numbering/answer blocks (60 parsed questions and 67 answer markers); teacher confirmation is required.",
    1079: "Further Mathematics PDF extraction corrupted powers, roots, vectors and formula stems; 40 parsed rows versus 51 answer markers.",
    1064: "Mathematics PDF extraction corrupted powers, fractions and formula stems; 42 parsed rows versus 50 answer markers.",
    1095: "50 CRS questions but only 49 explicit source answer markers; one key is unverified and two stems end incompletely.",
    1085: "Only 18 safe Civic Education questions recovered from 47 answer markers; 29 source questions were merged or lost.",
    1096: "49 safe Economics questions from 50 source answer markers; one question is missing.",
    1088: "45 safe English questions from 50 source answer markers; five questions are missing.",
    1090: "47 safe Food & Nutrition questions from 50 source answer markers; three questions are missing.",
    1099: "54 safe French questions from 55 source answer markers; one question is missing.",
    1092: "The supplied Physics paper repeats the electric-charge SI-unit question (Questions 12 and 21); teacher must provide one replacement.",
    1083: "38 safe Visual Art questions from 40 source answer markers; two questions are missing.",
}


def run():
    updated = []
    for exam_id, issue in ISSUES.items():
        exam = Exam.objects.get(pk=exam_id)
        if exam.status != CBTExamStatus.DRAFT:
            raise RuntimeError(f"Exam {exam_id} is no longer Draft; refusing to overwrite its note.")
        exam.open_now = False
        exam.activation_comment = f"HELD SAFELY IN DRAFT - {issue}"
        exam.save(update_fields=["open_now", "activation_comment", "updated_at"])
        updated.append((exam_id, exam.academic_class.code, exam.subject.code, issue))
    print({"annotated_drafts": updated, "count": len(updated)})


run()
