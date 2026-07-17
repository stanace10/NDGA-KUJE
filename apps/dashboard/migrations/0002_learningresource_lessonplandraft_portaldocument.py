import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('academics', '0007_campus_academicclass_campus'),
        ('dashboard', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='LearningResource',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=180)),
                ('description', models.TextField(blank=True)),
                ('category', models.CharField(choices=[('STUDY_MATERIAL', 'Study Material'), ('PAST_QUESTION', 'Past Question'), ('ASSIGNMENT', 'Assignment'), ('PRACTICE', 'Practice')], default='STUDY_MATERIAL', max_length=24)),
                ('content_text', models.TextField(blank=True)),
                ('resource_file', models.FileField(blank=True, null=True, upload_to='learning/resources/')),
                ('external_url', models.URLField(blank=True)),
                ('due_date', models.DateField(blank=True, null=True)),
                ('is_published', models.BooleanField(default=True)),
                ('academic_class', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='learning_resources', to='academics.academicclass')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='learning_resources', to='academics.academicsession')),
                ('subject', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='learning_resources', to='academics.subject')),
                ('term', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='learning_resources', to='academics.term')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_learning_resources', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', 'title'),
            },
        ),
        migrations.CreateModel(
            name='LessonPlanDraft',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('topic', models.CharField(max_length=180)),
                ('teaching_goal', models.TextField(blank=True)),
                ('teacher_notes', models.TextField(blank=True)),
                ('lesson_objectives', models.TextField()),
                ('lesson_outline', models.TextField()),
                ('class_activity', models.TextField()),
                ('assignment_text', models.TextField(blank=True)),
                ('quiz_text', models.TextField(blank=True)),
                ('publish_to_learning_hub', models.BooleanField(default=False)),
                ('assignment_due_date', models.DateField(blank=True, null=True)),
                ('academic_class', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lesson_plan_drafts', to='academics.academicclass')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lesson_plan_drafts', to='academics.academicsession')),
                ('subject', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lesson_plan_drafts', to='academics.subject')),
                ('teacher', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='lesson_plan_drafts', to=settings.AUTH_USER_MODEL)),
                ('term', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='lesson_plan_drafts', to='academics.term')),
            ],
            options={
                'ordering': ('-created_at',),
            },
        ),
        migrations.CreateModel(
            name='PortalDocument',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('title', models.CharField(max_length=180)),
                ('category', models.CharField(choices=[('TRANSCRIPT', 'Transcript'), ('CERTIFICATE', 'Certificate'), ('STUDENT_RECORD', 'Student Record'), ('GRADUATION_RECORD', 'Graduation Record'), ('GENERAL', 'General')], default='GENERAL', max_length=24)),
                ('document_file', models.FileField(upload_to='vault/documents/')),
                ('notes', models.TextField(blank=True)),
                ('is_visible_to_student', models.BooleanField(default=False)),
                ('academic_class', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vault_documents', to='academics.academicclass')),
                ('session', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vault_documents', to='academics.academicsession')),
                ('student', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='vault_documents', to=settings.AUTH_USER_MODEL)),
                ('term', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vault_documents', to='academics.term')),
                ('uploaded_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='uploaded_vault_documents', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ('-created_at', 'title'),
            },
        ),
    ]
