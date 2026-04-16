from __future__ import annotations

import base64
from decimal import Decimal
from pathlib import Path
import uuid

from django.core import signing
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.constants import ROLE_BURSAR, ROLE_IT_MANAGER, ROLE_PRINCIPAL, ROLE_VP
from apps.accounts.models import User
from apps.dashboard.forms import PublicAdmissionRegistrationForm, PublicContactForm
from apps.dashboard.models import (
    PublicAdmissionGatewayProvider,
    PublicAdmissionGatewayStatus,
    PublicAdmissionPaymentMode,
    PublicAdmissionPaymentStatus,
    PublicAdmissionWorkflowStatus,
    PublicAdmissionPaymentTransaction,
    PublicSiteSubmission,
    PublicSubmissionType,
    SchoolProfile,
)
from apps.dashboard.public_admission_utils import build_public_admission_snapshot
from apps.finance.services import (
    _flutterwave_api_request,
    _paystack_api_request,
    finance_profile,
    gateway_is_enabled,
    gateway_provider_label,
)
from apps.notifications.models import NotificationCategory
from apps.notifications.services import create_bulk_notifications, send_email_event
from apps.pdfs.services import render_pdf_bytes, school_logo_data_uri
from apps.dashboard.public_site import (
    PUBLIC_INDEXABLE_PATHS,
    get_public_events,
    get_public_gallery,
    get_public_gallery_category,
    get_public_contact,
    get_public_news,
    get_public_news_item,
    get_public_page,
    get_public_site_context,
    public_site_enabled,
)
from apps.tenancy.utils import build_portal_url


def _management_team_recipients(*, include_bursar=False, include_principal=False):
    role_codes = [ROLE_IT_MANAGER, ROLE_VP]
    if include_principal:
        role_codes.append(ROLE_PRINCIPAL)
    if include_bursar:
        role_codes.append(ROLE_BURSAR)
    role_filter = Q(primary_role__code__in=role_codes) | Q(secondary_roles__code__in=role_codes)
    return list(User.objects.filter(is_active=True).filter(role_filter).distinct())


def _notify_public_submission(*, submission, request):
    profile = SchoolProfile.load()
    include_bursar = submission.submission_type == "ADMISSION"
    recipients = _management_team_recipients(
        include_bursar=include_bursar,
        include_principal=submission.submission_type == "ADMISSION",
    )
    if submission.submission_type == "ADMISSION":
        title = f"New admission application: {submission.applicant_name or submission.contact_name}"
        message = (
            f"{submission.applicant_name or submission.contact_name} applied for {submission.intended_class or '-'}.\n"
            f"Guardian: {submission.guardian_name or submission.contact_name} | "
            f"Phone: {submission.guardian_phone or submission.contact_phone or '-'} | "
            f"Payment: {submission.get_payment_status_display()}."
        )
    else:
        title = f"New live chat: {submission.subject or submission.category or 'Website message'}"
        message = (
            f"{submission.contact_name} sent a {submission.category or 'website'} message.\n"
            f"Email: {submission.contact_email or '-'} | Phone: {submission.contact_phone or '-'}.\n\n"
            f"Message:\n{submission.message or '-'}"
        )
    if recipients:
        create_bulk_notifications(
            recipients=recipients,
            category=NotificationCategory.SYSTEM,
            title=title,
            message=message,
            action_url="/notifications/center/",
            metadata={
                "event": "PUBLIC_SITE_SUBMISSION",
                "submission_id": str(submission.id),
                "submission_type": submission.submission_type,
            },
        )
    send_email_event(
        to_emails=[profile.contact_email or "office@ndgakuje.org"],
        subject=f"NDGA Website: {title}",
        body_text=f"{message}\n\nOpen the portal notification center for follow-up.",
        request=request,
        metadata={
            "event": "PUBLIC_SITE_SUBMISSION",
            "submission_id": str(submission.id),
            "submission_type": submission.submission_type,
        },
    )


def _live_chat_category_and_subject(message: str) -> tuple[str, str]:
    normalized = (message or "").strip().lower()
    if any(term in normalized for term in ("complain", "complaint", "issue", "problem", "report", "not happy")):
        return ("Complaint", "Live Chat Complaint")
    if any(term in normalized for term in ("admission", "apply", "application", "registration", "screening", "enrol")):
        return ("Admissions", "Live Chat Admissions Enquiry")
    if any(term in normalized for term in ("boarding", "hostel", "boarder", "dorm")):
        return ("Boarding", "Live Chat Boarding Enquiry")
    if any(term in normalized for term in ("portal", "login", "password", "result checker", "student portal")):
        return ("Portal Support", "Live Chat Portal Support")
    if any(term in normalized for term in ("where", "direction", "location", "map", "address", "kuje")):
        return ("Directions", "Live Chat Directions Request")
    return ("General Enquiry", "Live Chat General Enquiry")


def _send_live_chat_confirmation(*, submission, request, ticket_reference: str):
    if not submission.contact_email:
        return
    body_text = (
        f"Your NDGA ticket has been created.\n\n"
        f"Reference: {ticket_reference}\n"
        f"Category: {submission.category or 'General Enquiry'}\n"
        f"Name: {submission.contact_name or '-'}\n"
        f"Email: {submission.contact_email}\n"
        f"Phone: {submission.contact_phone or '-'}\n\n"
        f"Message:\n{submission.message or '-'}\n\n"
        f"The school has received your message and follow-up will come through this email address."
    )
    send_email_event(
        to_emails=[submission.contact_email],
        subject=f"NDGA Ticket Created: {ticket_reference}",
        body_text=body_text,
        request=request,
        metadata={
            "event": "PUBLIC_LIVE_CHAT_CONFIRMATION",
            "submission_id": str(submission.id),
            "ticket_reference": ticket_reference,
        },
    )


def _default_chatbot_prompts():
    return [
        "How do I apply?",
        "Tell me about NDGA.",
        "What is boarding like?",
        "How do I contact the school?",
    ]


