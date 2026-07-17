from django.contrib import admin

from apps.academics.models import (
    AcademicClass,
    AcademicSession,
    ClassSubject,
    FormTeacherAssignment,
    GradeScale,
    StudentClassEnrollment,
    Subject,
    TeacherSubjectAssignment,
    Term,
)

admin.site.register(AcademicSession)
admin.site.register(Term)
admin.site.register(AcademicClass)
admin.site.register(Subject)
admin.site.register(ClassSubject)
admin.site.register(TeacherSubjectAssignment)
admin.site.register(FormTeacherAssignment)
admin.site.register(StudentClassEnrollment)
admin.site.register(GradeScale)
