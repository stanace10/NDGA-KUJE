from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("dashboard", "0006_schoolprofile_dean_comment_guidance_and_more"),
    ]

    operations = [
        migrations.CreateModel(
            name="PublicSiteSubmission",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("submission_type", models.CharField(choices=[("CONTACT", "Contact Enquiry"), ("ADMISSION", "Admission Registration")], default="CONTACT", max_length=16)),
                ("status", models.CharField(choices=[("NEW", "New"), ("IN_REVIEW", "In Review"), ("CLOSED", "Closed")], default="NEW", max_length=16)),
                ("contact_name", models.CharField(max_length=180)),
                ("contact_email", models.EmailField(blank=True, max_length=254)),
                ("contact_phone", models.CharField(blank=True, max_length=40)),
                ("category", models.CharField(blank=True, max_length=80)),
                ("subject", models.CharField(blank=True, max_length=180)),
                ("message", models.TextField(blank=True)),
                ("applicant_name", models.CharField(blank=True, max_length=180)),
                ("applicant_date_of_birth", models.DateField(blank=True, null=True)),
                ("intended_class", models.CharField(blank=True, max_length=40)),
                ("guardian_name", models.CharField(blank=True, max_length=180)),
                ("guardian_email", models.EmailField(blank=True, max_length=254)),
                ("guardian_phone", models.CharField(blank=True, max_length=40)),
                ("residential_address", models.TextField(blank=True)),
                ("previous_school", models.CharField(blank=True, max_length=180)),
                ("boarding_option", models.CharField(blank=True, max_length=24)),
                ("medical_notes", models.TextField(blank=True)),
                ("passport_photo", models.ImageField(blank=True, null=True, upload_to="public_submissions/passports/")),
                ("birth_certificate", models.FileField(blank=True, null=True, upload_to="public_submissions/birth_certificates/")),
                ("school_result", models.FileField(blank=True, null=True, upload_to="public_submissions/school_results/")),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "ordering": ("-created_at",),
            },
        ),
        migrations.AddIndex(
            model_name="publicsitesubmission",
            index=models.Index(fields=["submission_type", "status", "created_at"], name="dashboard_p_submis_7a8e95_idx"),
        ),
        migrations.AddIndex(
            model_name="publicsitesubmission",
            index=models.Index(fields=["contact_email"], name="dashboard_p_contact_a36db8_idx"),
        ),
        migrations.AddIndex(
            model_name="publicsitesubmission",
            index=models.Index(fields=["intended_class"], name="dashboard_p_intende_915938_idx"),
        ),
    ]