def _build_public_chatbot_payload(*, school_profile=None):
    public_contact = get_public_contact(school_profile=school_profile)
    school_name = public_contact["school_name"]
    contact_parts = [public_contact["phone_primary"]]
    if public_contact.get("phone_secondary"):
        contact_parts.append(public_contact["phone_secondary"])
    contact_summary = ", ".join([item for item in contact_parts if item])

    return {
        "school_name": school_name,
        "welcome": "Ask about admissions, boarding, academics, safeguarding, school life, portal help, or directions.",
        "fallback": {
            "reply": (
                "I can help with NDGA admissions, boarding, academics, school life, safeguarding, "
                "contact details, directions, and portal guidance. Try one of the quick prompts below "
                "or ask your question in a short sentence."
            ),
            "suggestions": [
                "How do I apply?",
                "Tell me about NDGA.",
                "What is boarding like?",
                "How do I contact the school?",
            ],
            "links": [
                {"label": "Admissions Overview", "url": "/admissions/"},
                {"label": "Contact Us", "url": "/contact/"},
            ],
        },
        "human_prompt": (
            "If you want a direct follow-up from the school, use Talk to School and your message will go to management."
        ),
        "answers": [
            {
                "key": "about-school",
                "phrases": [
                    "about school",
                    "about ndga",
                    "tell me about ndga",
                    "tell me about the school",
                    "what kind of school is ndga",
                    "who owns the school",
                    "who manages the school",
                ],
                "keywords": ["about", "school", "ndga", "catholic", "sisters", "owned", "managed", "academy"],
                "reply": (
                    f"{school_name} is a Catholic girls' secondary school owned and managed by the Sisters of "
                    "Notre Dame de Namur. The school is committed to academic excellence, discipline, faith "
                    "formation, service, and the full development of every girl."
                ),
                "links": [
                    {"label": "About NDGA", "url": "/about/"},
                    {"label": "Principal's Welcome", "url": "/principal/"},
                ],
                "suggestions": [
                    "What is boarding like?",
                    "How do I apply?",
                    "Where is the school located?",
                ],
            },
            {
                "key": "principal",
                "phrases": [
                    "principal",
                    "principal welcome",
                    "welcome message",
                    "leadership",
                ],
                "keywords": ["principal", "leadership", "welcome", "head", "administrator"],
                "reply": (
                    "The principal's message presents NDGA as a Catholic secondary school dedicated to forming "
                    "confident, competent, and compassionate young women through strong academics, character, "
                    "faith, and service."
                ),
                "links": [
                    {"label": "Principal's Welcome", "url": "/principal/"},
                    {"label": "Leadership", "url": "/about/leadership/"},
                ],
                "suggestions": [
                    "Tell me about NDGA.",
                    "What do students study?",
                    "How do I contact the school?",
                ],
            },
            {
                "key": "admissions",
                "phrases": [
                    "how do i apply",
                    "how can i apply",
                    "online registration",
                    "admission form",
                    "registration form",
                    "how to register",
                    "how do i register",
                ],
                "keywords": [
                    "apply",
                    "application",
                    "admission",
                    "register",
                    "registration",
                    "form",
                    "submit",
                ],
                "reply": (
                    "Families begin from the Online Registration page. Complete the student details, school "
                    "background, parent or guardian details, declaration, and document uploads, then submit the "
                    "application and follow the payment choice shown after submission."
                ),
                "links": [
                    {"label": "Online Registration", "url": "/admissions/registration/"},
                    {"label": "How to Apply", "url": "/admissions/how-to-apply/"},
                    {"label": "Admissions Overview", "url": "/admissions/"},
                ],
                "suggestions": [
                    "What are the entrance exam subjects?",
                    "What documents are needed?",
                    "Talk to admissions.",
                ],
            },
            {
                "key": "documents",
                "phrases": [
                    "documents needed",
                    "required documents",
                    "what documents are needed",
                    "what should i upload",
                ],
                "keywords": ["document", "upload", "passport", "birth", "certificate", "result", "medical"],
                "reply": (
                    "The registration process asks for supporting documents such as passport photographs, a birth "
                    "certificate, the last school result, a medical fitness report, and payment evidence where required."
                ),
                "links": [
                    {"label": "Online Registration", "url": "/admissions/registration/"},
                    {"label": "How to Apply", "url": "/admissions/how-to-apply/"},
                ],
                "suggestions": [
                    "How do I apply?",
                    "What is boarding like?",
                    "How do I contact the school?",
                ],
            },
            {
                "key": "screening",
                "phrases": [
                    "entrance exam",
                    "entrance screening",
                    "screening subjects",
                    "exam subjects",
                    "interview",
                ],
                "keywords": ["screening", "exam", "entrance", "subject", "interview", "test"],
                "reply": (
                    "After registration review, applicants are guided through screening. The written screening covers "
                    "English Language, Mathematics, and General Paper, and the school gives further guidance for any next step."
                ),
                "links": [
                    {"label": "Admission FAQs", "url": "/admissions/admission-faqs/"},
                    {"label": "How to Apply", "url": "/admissions/how-to-apply/"},
                ],
                "suggestions": [
                    "How do I apply?",
                    "What documents are needed?",
                    "Talk to admissions.",
                ],
            },
            {
                "key": "boarding",
                "phrases": [
                    "what is boarding like",
                    "tell me about boarding",
                    "hostel life",
                    "day or boarding",
                ],
                "keywords": ["boarding", "hostel", "boarder", "day", "routine", "prep", "welfare"],
                "reply": (
                    "NDGA offers boarding and day options. Boarding includes supervised prep, structured daily routine, "
                    "pastoral care, student welfare guidance, and a calm environment designed for study, discipline, and growth."
                ),
                "links": [
                    {"label": "Hostel & Boarding", "url": "/hostel-boarding/"},
                    {"label": "Life at NDGA", "url": "/life-at-ndga/"},
                ],
                "suggestions": [
                    "Tell me about NDGA.",
                    "What do students study?",
                    "Where is the school located?",
                ],
            },
            {
                "key": "academics",
                "phrases": [
                    "what do students study",
                    "tell me about academics",
                    "subjects offered",
                    "curriculum",
                    "waec",
                    "neco",
                ],
                "keywords": ["academic", "academics", "subject", "curriculum", "waec", "neco", "jss", "ss"],
                "reply": (
                    "NDGA provides junior and senior secondary education with core subjects, science and ICT exposure, "
                    "structured assessment, exam preparation, and guided academic support. Learning is strengthened by "
                    "co-curricular activities and the wider formation of students."
                ),
                "links": [
                    {"label": "Academics Overview", "url": "/academics/"},
                    {"label": "Subjects & Departments", "url": "/academics/subjects-departments/"},
                    {"label": "Assessment", "url": "/academics/examinations-assessment/"},
                ],
                "suggestions": [
                    "What is boarding like?",
                    "Tell me about school life.",
                    "How do I apply?",
                ],
            },
            {
                "key": "life-and-facilities",
                "phrases": [
                    "school life",
                    "life at ndga",
                    "clubs and activities",
                    "sports",
                    "facilities",
                ],
                "keywords": ["life", "clubs", "activities", "sports", "facility", "facilities", "laboratory", "library"],
                "reply": (
                    "Student life at NDGA includes clubs, leadership, sports, faith activities, assemblies, and community life. "
                    "The public site also highlights classrooms, labs, ICT spaces, the library, hostel areas, and other learning environments."
                ),
                "links": [
                    {"label": "Life at NDGA", "url": "/life-at-ndga/"},
                    {"label": "Facilities", "url": "/facilities/"},
                    {"label": "Clubs & Activities", "url": "/academics/co-curricular-activities/"},
                ],
                "suggestions": [
                    "Tell me about NDGA.",
                    "What is boarding like?",
                    "How do I contact the school?",
                ],
            },
            {
                "key": "safeguarding",
                "phrases": [
                    "child safeguarding",
                    "safeguarding",
                    "student safety",
                    "welfare",
                    "child protection",
                ],
                "keywords": ["safeguarding", "safety", "welfare", "protect", "protection", "care"],
                "reply": (
                    "Child safeguarding remains part of the school's duty of care. NDGA recognises every child as a gift "
                    "from God and works with parents and guardians to protect student welfare, dignity, and safety."
                ),
                "links": [
                    {"label": "School Life", "url": "/about/school-life/"},
                    {"label": "About NDGA", "url": "/about/"},
                ],
                "suggestions": [
                    "Tell me about NDGA.",
                    "What is boarding like?",
                    "How do I contact the school?",
                ],
            },
            {
                "key": "contact-and-location",
                "phrases": [
                    "how do i contact the school",
                    "contact the school",
                    "contact admissions",
                    "where is the school",
                    "school address",
                    "directions",
                ],
                "keywords": ["contact", "phone", "email", "office", "location", "address", "map", "direction"],
                "reply": (
                    f"You can reach the school by phone on {contact_summary} or by email at {public_contact['email']}. "
                    f"The school is located at {public_contact['address']}."
                ),
                "links": [
                    {"label": "Contact Us", "url": "/contact/"},
                    {"label": "Open Map", "url": public_contact["maps_url"]},
                ],
                "suggestions": [
                    "How do I apply?",
                    "Tell me about NDGA.",
                    "Talk to admissions.",
                ],
            },
            {
                "key": "portal",
                "phrases": [
                    "school portal",
                    "portal help",
                    "results",
                    "student portal",
                    "parent portal",
                ],
                "keywords": ["portal", "result", "results", "login", "parent", "student"],
                "reply": (
                    "The School Portal is mainly for existing students and parents to access approved school information, "
                    "results, and related records. New applicants should begin from the public admissions pages first."
                ),
                "links": [
                    {"label": "School Portal", "url": "/auth/login/?audience=student"},
                    {"label": "Online Registration", "url": "/admissions/registration/"},
                ],
                "suggestions": [
                    "How do I apply?",
                    "How do I contact the school?",
                    "Talk to admissions.",
                ],
            },
            {
                "key": "payments",
                "phrases": [
                    "payment",
                    "pay online",
                    "pay at school",
                    "bursar",
                    "application payment",
                ],
                "keywords": ["payment", "pay", "fees", "fee", "bursar", "receipt", "online", "physical"],
                "reply": (
                    "Application payment guidance is handled inside the admissions process. After registration, families "
                    "follow the payment option shown for the application, while school fee guidance is shared directly by the school."
                ),
                "links": [
                    {"label": "Online Registration", "url": "/admissions/registration/"},
                    {"label": "Payment Information", "url": "/admissions/payment-information/"},
                ],
                "suggestions": [
                    "How do I apply?",
                    "How do I contact the school?",
                    "Talk to admissions.",
                ],
            },
            {
                "key": "human",
                "phrases": [
                    "talk to admissions",
                    "talk to management",
                    "speak to someone",
                    "human agent",
                    "live chat",
                ],
                "keywords": ["human", "agent", "management", "admissions", "speak", "person"],
                "reply": (
                    "I can open a direct follow-up form for the school team. Leave your contact details and message, and management will respond."
                ),
                "links": [
                    {"label": "Contact Us", "url": "/contact/"},
                ],
                "suggestions": [
                    "Talk to admissions.",
                ],
            },
        ],
    }


