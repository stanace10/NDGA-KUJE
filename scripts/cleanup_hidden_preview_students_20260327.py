from django.contrib.auth import get_user_model

from apps.academics.models import AcademicClass, ClassSubject, StudentClassEnrollment, StudentSubjectEnrollment
from apps.finance.models import Payment, PaymentGatewayTransaction, Receipt, StudentCharge
from apps.notifications.models import Notification
from apps.pdfs.models import PDFArtifact
from apps.results.models import ClassResultCompilation, ClassResultStudentRecord, ResultAccessPin, ResultSheet, StudentSubjectScore


User = get_user_model()
PREVIEW_STUDENT_PREFIX = "preview-20260327-"
PREVIEW_CLASS_PREFIX = "TST-20260327-"


preview_students = list(User.objects.filter(username__startswith=PREVIEW_STUDENT_PREFIX))
preview_student_ids = [row.id for row in preview_students]
preview_classes = list(AcademicClass.objects.filter(code__startswith=PREVIEW_CLASS_PREFIX))

if preview_student_ids:
    ResultAccessPin.objects.filter(student_id__in=preview_student_ids).delete()
    PDFArtifact.objects.filter(student_id__in=preview_student_ids).delete()
    Notification.objects.filter(recipient_id__in=preview_student_ids).delete()
    Receipt.objects.filter(payment__student_id__in=preview_student_ids).delete()
    Payment.objects.filter(student_id__in=preview_student_ids).delete()
    PaymentGatewayTransaction.objects.filter(student_id__in=preview_student_ids).delete()
    StudentCharge.objects.filter(student_id__in=preview_student_ids).delete()
    StudentSubjectScore.objects.filter(student_id__in=preview_student_ids).delete()
    ClassResultStudentRecord.objects.filter(student_id__in=preview_student_ids).delete()
    StudentSubjectEnrollment.objects.filter(student_id__in=preview_student_ids).delete()
    StudentClassEnrollment.objects.filter(student_id__in=preview_student_ids).delete()
    User.objects.filter(id__in=preview_student_ids).delete()

if preview_classes:
    preview_class_ids = [row.id for row in preview_classes]
    ResultSheet.objects.filter(academic_class_id__in=preview_class_ids).delete()
    ClassResultCompilation.objects.filter(academic_class_id__in=preview_class_ids).delete()
    ClassSubject.objects.filter(academic_class_id__in=preview_class_ids).delete()
    AcademicClass.objects.filter(id__in=preview_class_ids).delete()

print("PREVIEW_STUDENTS_CLEANED")