PUBLIC_ADMISSION_ACCESS_SALT = "public-admission-access"
DEFAULT_PUBLIC_ADMISSION_FEE = Decimal("5500.00")


def _public_admission_reference(submission):
    existing = (submission.application_fee_reference or "").strip().upper()
    if existing:
        return existing
    return f"NDGA-APP-{timezone.localdate():%Y}-{submission.id:05d}"


def _public_admission_access_token(submission):
    return signing.dumps({"submission_id": submission.id}, salt=PUBLIC_ADMISSION_ACCESS_SALT)


def _resolve_public_admission_from_token(token):
    raw = (token or "").strip()
    if not raw:
        return None
    try:
        payload = signing.loads(raw, salt=PUBLIC_ADMISSION_ACCESS_SALT, max_age=60 * 60 * 24 * 90)
    except signing.BadSignature:
        return None
    submission_id = payload.get("submission_id")
    if not submission_id:
        return None
    return (
        PublicSiteSubmission.objects.filter(
            pk=submission_id,
            submission_type=PublicSubmissionType.ADMISSION,
        )
        .prefetch_related("payment_transactions")
        .first()
    )


def _public_admission_status_url(*, request, submission):
    return build_portal_url(
        request,
        "landing",
        reverse("dashboard:public-registration-status"),
        query={"access": _public_admission_access_token(submission)},
    )


def _public_admission_callback_url(request):
    return build_portal_url(
        request,
        "landing",
        reverse("dashboard:public-registration-payment-callback"),
    )


def _public_admission_download_url(*, request, submission):
    return build_portal_url(
        request,
        "landing",
        reverse("dashboard:public-registration-form-download"),
        query={"access": _public_admission_access_token(submission)},
    )


def _apply_public_admission_defaults(submission):
    profile = finance_profile()
    update_fields = []
    configured_fee = Decimal(profile.application_form_fee_amount or 0)
    effective_fee = configured_fee if configured_fee > 0 else DEFAULT_PUBLIC_ADMISSION_FEE
    if submission.application_fee_amount <= 0 and effective_fee > 0:
        submission.application_fee_amount = effective_fee
        update_fields.append("application_fee_amount")
    if not (submission.application_fee_reference or "").strip():
        submission.application_fee_reference = _public_admission_reference(submission)
        update_fields.append("application_fee_reference")
    if update_fields:
        submission.save(update_fields=[*update_fields, "updated_at"])
    return submission


def _public_gateway_provider_cards():
    cards = []
    for code in (
        PublicAdmissionGatewayProvider.PAYSTACK,
        PublicAdmissionGatewayProvider.FLUTTERWAVE,
    ):
        cards.append(
            {
                "code": code,
                "label": gateway_provider_label(code),
                "enabled": gateway_is_enabled(code),
            }
        )
    return cards


def _public_payment_email_targets(submission):
    emails = []
    for value in [submission.guardian_email, submission.contact_email]:
        normalized = (value or "").strip().lower()
        if normalized and normalized not in emails:
            emails.append(normalized)
    return emails


def _public_payment_customer_name(submission):
    return (
        submission.guardian_name
        or submission.contact_name
        or submission.applicant_name
        or "NDGA Applicant"
    ).strip()


def _public_payment_customer_phone(submission):
    return (submission.guardian_phone or submission.contact_phone or "").strip()


def _build_public_admission_receipt_email(*, submission, transaction_row, request):
    acknowledgement_url = _public_admission_status_url(request=request, submission=submission)
    subject = f"NDGA Admission Payment Receipt | {submission.application_fee_reference}"
    body_text = (
        "Dear Parent/Guardian,\n\n"
        "Your NDGA online registration payment has been confirmed.\n\n"
        f"Application Code: {submission.application_fee_reference}\n"
        f"Applicant: {submission.applicant_name}\n"
        f"Intended Class: {submission.intended_class}\n"
        f"Amount Paid: NGN {submission.application_fee_amount}\n"
        f"Gateway: {gateway_provider_label(transaction_row.provider)}\n"
        f"Gateway Reference: {transaction_row.reference}\n\n"
        "Please print the acknowledgement page and bring it with the completed admission form to the school.\n"
        f"Acknowledgement Page: {acknowledgement_url}\n\n"
        "Thank you."
    )
    body_html = render_to_string(
        "notifications/email_body_public_admission_receipt.html",
        {
            "submission": submission,
            "transaction": transaction_row,
            "acknowledgement_url": acknowledgement_url,
            "gateway_label": gateway_provider_label(transaction_row.provider),
        },
    )
    return {
        "subject": subject,
        "body_text": body_text,
        "body_html": body_html,
    }


def _send_public_admission_processing_email(*, submission, request):
    targets = _public_payment_email_targets(submission)
    if not targets:
        return None
    acknowledgement_url = _public_admission_status_url(request=request, submission=submission)
    subject = f"NDGA Admission Application Received | {submission.application_fee_reference}"
    body_text = (
        "Dear Parent/Guardian,\n\n"
        "Your daughter's NDGA admission application has been received successfully and is now being processed.\n\n"
        f"Application Code: {submission.application_fee_reference}\n"
        f"Applicant: {submission.applicant_name}\n"
        f"Intended Class: {submission.intended_class}\n\n"
        "Please print the acknowledgement page and come to the school for payment and admissions follow-up.\n"
        f"Acknowledgement Page: {acknowledgement_url}\n\n"
        "If payment is not yet completed, please present the application code at the school bursary.\n\n"
        "Thank you.\n"
        "Notre Dame Girls' Academy"
    )
    body_html = render_to_string(
        "notifications/email_body_public_admission_processing.html",
        {
            "submission": submission,
            "acknowledgement_url": acknowledgement_url,
        },
    )
    return send_email_event(
        to_emails=targets,
        subject=subject,
        body_text=body_text,
        body_html=body_html,
        request=request,
        metadata={
            "event": "PUBLIC_ADMISSION_PROCESSING_ACKNOWLEDGEMENT",
            "submission_id": submission.id,
        },
    )


def _public_admission_form_error_summary(form):
    if not form.errors:
        return ""
    if form.non_field_errors():
        return "Please review the admission details and complete the required information before you submit again."
    return "Some required admission details are still missing. Please complete the highlighted applicant and guardian information."


def _public_admission_init_error_message(exc):
    messages = [str(item).strip() for item in (getattr(exc, "messages", None) or [str(exc)]) if str(item).strip()]
    combined = " ".join(messages)
    lowered = combined.lower()
    if "gateway request failed" in lowered or "network error" in lowered or "invalid gateway" in lowered:
        return "Online payment is coming soon. Please use the physical payment option with your application code for now."
    if "email is required" in lowered:
        return "A parent or guardian email address is required before online payment can continue."
    if "application fee has not been configured" in lowered:
        return "The application fee is not ready yet. Please contact the school office."
    if "select a valid payment gateway" in lowered:
        return "Please choose one of the available payment options to continue."
    if "is not configured" in lowered:
        return "Online payment is coming soon. Please use the physical payment option with your application code for now."
    return "We could not start the payment right now. Please try again or use the offline payment option with your application code."


def _public_default_gateway_provider():
    for row in _public_gateway_provider_cards():
        if row["enabled"]:
            return row["code"]
    return ""


def _record_public_admission_payment_preference(*, submission, mode):
    metadata = dict(submission.metadata or {})
    metadata["preferred_payment_mode"] = (mode or "").strip().upper()
    if mode == PublicAdmissionPaymentMode.PHYSICAL:
        metadata["physical_payment_selected_at"] = timezone.now().isoformat()
    submission.metadata = metadata
    submission.save(update_fields=["metadata", "updated_at"])
    return submission


def _initialize_public_admission_payment(*, submission, provider, request):
    submission = _apply_public_admission_defaults(submission)
    _record_public_admission_payment_preference(
        submission=submission,
        mode=PublicAdmissionPaymentMode.ONLINE,
    )
    amount = Decimal(submission.application_fee_amount or 0).quantize(Decimal("0.01"))
    if amount <= Decimal("0.00"):
        raise ValidationError("Application fee has not been configured yet.")

    selected_provider = (provider or "").strip().upper()
    if selected_provider not in dict(PublicAdmissionGatewayProvider.choices):
        raise ValidationError("Select a valid payment gateway.")
    if not gateway_is_enabled(selected_provider):
        raise ValidationError(f"{gateway_provider_label(selected_provider)} is not configured.")

    payer_email = (_public_payment_email_targets(submission) or [None])[0]
    if not payer_email:
        raise ValidationError("Parent or guardian email is required for online payment.")

    reference = f"NDGA-APPPAY-{timezone.now():%Y%m%d%H%M%S}-{uuid.uuid4().hex[:8].upper()}"
    transaction_row = PublicAdmissionPaymentTransaction.objects.create(
        submission=submission,
        reference=reference,
        provider=selected_provider,
        status=PublicAdmissionGatewayStatus.PENDING,
        amount=amount,
        callback_url=_public_admission_callback_url(request),
        metadata={
            "application_fee_reference": submission.application_fee_reference,
            "applicant_name": submission.applicant_name,
            "intended_class": submission.intended_class,
        },
    )

    if selected_provider == PublicAdmissionGatewayProvider.PAYSTACK:
        payload = {
            "email": payer_email,
            "amount": int(amount * 100),
            "reference": reference,
            "callback_url": transaction_row.callback_url,
            "metadata": {
                "submission_id": submission.id,
                "payment_transaction_id": transaction_row.id,
                "application_fee_reference": submission.application_fee_reference,
            },
        }
        response = _paystack_api_request(path="/transaction/initialize", method="POST", payload=payload)
        if not response.get("status"):
            message = response.get("message") or "Gateway initialization failed."
            transaction_row.status = PublicAdmissionGatewayStatus.FAILED
            transaction_row.failure_reason = message
            transaction_row.metadata = {**transaction_row.metadata, "initialize_payload": payload, "initialize_response": response}
            transaction_row.save(update_fields=["status", "failure_reason", "metadata", "updated_at"])
            raise ValidationError(message)
        data = response.get("data") or {}
        transaction_row.status = PublicAdmissionGatewayStatus.INITIALIZED
        transaction_row.initialized_at = timezone.now()
        transaction_row.authorization_url = (data.get("authorization_url") or "")[:500]
        transaction_row.gateway_reference = (data.get("reference") or reference)[:180]
        transaction_row.metadata = {
            **transaction_row.metadata,
            "initialize_payload": payload,
            "initialize_response": response,
            "access_code": data.get("access_code", ""),
        }
        transaction_row.save(update_fields=["status", "initialized_at", "authorization_url", "gateway_reference", "metadata", "updated_at"])
        return transaction_row

    payload = {
        "tx_ref": reference,
        "amount": str(amount),
        "currency": "NGN",
        "redirect_url": transaction_row.callback_url,
        "customer": {
            "email": payer_email,
            "name": _public_payment_customer_name(submission),
            "phonenumber": _public_payment_customer_phone(submission),
        },
        "customizations": {
            "title": "Notre Dame Girls Academy",
            "description": f"NDGA admission application fee for {submission.applicant_name}",
        },
        "meta": {
            "submission_id": str(submission.id),
            "payment_transaction_id": str(transaction_row.id),
            "application_fee_reference": submission.application_fee_reference,
        },
    }
    response = _flutterwave_api_request(path="/payments", method="POST", payload=payload)
    if response.get("status") != "success":
        message = response.get("message") or "Gateway initialization failed."
        transaction_row.status = PublicAdmissionGatewayStatus.FAILED
        transaction_row.failure_reason = message
        transaction_row.metadata = {**transaction_row.metadata, "initialize_payload": payload, "initialize_response": response}
        transaction_row.save(update_fields=["status", "failure_reason", "metadata", "updated_at"])
        raise ValidationError(message)
    data = response.get("data") or {}
    transaction_row.status = PublicAdmissionGatewayStatus.INITIALIZED
    transaction_row.initialized_at = timezone.now()
    transaction_row.authorization_url = (data.get("link") or "")[:500]
    transaction_row.gateway_reference = (data.get("flw_ref") or reference)[:180]
    transaction_row.metadata = {
        **transaction_row.metadata,
        "initialize_payload": payload,
        "initialize_response": response,
    }
    transaction_row.save(update_fields=["status", "initialized_at", "authorization_url", "gateway_reference", "metadata", "updated_at"])
    return transaction_row


def _verify_public_admission_payment(*, reference, request):
    transaction_row = (
        PublicAdmissionPaymentTransaction.objects.select_related("submission")
        .filter(reference=(reference or "").strip())
        .first()
    )
    if transaction_row is None:
        raise ValidationError("Unknown payment reference.")
    if transaction_row.status == PublicAdmissionGatewayStatus.PAID:
        return transaction_row

    submission = _apply_public_admission_defaults(transaction_row.submission)
    amount = Decimal(transaction_row.amount or 0).quantize(Decimal("0.01"))
    transaction_row.verified_at = timezone.now()

    if transaction_row.provider == PublicAdmissionGatewayProvider.PAYSTACK:
        verification = _paystack_api_request(path=f"/transaction/verify/{transaction_row.reference}", method="GET")
        data = verification.get("data") or {}
        paid_ok = bool(verification.get("status")) and data.get("status") == "success"
        amount_ok = int(data.get("amount") or 0) == int(amount * 100)
        gateway_reference = (data.get("reference") or transaction_row.reference)[:180]
    else:
        verification = _flutterwave_api_request(
            path=f"/transactions/verify_by_reference?tx_ref={transaction_row.reference}",
            method="GET",
        )
        data = verification.get("data") or {}
        paid_ok = verification.get("status") == "success" and str(data.get("status") or "").lower() == "successful"
        amount_ok = Decimal(data.get("amount") or 0).quantize(Decimal("0.01")) == amount
        gateway_reference = (data.get("flw_ref") or transaction_row.gateway_reference or transaction_row.reference)[:180]

    transaction_row.metadata = {**transaction_row.metadata, "verify_response": verification}
    if not paid_ok or not amount_ok:
        transaction_row.status = PublicAdmissionGatewayStatus.FAILED
        transaction_row.failure_reason = (
            (verification.get("message") or verification.get("status") or "Gateway verification failed.")
            if not paid_ok
            else "Amount mismatch during gateway verification."
        )
        transaction_row.save(update_fields=["status", "failure_reason", "verified_at", "metadata", "updated_at"])
        raise ValidationError(transaction_row.failure_reason)

    transaction_row.status = PublicAdmissionGatewayStatus.PAID
    transaction_row.paid_at = timezone.now()
    transaction_row.gateway_reference = gateway_reference
    transaction_row.failure_reason = ""
    transaction_row.save(update_fields=["status", "verified_at", "paid_at", "gateway_reference", "failure_reason", "metadata", "updated_at"])

    metadata = dict(submission.metadata or {})
    metadata["application_payment_reference"] = transaction_row.reference
    metadata["application_payment_gateway_reference"] = gateway_reference
    metadata["application_payment_mode"] = PublicAdmissionPaymentMode.ONLINE
    submission.payment_status = PublicAdmissionPaymentStatus.PAID
    submission.application_fee_paid_at = transaction_row.paid_at
    submission.application_fee_amount = amount
    submission.metadata = metadata
    if submission.admissions_status == PublicAdmissionWorkflowStatus.NEW:
        submission.admissions_status = PublicAdmissionWorkflowStatus.PENDING
    submission.save(
        update_fields=[
            "payment_status",
            "application_fee_paid_at",
            "application_fee_amount",
            "admissions_status",
            "metadata",
            "updated_at",
        ]
    )

    if not metadata.get("application_receipt_sent_at"):
        email_package = _build_public_admission_receipt_email(
            submission=submission,
            transaction_row=transaction_row,
            request=request,
        )
        send_email_event(
            to_emails=_public_payment_email_targets(submission),
            subject=email_package["subject"],
            body_text=email_package["body_text"],
            body_html=email_package["body_html"],
            request=request,
            metadata={
                "event": "PUBLIC_ADMISSION_PAYMENT_RECEIPT",
                "submission_id": submission.id,
                "payment_reference": transaction_row.reference,
            },
        )
        metadata["application_receipt_sent_at"] = timezone.now().isoformat()
        submission.metadata = metadata
        submission.save(update_fields=["metadata", "updated_at"])

    return transaction_row


def _build_public_admission_pdf_context(*, submission, request):
    school_profile = SchoolProfile.load()
    public_contact = get_public_contact(school_profile=school_profile)
    snapshot = build_public_admission_snapshot(submission)
    try:
        passport_path = submission.passport_photo.path if submission.passport_photo else ""
    except Exception:
        passport_path = ""
    if passport_path and Path(passport_path).exists():
        suffix = Path(passport_path).suffix.lower()
        mime = "image/png" if suffix == ".png" else "image/jpeg"
        encoded = base64.b64encode(Path(passport_path).read_bytes()).decode("ascii")
        snapshot["student"]["passport_photo_data_uri"] = f"data:{mime};base64,{encoded}"
    else:
        snapshot["student"]["passport_photo_data_uri"] = ""
    return {
        "submission": submission,
        "admission": snapshot,
        "school_profile": school_profile,
        "public_contact": {
            **public_contact,
            "school_name": "Notre Dame Girls' Academy, Kuje-Abuja",
            "website": "www.ndgakuje.org",
            "email": "office@ndgakuje.org",
            "phone_primary": "0906 330 2377",
            "phone_secondary": "08018 932 5729",
        },
        "logo_data_uri": school_logo_data_uri(),
        "downloaded_at": timezone.now(),
        "download_url": _public_admission_download_url(request=request, submission=submission),
    }


def _public_admission_pdf_response(*, submission, request):
    pdf_bytes = render_pdf_bytes(
        template_name="pdfs/admission_application_pdf.html",
        context=_build_public_admission_pdf_context(submission=submission, request=request),
    )
    filename = f"NDGA-Admission-Form-{submission.application_fee_reference or submission.id}.pdf"
    response = HttpResponse(pdf_bytes, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response


class PublicSiteEnabledMixin:
    def dispatch(self, request, *args, **kwargs):
        if not public_site_enabled():
            raise Http404()
        if getattr(request, "portal_key", "landing") != "landing":
            raise Http404()
        return super().dispatch(request, *args, **kwargs)

    def school_profile(self):
        return SchoolProfile.load()

    def base_context(self):
        profile = self.school_profile()
        context = get_public_site_context(school_profile=profile)
        context["school_profile"] = profile
        context["public_indexable_paths"] = PUBLIC_INDEXABLE_PATHS
        context["chatbot_prompts"] = _default_chatbot_prompts()
        context["public_chatbot_payload"] = _build_public_chatbot_payload(school_profile=profile)
        return context


class PublicHomeView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/home.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_title": "Educating Girls for Life",
                "page_description": (
                    "Notre Dame Girls' Academy, Kuje-Abuja: a Catholic girls' boarding "
                    "school focused on academic formation, discipline, and care."
                ),
                "page_key": "home",
                "home_about": get_public_page("about"),
                "home_principal": get_public_page("principal"),
                "home_academics": get_public_page("academics"),
                "home_admissions": get_public_page("admissions"),
                "home_life": get_public_page("life-at-ndga"),
                "home_facilities": get_public_page("facilities"),
                "home_academic_highlights": [
                    {
                        "title": "Junior Secondary",
                        "text": "Strong foundations in English Studies, Mathematics, Intermediate Science, Digital Technologies, citizenship, and disciplined study routine.",
                        "image": context["public_images"]["computer_lab_junior"],
                        "images": [
                            context["public_images"]["computer_lab_junior"],
                            context["public_images"]["computer_lab_pair"],
                            context["public_images"]["hero_students"],
                        ],
                        "href": "/academics/junior-secondary/",
                    },
                    {
                        "title": "Senior Secondary",
                        "text": "A balanced programme preparing students for WAEC, NECO, leadership, and responsible choices beyond school.",
                        "image": context["public_images"]["science_lab"],
                        "images": [
                            context["public_images"]["science_lab"],
                            context["public_images"]["physics_lab"],
                            context["public_images"]["library"],
                        ],
                        "href": "/academics/senior-secondary/",
                    },
                    {
                        "title": "Subjects, Exams, and Support",
                        "text": "Subjects are broad, assessment is structured, and mentoring, revision, and guided follow-up support every girl's progress.",
                        "image": context["public_images"]["library"],
                        "images": [
                            context["public_images"]["library"],
                            context["public_images"]["cbt_room"],
                            context["public_images"]["computer_lab"],
                        ],
                        "href": "/academics/subjects-departments/",
                    },
                ],
                "home_support_highlights": [
                    {
                        "title": "Admissions & Screening",
                        "text": "Families can review the registration path, screening guidance, and required documents before moving ahead.",
                        "images": [
                            context["public_images"]["about_student"],
                            context["public_images"]["campus"],
                            context["public_images"]["computer_lab_pair"],
                        ],
                        "href": "/admissions/",
                    },
                    {
                        "title": "Boarding Life",
                        "text": "Boarding details explain routine, hostel care, study supervision, and the daily structure available to every girl.",
                        "images": [
                            context["public_images"]["hostel"],
                            context["public_images"]["hostel_alt"],
                            context["public_images"]["hostel_alt_two"],
                        ],
                        "href": "/hostel-boarding/",
                    },
                    {
                        "title": "Student Welfare",
                        "text": "Pastoral presence, calm routine, and supervised study help students settle, grow, and stay supported through the term.",
                        "images": [
                            context["public_images"]["assembly"],
                            context["public_images"]["assembly_alt"],
                            context["public_images"]["campus_view"],
                        ],
                        "href": "/about/school-life/",
                    },
                ],
                "home_life_highlights": [
                    {
                        "title": "Clubs & Leadership",
                        "text": "JETS, Literary and Debating, IT, Home Makers, Creative Arts, French, Young Farmers, and student leadership groups keep school life active.",
                        "images": [
                            context["public_images"]["socials"],
                            context["public_images"]["socials_alt"],
                            context["public_images"]["socials_alt_two"],
                        ],
                        "href": "/academics/co-curricular-activities/",
                    },
                    {
                        "title": "Sports & Recreation",
                        "text": "Football, basketball, volleyball, badminton, table tennis, athletics, and inter-house activities support confidence and healthy competition.",
                        "images": [
                            context["public_images"]["sports"],
                            context["public_images"]["sports_alt"],
                            context["public_images"]["sports_alt_two"],
                        ],
                        "href": "/facilities/",
                    },
                    {
                        "title": "Faith & Formation",
                        "text": "Prayer, liturgy, assemblies, retreats, and Gospel values remain part of the school day and the wider formation of students.",
                        "images": [
                            context["public_images"]["assembly"],
                            context["public_images"]["assembly_alt"],
                            context["public_images"]["campus_view"],
                        ],
                        "href": "/about/school-life/",
                    },
                ],
                "home_hallmarks": [
                    {
                        "title": "God is Good",
                        "text": "We proclaim by our lives even more than by our words that God is good.",
                    },
                    {
                        "title": "Dignity of Each Person",
                        "text": "We honour the dignity and sacredness of each person in the school community.",
                    },
                    {
                        "title": "Justice and Peace",
                        "text": "We educate for and act on behalf of justice and peace in the world.",
                    },
                    {
                        "title": "Community Service",
                        "text": "We commit ourselves to community service through generous action and shared responsibility.",
                    },
                    {
                        "title": "Gift of Diversity",
                        "text": "We embrace the gift of diversity and respect the background and worth of every child.",
                    },
                    {
                        "title": "Community",
                        "text": "We create community among those with whom we work and those we serve.",
                    },
                    {
                        "title": "Educating for Life",
                        "text": "We develop holistic learning communities which educate for life.",
                    },
                ],
                "home_testimonials": [
                    {
                        "quote": "The routines helped me settle in quickly, stay organised, and take my study time more seriously.",
                        "name": "JS1 Student",
                        "role": "",
                    },
                    {
                        "quote": "Boarding life taught me how to manage my time, stay focused, and live well with others.",
                        "name": "JS2 Student",
                        "role": "",
                    },
                    {
                        "quote": "The school environment feels calm and structured, and it keeps me focused on my goals.",
                        "name": "JS3 Student",
                        "role": "",
                    },
                    {
                        "quote": "I like that teachers notice effort, guide us closely, and expect us to keep improving.",
                        "name": "SS1 Student",
                        "role": "",
                    },
                    {
                        "quote": "The supervised study periods and daily structure make it easier to stay disciplined.",
                        "name": "SS2 Student",
                        "role": "",
                    },
                    {
                        "quote": "NDGA has helped me grow in confidence, responsibility, and the way I carry myself.",
                        "name": "SS3 Student",
                        "role": "",
                    },
                    {
                        "quote": "There is a strong sense of order here, and it makes learning feel more serious and purposeful.",
                        "name": "JS1 Student",
                        "role": "",
                    },
                    {
                        "quote": "The school encourages good conduct, respect, and better habits both in class and outside class.",
                        "name": "JS3 Student",
                        "role": "",
                    },
                    {
                        "quote": "I have become more focused because the school day is structured and teachers guide us well.",
                        "name": "SS1 Student",
                        "role": "",
                    },
                    {
                        "quote": "The environment supports prayer, discipline, and serious preparation for exams and life.",
                        "name": "SS3 Student",
                        "role": "",
                    },
                ],
                "home_gallery": get_public_gallery()[:4],
                "home_news": get_public_news()[:2],
                "home_events": get_public_events()[:3],
                "credibility_points": [
                    "Structured boarding routine and supervised student welfare.",
                    "Academic support from junior to senior secondary.",
                    "Catholic formation rooted in discipline, responsibility, and service.",
                    "Learning spaces that support science, ICT, reading, and student growth.",
                    "Child safeguarding remains part of the school's duty of care to every student.",
                ],
                "chatbot_prompts": [
                    "How do I apply?",
                    "What are the entrance exam subjects?",
                    "Tell me about boarding.",
                    "How do I contact admissions?",
                ],
            }
        )
        return context


class PublicContentPageView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/page.html"
    page_slug = ""

    def get_page(self):
        page = get_public_page(self.page_slug)
        if page is None:
            raise Http404()
        return page

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        page = self.get_page()
        context.update(self.base_context())
        context.update(
            {
                "page_key": self.page_slug,
                "page_title": page["title"],
                "page_description": page["description"],
                "public_page": page,
            }
        )
        if self.page_slug == "gallery":
            context["gallery_items"] = get_public_gallery()
        elif self.page_slug == "news":
            context["news_items"] = get_public_news()
        elif self.page_slug == "events":
            context["event_items"] = get_public_events()
        return context


class PublicGalleryCategoryView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/gallery_category.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        category = get_public_gallery_category(kwargs["slug"])
        if category is None:
            raise Http404()
        context.update(self.base_context())
        context.update(
            {
                "page_key": "gallery",
                "page_title": category["title"],
                "page_description": category["summary"],
                "gallery_category": category,
                "related_gallery_categories": [
                    row for row in get_public_gallery() if row["slug"] != category["slug"]
                ][:4],
            }
        )
        return context


class PublicNewsDetailView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/news_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        article = get_public_news_item(kwargs["slug"])
        if article is None:
            raise Http404()
        context.update(self.base_context())
        context.update(
            {
                "page_key": "news",
                "page_title": article["title"],
                "page_description": article["summary"],
                "article": article,
                "related_articles": [
                    row for row in get_public_news() if row["slug"] != article["slug"]
                ][:2],
            }
        )
        return context


class PublicContactView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/contact.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_key": "contact",
                "page_title": "Contact Us",
                "page_description": "Contact admissions, send an enquiry, or find the school location.",
                "form": kwargs.get("form") or PublicContactForm(),
                "submitted": self.request.GET.get("submitted") == "1",
                "chatbot_prompts": [
                    "Ask about admissions",
                    "Ask about boarding",
                    "Ask about portal help",
                    "Ask about directions",
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = PublicContactForm(request.POST)
        if form.is_valid():
            submission = form.save()
            _notify_public_submission(submission=submission, request=request)
            return redirect(f"{request.path}?submitted=1")
        return self.render_to_response(self.get_context_data(form=form))


class PublicRegistrationView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/registration.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(self.base_context())
        context.update(
            {
                "page_key": "registration",
                "page_title": "Online Registration",
                "page_description": "Begin the NDGA admission process with the full student, parent, and supporting document information required for the official form.",
                "form": kwargs.get("form") or PublicAdmissionRegistrationForm(),
                "form_error_summary": kwargs.get("form_error_summary", ""),
                "required_documents": [
                    "Two recent passport photographs",
                    "Birth certificate",
                    "Last school result",
                    "Medical fitness report",
                    "Online or bursary payment receipt",
                ],
                "registration_steps": [
                    "Basic details",
                    "Religious and school background",
                    "Parents and guardians",
                    "Statement and declaration",
                    "Documents and final review",
                ],
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        form = PublicAdmissionRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            submission = form.save()
            _apply_public_admission_defaults(submission)
            _notify_public_submission(submission=submission, request=request)
            _send_public_admission_processing_email(submission=submission, request=request)
            return redirect(
                f"{_public_admission_status_url(request=request, submission=submission)}&prompt=payment"
            )
        return self.render_to_response(
            self.get_context_data(
                form=form,
                form_error_summary=_public_admission_form_error_summary(form),
            )
        )


class PublicRegistrationStatusView(PublicSiteEnabledMixin, TemplateView):
    template_name = "website/registration_status.html"

    def _submission(self):
        return _resolve_public_admission_from_token(
            self.request.POST.get("access_token") or self.request.GET.get("access")
        )

    def dispatch(self, request, *args, **kwargs):
        submission = self._submission()
        if submission is None:
            return redirect("dashboard:public-registration")
        self.submission = _apply_public_admission_defaults(submission)
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        latest_payment = self.submission.payment_transactions.order_by("-created_at").first()
        provider_cards = _public_gateway_provider_cards()
        admission_snapshot = build_public_admission_snapshot(self.submission)
        default_provider = _public_default_gateway_provider()
        context.update(self.base_context())
        context.update(
            {
                "page_key": "registration",
                "page_title": "Registration Acknowledgement",
                "page_description": "Review your application code, payment status, and the next admission step.",
                "submission": self.submission,
                "admission_snapshot": admission_snapshot,
                "access_token": _public_admission_access_token(self.submission),
                "provider_cards": provider_cards,
                "gateway_enabled": any(row["enabled"] for row in provider_cards),
                "default_provider": default_provider,
                "latest_payment": latest_payment,
                "payment_status_flag": (self.request.GET.get("payment") or "").strip().lower(),
                "payment_error": (
                    (self.request.GET.get("error") or "").strip()
                    or ("Payment could not be confirmed yet." if (self.request.GET.get("payment") or "").strip().lower() == "failed" else "")
                ),
                "show_payment_prompt": (
                    (self.request.GET.get("prompt") or "").strip().lower() == "payment"
                    and self.submission.payment_status != PublicAdmissionPaymentStatus.PAID
                ),
                "payment_choice": (self.request.GET.get("choice") or "").strip().lower(),
                "application_fee_amount": self.submission.application_fee_amount,
                "init_error": kwargs.get("init_error", ""),
                "download_url": _public_admission_download_url(request=self.request, submission=self.submission),
                "public_download_allowed": self.submission.public_admission_pdf_available(),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        action = (request.POST.get("action") or "").strip().lower()
        if action == "choose_physical_payment":
            _record_public_admission_payment_preference(
                submission=self.submission,
                mode=PublicAdmissionPaymentMode.PHYSICAL,
            )
            redirect_url = _public_admission_status_url(request=request, submission=self.submission)
            return redirect(f"{redirect_url}&choice=physical")
        if action != "init_application_payment":
            return redirect(_public_admission_status_url(request=request, submission=self.submission))
        provider = (request.POST.get("provider") or _public_default_gateway_provider()).strip().upper()
        try:
            payment_row = _initialize_public_admission_payment(
                submission=self.submission,
                provider=provider,
                request=request,
            )
        except ValidationError as exc:
            return self.render_to_response(
                self.get_context_data(init_error=_public_admission_init_error_message(exc))
            )
        if payment_row.authorization_url:
            return redirect(payment_row.authorization_url)
        return self.render_to_response(
            self.get_context_data(init_error="Payment link was created without a checkout URL.")
        )


class PublicAdmissionFormDownloadView(PublicSiteEnabledMixin, View):
    def get(self, request, *args, **kwargs):
        submission = _resolve_public_admission_from_token(request.GET.get("access"))
        if submission is None:
            return redirect("dashboard:public-registration")
        submission = _apply_public_admission_defaults(submission)
        if not submission.public_admission_pdf_available():
            return redirect(
                f"{_public_admission_status_url(request=request, submission=submission)}&error=Admission+PDF+is+released+only+after+successful+online+payment."
            )
        return _public_admission_pdf_response(submission=submission, request=request)


class PublicAdmissionPaymentCallbackView(PublicSiteEnabledMixin, View):
    def get(self, request, *args, **kwargs):
        reference = (
            request.GET.get("reference")
            or request.GET.get("trxref")
            or request.GET.get("tx_ref")
            or ""
        ).strip()
        if not reference:
            return redirect("dashboard:public-registration")
        try:
            transaction_row = _verify_public_admission_payment(reference=reference, request=request)
            redirect_url = _public_admission_status_url(
                request=request,
                submission=transaction_row.submission,
            )
            return redirect(f"{redirect_url}&payment=success")
        except ValidationError as exc:
            payment_row = (
                PublicAdmissionPaymentTransaction.objects.select_related("submission")
                .filter(reference=reference)
                .first()
            )
            if payment_row is None:
                return redirect("dashboard:public-registration")
            redirect_url = _public_admission_status_url(
                request=request,
                submission=payment_row.submission,
            )
            return redirect(f"{redirect_url}&payment=failed")


class PublicLiveChatCreateView(PublicSiteEnabledMixin, View):
    def post(self, request, *args, **kwargs):
        contact_email = request.POST.get("contact_email", "").strip()
        message = request.POST.get("message", "").strip()
        if not contact_email:
            return JsonResponse(
                {
                    "ok": False,
                    "errors": {
                        "contact_email": [
                            {
                                "message": "Email address is required so management can reply to you.",
                                "code": "required",
                            }
                        ]
                    },
                },
                status=400,
            )
        category, subject = _live_chat_category_and_subject(message)
        form = PublicContactForm(
            {
                "contact_name": request.POST.get("contact_name", "").strip(),
                "contact_email": contact_email,
                "contact_phone": request.POST.get("contact_phone", "").strip(),
                "category": category,
                "subject": subject,
                "message": message,
            }
        )
        if form.is_valid():
            submission = form.save()
            _notify_public_submission(submission=submission, request=request)
            ticket_reference = f"NDGA-CHAT-{submission.id:05d}"
            _send_live_chat_confirmation(
                submission=submission,
                request=request,
                ticket_reference=ticket_reference,
            )
            return JsonResponse(
                {
                    "ok": True,
                    "message": (
                        "Ticket created. A confirmation email has been sent to you and the school "
                        "has received your message."
                    ),
                    "ticket_reference": ticket_reference,
                    "category": submission.category,
                }
            )
        return JsonResponse({"ok": False, "errors": form.errors.get_json_data()}, status=400)
