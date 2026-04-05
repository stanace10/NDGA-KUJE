from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace
from urllib.parse import quote_plus

from django import forms
from django.conf import settings
from django.contrib import messages
from django.core.mail import send_mail
from django.db.utils import OperationalError, ProgrammingError
from django.http import Http404
from django.urls import reverse
from django.views.generic import FormView, TemplateView

from apps.dashboard.models import PublicSiteSubmission, PublicSubmissionType, SchoolProfile
from apps.finance.models import FinanceInstitutionProfile
from apps.tenancy.utils import build_portal_url


DISPLAY_SCHOOL_NAME = "Notre Dame Girls' Academy, Kuje -Abuja"
DISPLAY_ADDRESS = "After Ss Simon and Jude Minor Seminary, Kuchiyako Layout, Kuje - Abuja"
DISPLAY_EMAIL = "office@ndgakuje.org"
PRIMARY_PHONE = "+234 902 940 5413"
SECONDARY_PHONE = "+234 813 341 3127"
WHATSAPP_NUMBER = "2349029405413"
MAP_QUERY = quote_plus(f"{DISPLAY_SCHOOL_NAME} {DISPLAY_ADDRESS}")
OFFICE_HOURS = (
    "Monday to Friday: 8:00 AM to 4:00 PM",
    "Saturday visits: By prior arrangement with the school",
)


def _static_asset(path: str) -> str:
    base = getattr(settings, "STATIC_URL", "/static/") or "/static/"
    if not base.endswith("/"):
        base = f"{base}/"
    return f"{base}{path.lstrip('/')}"


def _media_asset(path: str) -> str:
    base = getattr(settings, "MEDIA_URL", "/media/") or "/media/"
    if not base.endswith("/"):
        base = f"{base}/"
    return f"{base}{path.lstrip('/')}"


def _image(filename: str) -> str:
    return _static_asset(f"images/ndga/{filename}")


def _video(filename: str) -> str:
    return _media_asset(f"site/ndga/{filename}")


SITE_IMAGES = {
    "hero": _image("hero-alt-2.jpg"),
    "campus": _image("hero-alt-1.jpg"),
    "students": _image("hero-alt-3.jpg"),
    "school_life": _image("hero-main.jpg"),
    "principal": _image("principal.jpg"),
}

SITE_VIDEOS = {"hero": _video("main.mp4"), "ambient": _video("sec.mp4")}

INTENDED_CLASS_CHOICES = [(value, value) for value in ("JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3")]

CONTACT_CATEGORY_CHOICES = [
    ("Admissions enquiry", "Admissions enquiry"),
    ("Boarding enquiry", "Boarding enquiry"),
    ("Parent support", "Parent support"),
    ("General enquiry", "General enquiry"),
    ("Technical or portal support", "Technical or portal support"),
    ("Complaint or concern", "Complaint or concern"),
]

STANDARD_PAGE_PATHS = {
    "about": "about/",
    "principal": "principal/",
    "leadership": "about/leadership/",
    "mission-values": "about/mission-vision-values/",
    "school-life": "about/school-life/",
    "faith-character": "about/faith-character-formation/",
    "academics": "academics/",
    "junior-secondary": "academics/junior-secondary/",
    "senior-secondary": "academics/senior-secondary/",
    "curriculum": "academics/subjects-curriculum/",
    "ict-digital-learning": "academics/ict-digital-learning/",
    "clubs-co-curriculars": "academics/clubs-co-curriculars/",
    "admissions": "admissions/",
    "how-to-apply": "admissions/how-to-apply/",
    "screening": "admissions/screening/",
    "admission-faqs": "admissions/faqs/",
    "fees": "fees/",
    "hostel": "admissions/hostel-boarding/",
}

LIST_PAGE_PATHS = {
    "facilities": "facilities/",
    "gallery": "gallery/",
    "news": "news/",
    "events": "events/",
    "contact": "contact/",
    "registration": "admissions/registration/",
}

PUBLIC_INDEXABLE_PATHS = {"/", "/about/", "/academics/", "/admissions/", "/facilities/", "/gallery/", "/news/", "/events/", "/fees/", "/contact/", "/principal/"}


def _cards(eyebrow, title, columns, cards):
    return {"layout": "cards", "eyebrow": eyebrow, "title": title, "columns": columns, "cards": cards}


def _columns(eyebrow, title, columns):
    return {"layout": "columns", "eyebrow": eyebrow, "title": title, "columns": columns}


def _process(eyebrow, title, steps):
    return {"layout": "process", "eyebrow": eyebrow, "title": title, "steps": steps}


def _faq(eyebrow, title, items):
    return {"layout": "faq", "eyebrow": eyebrow, "title": title, "items": items}


ASSISTANT_TOPICS = [
    {"slug": "apply", "title": "How admissions starts", "prompt": "How do I apply?", "response": "Choose the class, complete the form, upload the required documents, and wait for the school's next instruction.", "url_key": "registration"},
    {"slug": "fees", "title": "Fees and payment", "prompt": "Show fees", "response": "The fees page shows the charge areas families need to plan for. The current approved schedule is confirmed directly by the school.", "url_key": "fees"},
    {"slug": "boarding", "title": "Boarding questions", "prompt": "Boarding help", "response": "NDGA is presented here as a girls' boarding school. Review hostel life, routines, welfare, and admissions guidance before submitting registration.", "url_key": "hostel"},
    {"slug": "screening", "title": "Screening dates", "prompt": "Screening dates", "response": "Screening information is released by the school when the intake schedule is ready, and registered families are contacted directly.", "url_key": "screening"},
    {"slug": "contact", "title": "Speak with the school", "prompt": "Talk to admissions", "response": f"Call {PRIMARY_PHONE} or {SECONDARY_PHONE}, send a message through the contact form, or use the portal only when the school has directed you there.", "url_key": "contact"},
]

FACILITY_ITEMS = {
    "science-laboratories": {"slug": "science-laboratories", "title": "Science Laboratories", "summary": "Practical spaces for guided experiments and careful science teaching.", "image": SITE_IMAGES["campus"], "body": ["Science lessons are strengthened when students can test, observe, and record what they learn.", "The laboratories support practical work under supervision and help students build accuracy, curiosity, and discipline in the sciences."], "highlights": ["Practical learning built into classroom science", "Guided routines for safety and focus", "A setting that encourages careful observation"]},
    "ict-cbt-lab": {"slug": "ict-cbt-lab", "title": "ICT & CBT Lab", "summary": "Digital learning spaces for computer literacy, research, and technology-supported assessment.", "image": SITE_IMAGES["students"], "body": ["Students are introduced to responsible digital skills that support study, research, and assessment.", "The ICT and CBT space helps girls grow comfortable with practical computer work while still keeping the school's culture of order and guided learning."], "highlights": ["Computer literacy with guided supervision", "Digital tools that support classroom learning", "Preparation for technology-based assessment"]},
    "library": {"slug": "library", "title": "Library", "summary": "A quiet reading environment that supports study habits and serious preparation.", "image": SITE_IMAGES["school_life"], "body": ["A strong reading culture is part of serious schooling.", "The library gives students room for reading, revision, and the quiet routines that support steady academic growth."], "highlights": ["Calm space for reading and revision", "Support for independent study", "An atmosphere that rewards focus and order"]},
    "music-arts": {"slug": "music-arts", "title": "Music & Arts", "summary": "Creative spaces where students rehearse, perform, and grow in expression with discipline.", "image": SITE_IMAGES["school_life"], "body": ["Music and the arts are part of balanced formation.", "Students are given room to rehearse, participate, and build confidence through organised creative activity."], "highlights": ["Rehearsal and performance support", "Creative growth within a structured school setting", "Confidence built through guided participation"]},
    "sports": {"slug": "sports", "title": "Sports", "summary": "Physical activity that supports fitness, teamwork, stamina, and healthy routine.", "image": SITE_IMAGES["students"], "body": ["Sports help students build resilience, discipline, and a healthy balance to academic life.", "Participation is guided in a way that supports teamwork, movement, and responsible conduct."], "highlights": ["Movement and fitness in school routine", "Teamwork and healthy competition", "A practical contribution to student wellbeing"]},
    "hostel-boarding": {"slug": "hostel-boarding", "title": "Hostel & Boarding", "summary": "A supervised boarding environment shaped by routine, study, care, and student welfare.", "image": SITE_IMAGES["campus"], "body": ["Boarding life at NDGA is built around routine, supervision, and the steady habits that support girls through school life.", "Families can expect a structured environment where study, rest, care, and conduct are all kept in view."], "highlights": ["Boarding-only school life for girls", "Structured study and daily supervision", "Care, welfare, and routine held together"]},
}

GALLERY_CATEGORY_ITEMS = {
    "academics": {"slug": "academics", "title": "Academics", "summary": "Learning moments from classrooms, revision, and practical lessons.", "image": SITE_IMAGES["school_life"]},
    "ict-science": {"slug": "ict-science", "title": "ICT & Science", "summary": "Digital learning, science practice, and focused academic work.", "image": SITE_IMAGES["students"]},
    "sports": {"slug": "sports", "title": "Sports", "summary": "Movement, teamwork, and organised student participation.", "image": SITE_IMAGES["students"]},
    "music-arts": {"slug": "music-arts", "title": "Music & Arts", "summary": "Creative practice, performances, and student expression.", "image": SITE_IMAGES["school_life"]},
    "clubs": {"slug": "clubs", "title": "Clubs & Leadership", "summary": "Service, student responsibility, and co-curricular life.", "image": SITE_IMAGES["campus"]},
    "events-ceremonies": {"slug": "events-ceremonies", "title": "Events & Ceremonies", "summary": "School gatherings, celebrations, liturgy, and shared milestones.", "image": SITE_IMAGES["campus"]},
}

GALLERY_IMAGES = [
    {"title": "Focused classroom learning", "caption": "Quiet study and close guidance remain central to school life.", "image": SITE_IMAGES["school_life"], "categories": ["academics"]},
    {"title": "Students on campus", "caption": "Life at NDGA combines discipline, belonging, and growth.", "image": SITE_IMAGES["students"], "categories": ["sports", "clubs"]},
    {"title": "Campus atmosphere", "caption": "A school environment arranged for order, safety, and learning.", "image": SITE_IMAGES["campus"], "categories": ["events-ceremonies"]},
    {"title": "ICT and digital readiness", "caption": "Digital tools are introduced in ways that support real classroom work.", "image": SITE_IMAGES["students"], "categories": ["ict-science", "academics"]},
    {"title": "Creative expression", "caption": "Music and the arts help students grow in confidence and discipline.", "image": SITE_IMAGES["school_life"], "categories": ["music-arts", "clubs"]},
    {"title": "Shared school moments", "caption": "Ceremonies, gatherings, and student participation shape community life.", "image": SITE_IMAGES["campus"], "categories": ["events-ceremonies", "clubs"]},
]

NEWS_ITEMS = {
    "admissions-guidance": {"slug": "admissions-guidance", "category": "Admissions", "meta": "Current guidance", "title": "Admissions guidance for new families", "excerpt": "Registration, class selection, required documents, and next steps are organised in one clear flow for parents and guardians.", "image": SITE_IMAGES["students"], "body": ["Families do not need to begin with the portal.", "The admissions flow starts with registration, document preparation, fee guidance, and direct communication from the school when screening or the next review stage is ready."]},
    "boarding-life": {"slug": "boarding-life", "category": "Boarding", "meta": "School life", "title": "Boarding life built on routine, study, and care", "excerpt": "Hostel life is part of the school's wider formation of girls in discipline, responsibility, and daily order.", "image": SITE_IMAGES["campus"], "body": ["Boarding is not treated as an extra service on the side.", "It is part of the school's daily rhythm, with supervision, study routines, rest, and student welfare kept in view."]},
    "faith-and-learning": {"slug": "faith-and-learning", "category": "School Life", "meta": "Catholic formation", "title": "Faith, learning, and formation held together", "excerpt": "Academic work, chapel life, guidance, and character formation all belong to the same school experience.", "image": SITE_IMAGES["school_life"], "body": ["NDGA belongs to a Catholic educational tradition that values both learning and formation.", "Students are taught in an environment where responsibility, service, reflection, and disciplined study are expected to grow together."]},
}

EVENT_ITEMS = {
    "screening-notice": {"slug": "screening-notice", "status": "Admissions", "timing": "Date released by the admissions office", "location": DISPLAY_ADDRESS, "title": "Entrance screening and class placement guidance", "excerpt": "Registered families receive the next screening instruction directly from the school once the intake stage opens.", "image": SITE_IMAGES["students"], "body": ["Entrance screening dates are issued by the school when the admissions schedule for an intake is ready.", "Parents and guardians should complete registration first, keep their contact details active, and follow the instruction sent by the admissions office."]},
    "visit-arrangement": {"slug": "visit-arrangement", "status": "School Visit", "timing": "By arrangement with the school", "location": DISPLAY_ADDRESS, "title": "Family visits and enquiry appointments", "excerpt": "Families who need help on boarding, registration, or class placement can arrange direct guidance through the school office.", "image": SITE_IMAGES["campus"], "body": ["Some questions are best handled directly with the school.", "Families who need help with boarding, documentation, registration, or portal follow-up can contact the office to request guidance."]},
    "orientation-guidance": {"slug": "orientation-guidance", "status": "Orientation", "timing": "Shared when resumption details are confirmed", "location": "NDGA campus", "title": "Orientation and resumption guidance", "excerpt": "Arrival details, resumption instructions, and school-start guidance are shared when the school is ready to release them.", "image": SITE_IMAGES["school_life"], "body": ["Resumption and orientation notices follow the real school calendar rather than placeholder dates.", "Where details are still pending, the school says so plainly and shares the next update when it is ready."]},
}

STANDARD_PAGES = {
    "about": {
        "nav_key": "about",
        "eyebrow": "About NDGA",
        "title": "A Catholic girls' boarding school shaped by learning, discipline, and care.",
        "intro": "Girls are formed for serious study, responsible living, and faith-rooted growth in a calm boarding environment.",
        "hero_image": SITE_IMAGES["campus"],
        "hero_highlights": ["Girls' boarding school", "Kuje, Abuja", "Notre Dame tradition"],
        "hero_actions": [{"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"}, {"label": "View Hostel Life", "url_key": "hostel", "variant": "secondary"}],
        "sections": [_cards("Mission, Vision & Values", "What shapes the life of the school", 3, [{"title": "Mission", "text": "To educate girls in knowledge, discipline, faith, and service through disciplined academic and boarding life."}, {"title": "Vision", "text": "To raise young women who think clearly, live responsibly, and contribute with confidence and integrity."}, {"title": "Values", "text": "Faith, discipline, responsibility, respect, service, and seriousness of purpose."}]), _columns("School Life", "Formation beyond the classroom", [{"title": "Boarding rhythm", "items": ["Study periods, chapel life, and supervision are part of daily routine.", "Girls live within a structure that teaches timekeeping and responsibility."]}, {"title": "Faith and service", "items": ["Catholic values shape relationships, reflection, and community life.", "Students are encouraged to grow in compassion, discipline, and service."]}])],
    },
    "principal": {
        "nav_key": "about",
        "eyebrow": "Principal's Welcome",
        "title": "Girls deserve a school that combines disciplined learning with care and purpose.",
        "intro": "Parents and guardians should expect a school that keeps academic work, moral formation, and boarding welfare together.",
        "hero_image": SITE_IMAGES["principal"],
        "hero_highlights": ["Clear academic expectations", "Steady guidance", "Close work with families"],
        "hero_actions": [{"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"}, {"label": "Contact the School", "url_key": "contact", "variant": "secondary"}],
        "sections": [_columns("A Welcome", "A message to families considering NDGA", [{"title": "Academic life", "items": ["Girls are expected to study well and take their work seriously.", "Learning is supported through structure, routine, and close follow-up."]}, {"title": "Boarding care", "items": ["Hostel life is supervised carefully so that study, rest, and welfare are not left to chance.", "The school works closely with families so girls are encouraged and guided well."]}]), _cards("School Direction", "What families can expect", 3, [{"title": "Academic seriousness", "text": "Clear expectations for study and conduct."}, {"title": "Character formation", "text": "Respect, discipline, and responsibility are part of education itself."}, {"title": "Boarding support", "text": "Daily routines are designed to support girls with care and order."}])],
    },
    "academics": {"nav_key": "academics", "eyebrow": "Academics", "title": "Strong teaching, guided study, and close follow-up from junior to senior secondary.", "intro": "Girls are supported through clear subject foundations, disciplined study habits, and practical learning opportunities.", "hero_image": SITE_IMAGES["students"], "hero_highlights": ["Junior secondary", "Senior secondary", "ICT and co-curricular growth"], "hero_actions": [{"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"}, {"label": "See Subjects & Curriculum", "url_key": "curriculum", "variant": "secondary"}], "sections": [_cards("Academic Pathway", "How learning is organised at NDGA", 4, [{"title": "Junior Secondary", "text": "Builds foundations in literacy, numeracy, science, and disciplined study.", "url_key": "junior-secondary"}, {"title": "Senior Secondary", "text": "Supports focused subject learning, exam preparation, and stronger responsibility.", "url_key": "senior-secondary"}, {"title": "ICT & Digital Learning", "text": "Introduces girls to practical digital tools and responsible use of technology.", "url_key": "ict-digital-learning"}, {"title": "Clubs, Music & Sports", "text": "Rounds out academic life with participation, leadership, and balance.", "url_key": "clubs-co-curriculars"}]), _columns("Academic Approach", "What families can expect from the learning culture", [{"title": "In class", "items": ["Clear instruction and attention to subject fundamentals.", "Study habits, class participation, and follow-up work are treated seriously."]}, {"title": "Beyond class", "items": ["Practical learning through science, ICT, and guided participation.", "Support for girls to grow in confidence without losing discipline."]}])]},
    "junior-secondary": {"nav_key": "academics", "eyebrow": "Junior Secondary", "title": "Junior secondary lays the habits and subject foundations girls need to grow well.", "intro": "At this stage, girls are helped to read widely, write clearly, think carefully, and develop sound study routines.", "hero_image": SITE_IMAGES["school_life"], "hero_highlights": ["Core foundations", "Study habits", "Guided growth"], "sections": [_columns("Focus Areas", "What the junior stage is meant to build", [{"title": "Academic foundations", "items": ["English Studies and communication", "Mathematics and numeracy", "Basic Science and broad curiosity"]}, {"title": "Student growth", "items": ["Timekeeping and study discipline", "Respectful conduct and responsibility", "Readiness for deeper academic work"]}])]},
    "senior-secondary": {"nav_key": "academics", "eyebrow": "Senior Secondary", "title": "Senior secondary prepares girls for focused study, examinations, and life beyond school.", "intro": "Girls are expected to deepen subject understanding, strengthen independence, and prepare seriously for the next stage.", "hero_image": SITE_IMAGES["students"], "hero_highlights": ["Focused subject study", "Exam readiness", "Leadership and maturity"], "sections": [_columns("Senior Focus", "What changes at this stage", [{"title": "Academic direction", "items": ["Deeper work in selected subject areas", "More responsibility for preparation and revision", "Guided support toward examination success"]}, {"title": "Student maturity", "items": ["Leadership and example in conduct", "Responsible use of time and school resources", "Preparation for life after secondary school"]}])]},
    "curriculum": {"nav_key": "academics", "eyebrow": "Subjects & Curriculum", "title": "The curriculum is organised to give girls a strong and balanced secondary education.", "intro": "Subject teaching is arranged clearly so that families can see both the range of learning and the seriousness of the programme.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Balanced subject groups", "Moral formation", "Practical ICT"], "sections": [_cards("Subject Areas", "The main curriculum groups", 3, [{"title": "Languages", "text": "English Studies and communication skills for steady academic growth."}, {"title": "Mathematics & Sciences", "text": "Mathematics, Basic Science, and the sciences that support analytical learning."}, {"title": "Humanities & Social Studies", "text": "Subjects that help girls understand society, culture, history, and civic responsibility."}, {"title": "ICT", "text": "Digital learning that supports classroom work and responsible technology use."}, {"title": "Religious and Moral Instruction", "text": "Faith-rooted formation within the Catholic character of the school."}, {"title": "Business and Practical Subjects", "text": "Relevant subject areas that strengthen wider readiness and skill development."}])]},
    "ict-digital-learning": {"nav_key": "academics", "eyebrow": "ICT & Digital Learning", "title": "Girls are introduced to digital tools in ways that support learning, research, and responsible use.", "intro": "Technology is used to strengthen study and practical readiness, not to distract from the school's academic discipline.", "hero_image": SITE_IMAGES["students"], "hero_highlights": ["Computer literacy", "Research skills", "CBT readiness"], "sections": [_columns("Digital Growth", "What ICT learning supports", [{"title": "Skill development", "items": ["Comfort with digital tools and basic software use.", "Practical exposure that supports research and classroom tasks."]}, {"title": "Good habits", "items": ["Responsible use of technology.", "A guided approach that keeps purpose and discipline in view."]}])]},
    "clubs-co-curriculars": {"nav_key": "academics", "eyebrow": "Clubs & Co-curriculars", "title": "Girls grow beyond the classroom through clubs, sports, music, arts, and shared school responsibilities.", "intro": "Co-curricular life is part of balanced formation and helps girls develop confidence, teamwork, and leadership.", "hero_image": SITE_IMAGES["school_life"], "hero_highlights": ["Clubs", "Music and arts", "Sports"], "sections": [_cards("Co-curricular Life", "How girls participate", 4, [{"title": "Clubs", "text": "Shared interest groups that build responsibility, service, and participation."}, {"title": "Music", "text": "Rehearsal, performance, and the confidence that grows through careful practice."}, {"title": "Arts", "text": "Creative expression guided with purpose and discipline."}, {"title": "Sports", "text": "Movement, teamwork, and healthy competition within school routine."}])]},
    "admissions": {"nav_key": "admissions", "eyebrow": "Admissions", "title": "Admissions at NDGA are clear, guided, and built around a boarding school experience for girls.", "intro": "Families can begin online, prepare the required documents, review fee areas, and wait for the school's next instruction without confusion.", "hero_image": SITE_IMAGES["hero"], "hero_highlights": ["Girls' boarding school admission", "JSS1 to SS3 entry points", "Guided screening follow-up"], "hero_actions": [{"label": "Start Registration", "url_key": "registration", "variant": "primary"}, {"label": "View Fees", "url_key": "fees", "variant": "secondary"}, {"label": "School Portal", "url_key": "portal", "variant": "ghost"}], "sections": [_cards("Why NDGA", "What families are choosing", 3, [{"title": "Structured boarding life", "text": "Daily routines, supervision, and clear expectations that support girls well."}, {"title": "Academic seriousness", "text": "Strong attention to study, subject foundations, and classroom discipline."}, {"title": "Faith and character", "text": "A Catholic environment where responsibility and service are part of school life."}]), _process("Admission Process", "How the process moves", ["Complete online registration and choose the intended class.", "Submit the applicant and guardian details with the required documents.", "Receive guidance on the current approved fee schedule and the next payment stage.", "Wait for the school to release screening or class-placement instructions.", "Admission is confirmed after review, approval, and the required payment step."]), _faq("Questions Families Ask", "Important admissions answers", [{"question": "Does admissions begin on the portal?", "answer": "No. Registration begins on the public admissions pages."}, {"question": "Is boarding treated seriously?", "answer": "Yes. Hostel life, boarding routines, and fee areas are presented as part of the school experience from the start."}, {"question": "When are screening dates shared?", "answer": "The school releases them when the intake schedule is ready and follows up directly with registered families."}])]},
    "how-to-apply": {"nav_key": "admissions", "eyebrow": "How to Apply", "title": "Application starts with a clear online form, the right documents, and direct follow-up from the school.", "intro": "Families should know what to prepare before they begin so the process moves smoothly.", "hero_image": SITE_IMAGES["students"], "hero_highlights": ["Prepare documents first", "Choose the correct class", "Expect direct follow-up"], "sections": [_process("Application Steps", "Prepare and submit in this order", ["Review the admissions page and confirm the intended class level.", "Prepare the applicant's basic details and supporting documents.", "Submit the online registration form with accurate guardian contact details.", "Wait for the school to guide the payment and screening stage.", "Follow the next instruction from the admissions office until review is complete."]), _columns("Required Documents", "What families should have ready", [{"title": "Documents", "items": ["Passport photograph", "Birth certificate", "Last school result or transcript where required"]}, {"title": "Practical notes", "items": ["Keep the guardian phone number active.", "Use an email address the family checks regularly.", "Ensure class choice and names are entered carefully."]}])]},
    "screening": {"nav_key": "admissions", "eyebrow": "Entrance Exam / Screening", "title": "Screening is arranged by the school after registration review and shared when the intake schedule is ready.", "intro": "Families should not rely on guesswork. The school communicates the next stage directly once the schedule is confirmed.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Dates shared by the school", "Follow-up after registration", "No placeholder schedules"], "sections": [_columns("How It Works", "What families should expect", [{"title": "Before screening", "items": ["Complete registration first.", "Wait for the admissions office to review and issue the next instruction."]}, {"title": "After screening", "items": ["The school completes its review and communicates the decision.", "Successful applicants receive the next confirmation and follow-up guidance."]}])]},
    "admission-faqs": {"nav_key": "admissions", "eyebrow": "Admission FAQs", "title": "Short answers to the questions families ask before registration.", "intro": "This page keeps the practical questions in one place and points families to the right next step.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Admissions", "Boarding", "Fees and portal follow-up"], "sections": [_faq("Frequently Asked", "Helpful answers", [{"question": "Does application begin on the portal?", "answer": "No. It begins with the admissions pages and the online registration form."}, {"question": "Can we review boarding information before applying?", "answer": "Yes. Hostel and boarding guidance is available before registration is submitted."}, {"question": "Will the school share the current fee schedule?", "answer": "Yes. The fees page explains the charge areas and the school confirms the current approved schedule before payment."}, {"question": "Can screening dates change?", "answer": "Yes. The school communicates the real schedule when it is ready instead of posting placeholders."}])]},
    "fees": {"nav_key": "admissions", "eyebrow": "Fees & Charges", "title": "Families should be able to see the fee areas clearly before they begin the admission process.", "intro": "The school does not hide the structure of charges. What is confirmed later is the current approved amount for the active intake or session.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Tuition and school charges", "Boarding and hostel costs", "Payment guidance before transfer"], "hero_actions": [{"label": "Start Registration", "url_key": "registration", "variant": "primary"}, {"label": "Talk to Admissions", "url_key": "contact", "variant": "secondary"}], "sections": [{"layout": "table", "eyebrow": "Fee Overview", "title": "The main charge areas families should review", "columns": ["Charge area", "What it covers", "Current approved amount"], "rows": [["Tuition / school fees", "Teaching, core school operations, and classroom learning support", "Confirmed by the admissions office for the active intake"], ["Boarding / hostel fees", "Accommodation, supervision, welfare, and hostel-related support", "Confirmed by the admissions office for the active intake"], ["Registration / admissions fee", "Application handling and admissions processing where applicable", "Shared during registration guidance"], ["Other approved charges", "Examination, activity, or other school-approved items where relevant", "Communicated when applicable"]], "note": "Amounts are not guessed here. The current approved schedule comes directly from the school before any payment is made."}, _cards("Payment Information", "What makes the fee page useful", 3, [{"title": "Before payment", "text": "Families are given the current approved schedule and the right payment instruction before they transfer anything."}, {"title": "During admissions", "text": "Fee guidance is tied to the registration and review flow, so parents know what the next step is."}, {"title": "For boarding", "text": "Boarding-related costs are treated clearly as part of the overall school process, not buried elsewhere."}])]},
    "hostel": {"nav_key": "admissions", "eyebrow": "Hostel & Boarding", "title": "Boarding life is designed to help girls live, study, and grow within a supervised and orderly environment.", "intro": "Families considering NDGA should understand boarding as part of the school's full formation of girls, not as an afterthought.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Girls' boarding environment", "Study, supervision, and welfare", "Daily routine that supports growth"], "hero_actions": [{"label": "View Fees", "url_key": "fees", "variant": "primary"}, {"label": "Start Registration", "url_key": "registration", "variant": "secondary"}], "sections": [_columns("Boarding Overview", "Why families value the boarding environment", [{"title": "Daily life", "items": ["Boarding is arranged around study, rest, supervision, and healthy daily structure.", "Girls are expected to live responsibly and keep routine well."]}, {"title": "What it supports", "items": ["Boarding supports focus, reading time, and follow-up on academic routine.", "Student welfare, order, and community life are kept in view."]}])]},
    "leadership": {"nav_key": "about", "eyebrow": "Leadership", "title": "Leadership at NDGA is built around order, welfare, and academic direction.", "intro": "The school is led in ways that keep girls safe, visible, and steadily supported through boarding and classroom life.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Academic guidance", "Boarding supervision", "Parent communication"], "sections": [_cards("School Leaders", "The people who hold school life together", 3, [{"title": "Principal", "text": "Leads the tone of the school, academic priorities, discipline, and wider community trust."}, {"title": "Academic and Boarding Leadership", "text": "Coordinates teaching quality, student routines, hostel supervision, and everyday order."}, {"title": "Admissions and Parent Support", "text": "Supports communication with families from first enquiry through registration and follow-up."}])]},
    "mission-values": {"nav_key": "about", "eyebrow": "Mission, Vision & Values", "title": "NDGA exists to educate girls with seriousness, faith, and responsibility.", "intro": "The school's direction is simple: girls should leave stronger in learning, character, and purpose.", "hero_image": SITE_IMAGES["school_life"], "hero_highlights": ["Faith-rooted education", "Formation of the whole child", "Responsible young women"], "sections": [_cards("Core Direction", "The school's guiding statements", 3, [{"title": "Mission", "text": "To educate girls in knowledge, discipline, faith, and service through sound teaching and guided boarding life."}, {"title": "Vision", "text": "To raise responsible young women who think clearly, live well, and serve with integrity."}, {"title": "Values", "text": "Faith, discipline, responsibility, service, respect, and care for others."}])]},
    "school-life": {"nav_key": "about", "eyebrow": "School Life", "title": "Boarding life at NDGA is arranged to support study, belonging, and steady growth.", "intro": "Girls live and learn in a rhythm that values order, companionship, chapel life, and responsibility.", "hero_image": SITE_IMAGES["school_life"], "hero_highlights": ["Boarding routines", "Chapel and reflection", "Clubs, arts, and sports"], "sections": [_cards("Student Experience", "What shapes everyday life", 4, [{"title": "Study", "text": "Quiet time, follow-up reading, and focused preparation remain essential."}, {"title": "Faith", "text": "Prayer, reflection, and Catholic values are part of the tone of the school."}, {"title": "Belonging", "text": "Girls learn to live and work respectfully with others in a close community."}, {"title": "Activity", "text": "Clubs, music, arts, sports, and school events build balance into student life."}])]},
    "faith-character": {"nav_key": "about", "eyebrow": "Faith & Character Formation", "title": "Faith and character are treated as part of education, not as decoration around it.", "intro": "NDGA forms girls to think well, live responsibly, and respond to others with respect and service.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Catholic environment", "Service and responsibility", "Guided moral formation"], "sections": [_cards("Visible Outcomes", "The kind of growth the school seeks", 3, [{"title": "Responsibility", "text": "Taking school work, routines, and relationships seriously."}, {"title": "Respect", "text": "Learning to speak, respond, and live with care for others."}, {"title": "Service", "text": "Growing beyond self-interest into useful participation and concern for the community."}])]},
}

STANDARD_PAGES["about"]["sections"].extend(
    [
        _cards(
            "Why Families Choose NDGA",
            "What gives the school its tone",
            3,
            [
                {
                    "title": "Catholic identity",
                    "text": "The school draws from a Notre Dame tradition that values learning, prayer, service, and the dignity of every girl.",
                },
                {
                    "title": "Boarding structure",
                    "text": "Study, rest, supervision, and student welfare are kept together in one clear daily rhythm.",
                },
                {
                    "title": "Parent trust",
                    "text": "Families should be able to see the school's expectations, contact points, and admissions path without confusion.",
                },
            ],
        ),
        _cards(
            "Leadership",
            "People and structures that keep the school steady",
            3,
            [
                {
                    "title": "Principal",
                    "text": "Sets the academic tone of the school and oversees discipline, care, and parent communication.",
                    "url_key": "principal",
                },
                {
                    "title": "School leadership",
                    "text": "Supports the running of academics, hostel routines, student welfare, and school organisation.",
                    "url_key": "leadership",
                },
                {
                    "title": "School life",
                    "text": "Shows how girls live, learn, worship, and participate in the daily rhythm of the academy.",
                    "url_key": "school-life",
                },
            ],
        ),
    ]
)
STANDARD_PAGES["about"]["cta"] = {
    "title": "See the school, the boarding environment, and the admissions path in one clear flow.",
    "links": [
        {"label": "Explore School Life", "url_key": "school-life", "variant": "primary"},
        {"label": "Start Registration", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["principal"]["sections"].append(
    _process(
        "Working With Families",
        "What parents and guardians should expect",
        [
            "A clear admissions route that starts before the portal becomes necessary.",
            "Steady communication when the school needs documents, payment, or screening follow-up.",
            "A boarding environment where learning, welfare, and conduct are guided together.",
            "Academic and pastoral attention that keeps the girl child visible and supported.",
        ],
    )
)
STANDARD_PAGES["principal"]["cta"] = {
    "title": "Move from welcome to action with admissions, boarding details, or direct contact.",
    "links": [
        {"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"},
        {"label": "Contact the School", "url_key": "contact", "variant": "secondary"},
    ],
}

STANDARD_PAGES["academics"]["sections"].extend(
    [
        _cards(
            "Subject Areas",
            "The main groups families should expect to see across the school",
            3,
            [
                {"title": "Languages and communication", "text": "English studies, reading, writing, speaking, and the habits that support sound expression."},
                {"title": "Mathematics and sciences", "text": "Numeracy, scientific thinking, practical learning, and preparation for stronger senior work."},
                {"title": "Humanities and practical studies", "text": "Social studies, arts, moral instruction, business subjects, and wider readiness for life beyond school."},
            ],
        ),
        _columns(
            "Academic Support",
            "What keeps girls progressing steadily",
            [
                {
                    "title": "Study culture",
                    "items": [
                        "Orderly classrooms and attention to the basics of each subject.",
                        "Follow-up work, reading habits, and routines that reward seriousness.",
                    ],
                },
                {
                    "title": "Practical growth",
                    "items": [
                        "Science, ICT, clubs, music, arts, and sports all help girls grow beyond books alone.",
                        "The school seeks balance without losing academic discipline.",
                    ],
                },
            ],
        ),
    ]
)
STANDARD_PAGES["academics"]["cta"] = {
    "title": "See the curriculum, choose the right class entry point, and begin admission properly.",
    "links": [
        {"label": "View Subjects", "url_key": "curriculum", "variant": "primary"},
        {"label": "Start Registration", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["junior-secondary"]["sections"].append(
    _cards(
        "What Matters Early",
        "The habits that set girls up for later success",
        3,
        [
            {"title": "Reading and writing", "text": "Students are expected to read with attention and communicate clearly."},
            {"title": "Numeracy and science", "text": "Core mathematical and scientific understanding is built carefully and steadily."},
            {"title": "Conduct and study habits", "text": "Timekeeping, organisation, respect, and care for school work are formed early."},
        ],
    )
)
STANDARD_PAGES["junior-secondary"]["cta"] = {
    "title": "Move from junior-secondary overview to admissions and registration.",
    "links": [
        {"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"},
        {"label": "Register Online", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["senior-secondary"]["sections"].append(
    _columns(
        "Senior Preparation",
        "How girls are supported at the higher level",
        [
            {
                "title": "Focused study",
                "items": [
                    "Students are guided into more serious subject concentration and stronger personal accountability.",
                    "Senior years call for revision, consistent effort, and responsible use of time.",
                ],
            },
            {
                "title": "Wider readiness",
                "items": [
                    "Girls are prepared for examination demands, leadership, and more mature decision-making.",
                    "The school expects both academic seriousness and steady character.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["senior-secondary"]["cta"] = {
    "title": "See senior academics clearly, then begin the admissions path.",
    "links": [
        {"label": "View Subjects", "url_key": "curriculum", "variant": "primary"},
        {"label": "Apply Now", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["curriculum"]["sections"].append(
    _columns(
        "Curriculum Clarity",
        "What families usually want to confirm",
        [
            {
                "title": "Across the school",
                "items": [
                    "Subject groups are arranged to give girls broad grounding with room for deeper senior work.",
                    "ICT and moral formation are treated as part of normal school life, not as extras.",
                ],
            },
            {
                "title": "With practical support",
                "items": [
                    "Laboratories, library time, computer access, clubs, and co-curricular work support the formal curriculum.",
                    "Learning is expected to show in both classroom work and everyday student responsibility.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["curriculum"]["cta"] = {
    "title": "Pair the curriculum with admissions guidance and the right class choice.",
    "links": [
        {"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"},
        {"label": "Register Online", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["ict-digital-learning"]["cta"] = {
    "title": "See how digital learning supports academics, then continue with admission guidance.",
    "links": [
        {"label": "View Academics", "url_key": "academics", "variant": "primary"},
        {"label": "Start Registration", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["clubs-co-curriculars"]["sections"].append(
    _columns(
        "Why It Matters",
        "Co-curricular life supports balanced growth",
        [
            {
                "title": "For the student",
                "items": [
                    "Girls gain confidence, teamwork, and a healthy sense of participation.",
                    "Shared responsibilities and guided activity help them grow beyond individual routine.",
                ],
            },
            {
                "title": "For the school culture",
                "items": [
                    "Clubs, sports, and creative life strengthen belonging without reducing the seriousness of study.",
                    "They help shape disciplined, visible, and well-rounded students.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["clubs-co-curriculars"]["cta"] = {
    "title": "See student life, hostel life, and admissions together before you apply.",
    "links": [
        {"label": "View School Life", "url_key": "school-life", "variant": "primary"},
        {"label": "Begin Registration", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["admissions"]["sections"].extend(
    [
        _cards(
            "Class Levels",
            "Entry points families usually ask about",
            3,
            [
                {"title": "Junior Secondary", "text": "JSS1 is the usual main entry point, with other placements subject to school review and space."},
                {"title": "Senior Secondary", "text": "SS1 is an important senior entry stage, while other classes depend on policy and available places."},
                {"title": "Placement review", "text": "Class choice is checked carefully so each applicant is guided to the right next step."},
            ],
        ),
        _columns(
            "Before You Submit",
            "The practical things families should know first",
            [
                {
                    "title": "Documents and contact details",
                    "items": [
                        "Use working guardian phone and email details so the school can follow up directly.",
                        "Prepare the applicant's basic documents before you start the form.",
                    ],
                },
                {
                    "title": "Fees and boarding",
                    "items": [
                        "Families can review the fee structure before payment is requested.",
                        "Boarding is part of the school experience from the beginning of the admissions path.",
                    ],
                },
            ],
        ),
    ]
)
STANDARD_PAGES["admissions"]["cta"] = {
    "title": "Choose the class, review fees, and start the form when you are ready.",
    "links": [
        {"label": "Start Registration", "url_key": "registration", "variant": "primary"},
        {"label": "View Fees", "url_key": "fees", "variant": "secondary"},
    ],
}

STANDARD_PAGES["how-to-apply"]["cta"] = {
    "title": "Move straight from preparation to submission.",
    "links": [
        {"label": "Open Registration", "url_key": "registration", "variant": "primary"},
        {"label": "Contact Admissions", "url_key": "contact", "variant": "secondary"},
    ],
}

STANDARD_PAGES["screening"]["sections"].append(
    _faq(
        "Screening Questions",
        "Short answers that help families avoid guesswork",
        [
            {
                "question": "Will the school post made-up dates to fill the page?",
                "answer": "No. Screening and placement details are shared only when the school is ready to issue them.",
            },
            {
                "question": "What should families do before a date is released?",
                "answer": "Complete registration, keep contact details active, and wait for the school's official instruction.",
            },
        ],
    )
)
STANDARD_PAGES["screening"]["cta"] = {
    "title": "Submit the form first, then follow the school's real screening guidance.",
    "links": [
        {"label": "Register Online", "url_key": "registration", "variant": "primary"},
        {"label": "View Admissions", "url_key": "admissions", "variant": "secondary"},
    ],
}

STANDARD_PAGES["admission-faqs"]["cta"] = {
    "title": "Questions answered. The next useful step is admissions or registration.",
    "links": [
        {"label": "Explore Admissions", "url_key": "admissions", "variant": "primary"},
        {"label": "Begin Registration", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["fees"]["sections"].append(
    _columns(
        "Fee Guidance",
        "What makes the process clearer for families",
        [
            {
                "title": "Before transfer",
                "items": [
                    "The school confirms the current approved figures before payment is made.",
                    "Families are shown the proper payment step and not left to guess what comes next.",
                ],
            },
            {
                "title": "Alongside admissions",
                "items": [
                    "Fees are part of a guided process that includes registration, review, and follow-up.",
                    "Boarding-related charges are treated clearly because hostel life is central to the school.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["fees"]["cta"] = {
    "title": "Review the fee structure, then move into registration with the right expectations.",
    "links": [
        {"label": "Start Registration", "url_key": "registration", "variant": "primary"},
        {"label": "Talk to Admissions", "url_key": "contact", "variant": "secondary"},
    ],
}

STANDARD_PAGES["hostel"]["sections"].extend(
    [
        _cards(
            "Boarding Support",
            "What families usually want to know about hostel life",
            3,
            [
                {"title": "Student welfare", "text": "Girls live within close supervision, routine, and care for their daily wellbeing."},
                {"title": "Study rhythm", "text": "Boarding helps create reading time, order, and stronger attention to school work."},
                {"title": "Shared life", "text": "Girls learn to live responsibly with others in a guided community environment."},
            ],
        ),
        _columns(
            "What Boarding Looks Like",
            "The school treats boarding as part of formation",
            [
                {
                    "title": "Daily structure",
                    "items": [
                        "Time for study, rest, prayer, meals, and supervised routine is kept in view.",
                        "Girls are helped to form habits that support steady growth and self-control.",
                    ],
                },
                {
                    "title": "Why families value it",
                    "items": [
                        "Boarding supports attention to school work and makes the wider school environment more coherent.",
                        "Parents can see that the school is thinking about welfare, not academics alone.",
                    ],
                },
            ],
        ),
    ]
)
STANDARD_PAGES["hostel"]["cta"] = {
    "title": "Pair boarding information with fees and registration before moving further.",
    "links": [
        {"label": "View Fees", "url_key": "fees", "variant": "primary"},
        {"label": "Apply Now", "url_key": "registration", "variant": "secondary"},
    ],
}

STANDARD_PAGES["leadership"]["sections"].append(
    _columns(
        "Leadership Priorities",
        "What the school leadership is expected to hold together",
        [
            {
                "title": "Inside the school",
                "items": [
                    "Academic direction, conduct, student support, and boarding order.",
                    "Clear systems that help families know where to turn when they need help.",
                ],
            },
            {
                "title": "With families",
                "items": [
                    "Communication that is practical and respectful.",
                    "A visible admissions path and follow-up process that does not depend on guesswork.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["leadership"]["cta"] = {
    "title": "Leadership matters most when it supports school life, admissions, and parent trust.",
    "links": [
        {"label": "Read the Principal's Welcome", "url_key": "principal", "variant": "primary"},
        {"label": "Contact the School", "url_key": "contact", "variant": "secondary"},
    ],
}

STANDARD_PAGES["mission-values"]["sections"].append(
    _columns(
        "How These Values Show Up",
        "The values are meant to be visible in daily school life",
        [
            {
                "title": "In the classroom",
                "items": [
                    "Girls are expected to take work seriously, pay attention, and grow in discipline.",
                    "Teaching aims at both understanding and good habits.",
                ],
            },
            {
                "title": "In boarding life",
                "items": [
                    "Routine, shared life, chapel moments, and responsibility all reflect the school's values.",
                    "Respect and service are expected in ordinary daily conduct.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["school-life"]["sections"].append(
    _columns(
        "What School Life Holds Together",
        "The everyday experience is broader than one timetable",
        [
            {
                "title": "Routine and belonging",
                "items": [
                    "Girls grow through shared routines, friendships, study periods, and organised activity.",
                    "The school environment helps them live with order and mutual respect.",
                ],
            },
            {
                "title": "Formation and participation",
                "items": [
                    "Prayer, reflection, clubs, arts, sports, and school events all support balanced growth.",
                    "Participation is encouraged in ways that remain calm, guided, and responsible.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["school-life"]["cta"] = {
    "title": "See school life, then move into hostel information or admissions.",
    "links": [
        {"label": "View Hostel & Boarding", "url_key": "hostel", "variant": "primary"},
        {"label": "Explore Admissions", "url_key": "admissions", "variant": "secondary"},
    ],
}

STANDARD_PAGES["faith-character"]["sections"].append(
    _columns(
        "Formation In Practice",
        "This part of school life should be visible, not abstract",
        [
            {
                "title": "Personal growth",
                "items": [
                    "Girls are helped to make better decisions, respond well to correction, and take responsibility seriously.",
                    "The aim is steady growth in judgement, self-control, and maturity.",
                ],
            },
            {
                "title": "Community life",
                "items": [
                    "Respect, service, and concern for others should shape the atmosphere of the hostel and classroom.",
                    "Catholic values support how girls relate, work, and grow together.",
                ],
            },
        ],
    )
)
STANDARD_PAGES["faith-character"]["cta"] = {
    "title": "See how faith and formation shape school life and admissions expectations.",
    "links": [
        {"label": "View School Life", "url_key": "school-life", "variant": "primary"},
        {"label": "Contact the School", "url_key": "contact", "variant": "secondary"},
    ],
}


class PublicContactForm(forms.Form):
    full_name = forms.CharField(max_length=180, label="Full name")
    email = forms.EmailField(required=False, label="Email address")
    phone = forms.CharField(max_length=40, required=False, label="Phone number")
    category = forms.ChoiceField(choices=CONTACT_CATEGORY_CHOICES, label="Category")
    subject = forms.CharField(max_length=180, label="Subject")
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}), label="Message")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_public_form(self.fields)

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("email") and not cleaned.get("phone"):
            raise forms.ValidationError("Provide an email address or phone number so the school can reply.")
        return cleaned

    def save(self, request):
        cleaned = self.cleaned_data
        return PublicSiteSubmission.objects.create(
            submission_type=PublicSubmissionType.CONTACT,
            contact_name=cleaned["full_name"],
            contact_email=cleaned.get("email", ""),
            contact_phone=cleaned.get("phone", ""),
            category=cleaned["category"],
            subject=cleaned["subject"],
            message=cleaned["message"],
            metadata=_request_metadata(request),
        )


class PublicAdmissionRegistrationForm(forms.Form):
    applicant_name = forms.CharField(max_length=180, label="Applicant full name")
    applicant_date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Date of birth")
    intended_class = forms.ChoiceField(choices=INTENDED_CLASS_CHOICES, label="Intended class")
    guardian_name = forms.CharField(max_length=180, label="Parent or guardian full name")
    guardian_email = forms.EmailField(required=False, label="Parent or guardian email")
    guardian_phone = forms.CharField(max_length=40, label="Parent or guardian phone")
    residential_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}), label="Residential address")
    previous_school = forms.CharField(max_length=180, required=False, label="Previous school")
    boarding_option = forms.CharField(initial="BOARDING", widget=forms.HiddenInput(), required=False)
    medical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}), label="Medical or special notes")
    passport_photo = forms.ImageField(required=False, label="Passport photograph")
    birth_certificate = forms.FileField(required=False, label="Birth certificate")
    school_result = forms.FileField(required=False, label="Last school result or transcript")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_public_form(self.fields)

    def clean(self):
        cleaned = super().clean()
        cleaned["boarding_option"] = "BOARDING"
        return cleaned

    def save(self, request):
        cleaned = self.cleaned_data
        return PublicSiteSubmission.objects.create(
            submission_type=PublicSubmissionType.ADMISSION,
            contact_name=cleaned["guardian_name"],
            contact_email=cleaned.get("guardian_email", ""),
            contact_phone=cleaned["guardian_phone"],
            applicant_name=cleaned["applicant_name"],
            applicant_date_of_birth=cleaned.get("applicant_date_of_birth"),
            intended_class=cleaned["intended_class"],
            guardian_name=cleaned["guardian_name"],
            guardian_email=cleaned.get("guardian_email", ""),
            guardian_phone=cleaned["guardian_phone"],
            residential_address=cleaned["residential_address"],
            previous_school=cleaned.get("previous_school", ""),
            boarding_option=cleaned.get("boarding_option", "BOARDING"),
            medical_notes=cleaned.get("medical_notes", ""),
            passport_photo=cleaned.get("passport_photo"),
            birth_certificate=cleaned.get("birth_certificate"),
            school_result=cleaned.get("school_result"),
            metadata=_request_metadata(request),
        )


def _style_public_form(fields):
    for field in fields.values():
        css_class = "site-form-input"
        if isinstance(field.widget, forms.Textarea):
            css_class = "site-form-input site-form-textarea"
        if isinstance(field.widget, forms.Select):
            css_class = "site-form-input site-form-select"
        if isinstance(field.widget, forms.ClearableFileInput):
            css_class = "site-form-input site-form-file"
        field.widget.attrs["class"] = f"{field.widget.attrs.get('class', '')} {css_class}".strip()
        if isinstance(field.widget, (forms.TextInput, forms.EmailInput)):
            field.widget.attrs.setdefault("placeholder", field.label)


def _request_metadata(request):
    return {"path": getattr(request, "path", "/"), "host": request.get_host(), "user_agent": request.META.get("HTTP_USER_AGENT", ""), "referrer": request.META.get("HTTP_REFERER", "")}


def _safe_school_profile():
    try:
        return SchoolProfile.load()
    except (OperationalError, ProgrammingError):
        return SimpleNamespace(school_name=DISPLAY_SCHOOL_NAME, address=DISPLAY_ADDRESS, contact_email=DISPLAY_EMAIL, contact_phone=PRIMARY_PHONE, principal_name="The Principal")


def _safe_finance_profile():
    try:
        return FinanceInstitutionProfile.load()
    except (OperationalError, ProgrammingError):
        return SimpleNamespace(school_bank_name="", school_account_name="", school_account_number="")


class PublicWebsiteBaseView(TemplateView):
    current_nav_key = "home"
    page_key = ""

    def _url(self, path: str) -> str:
        return build_portal_url(self.request, "landing", path)

    def page_url(self, key: str) -> str:
        if key == "home":
            return self._url("/")
        if key == "portal":
            return build_portal_url(self.request, "portal", "/")
        if key in STANDARD_PAGE_PATHS:
            return self._url(f"/{STANDARD_PAGE_PATHS[key]}")
        if key in LIST_PAGE_PATHS:
            return self._url(f"/{LIST_PAGE_PATHS[key]}")
        raise KeyError(key)

    def facility_url(self, slug: str) -> str:
        return self._url(f"/facilities/{slug}/")

    def gallery_category_url(self, slug: str) -> str:
        return self._url(f"/gallery/{slug}/")

    def news_url(self, slug: str) -> str:
        return self._url(f"/news/{slug}/")

    def event_url(self, slug: str) -> str:
        return self._url(f"/events/{slug}/")

    def hydrate_page(self, page):
        hydrated = deepcopy(page)
        for section in hydrated.get("sections", []):
            if section.get("layout") == "cards":
                for card in section.get("cards", []):
                    if card.get("url_key"):
                        card["url"] = self.page_url(card["url_key"])
        for action in hydrated.get("hero_actions", []):
            if action.get("url_key"):
                action["url"] = self.page_url(action["url_key"])
        if hydrated.get("cta"):
            for link in hydrated["cta"].get("links", []):
                link["url"] = self.page_url(link["url_key"])
        return hydrated

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school_profile = _safe_school_profile()
        context.update(
            {
                "page": deepcopy(STANDARD_PAGES.get(self.page_key, {"title": DISPLAY_SCHOOL_NAME, "intro": "Catholic girls' boarding school in Kuje, Abuja."})),
                "public_root_url": self.page_url("home"),
                "public_portal_url": self.page_url("portal"),
                "apply_now_url": self.page_url("registration"),
                "fees_url": self.page_url("fees"),
                "hostel_url": self.page_url("hostel"),
                "contact_url": self.page_url("contact"),
                "map_url": f"https://www.google.com/maps/search/?api=1&query={MAP_QUERY}",
                "whatsapp_url": f"https://wa.me/{WHATSAPP_NUMBER}",
                "contact_email": DISPLAY_EMAIL,
                "contact_phone": PRIMARY_PHONE,
                "secondary_phone": SECONDARY_PHONE,
                "school_address": DISPLAY_ADDRESS,
                "school_name": DISPLAY_SCHOOL_NAME,
                "principal_name": school_profile.principal_name or "The Principal",
                "office_hours": OFFICE_HOURS,
                "assistant_topics": [{**topic, "url": self.page_url(topic["url_key"])} for topic in ASSISTANT_TOPICS],
                "assistant_default_topic": ASSISTANT_TOPICS[0]["slug"],
                "nav_home_active": self.current_nav_key == "home",
                "nav_about_active": self.current_nav_key == "about",
                "nav_academics_active": self.current_nav_key == "academics",
                "nav_admissions_active": self.current_nav_key == "admissions",
                "nav_school_life_active": self.current_nav_key == "school-life",
            }
        )
        return context


class PublicHomeView(PublicWebsiteBaseView):
    template_name = "website/home.html"
    current_nav_key = "home"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {"title": f"{DISPLAY_SCHOOL_NAME} | Girls' Boarding School in Kuje Abuja", "intro": "Catholic girls' boarding school in Kuje, Abuja."}
        context["hero"] = {"eyebrow": DISPLAY_SCHOOL_NAME, "title": "A Catholic girls' secondary boarding school in Kuje, Abuja", "text": "Girls learn in a calm boarding environment where study, discipline, faith, and close care are held together every day.", "video": SITE_VIDEOS["hero"], "poster": SITE_IMAGES["hero"], "actions": [{"label": "Apply for Admission", "url": self.page_url("registration"), "variant": "primary"}, {"label": "Explore School Life", "url": self.page_url("school-life"), "variant": "secondary"}, {"label": "School Portal", "url": self.page_url("portal"), "variant": "ghost"}], "highlights": ["Girls' boarding school", "Junior and senior secondary", "Catholic learning tradition"]}
        context["hero_side"] = {"title": "What families need first", "items": [{"label": "Admissions", "value": "Registration, documents, fees, and screening guidance"}, {"label": "Boarding", "value": "Hostel life, supervision, routines, and welfare"}, {"label": "Contact", "value": f"{PRIMARY_PHONE} or {SECONDARY_PHONE}"}]}
        context["about_preview"] = {"eyebrow": "About NDGA", "title": "Educating girls for life with learning, discipline, faith, and care.", "text": "NDGA brings together serious academics, boarding structure, Catholic formation, and close attention to the growth of the girl child.", "image": SITE_IMAGES["campus"], "bullets": ["A boarding rhythm that supports study", "Faith-rooted formation and good conduct", "A school environment families can trust"], "actions": [{"label": "About NDGA", "url": self.page_url("about"), "variant": "primary"}, {"label": "Principal's Welcome", "url": self.page_url("principal"), "variant": "secondary"}]}
        context["principal_preview"] = {"eyebrow": "Principal's Welcome", "title": "Girls deserve a school that combines firm academic guidance with daily care.", "message": "At NDGA, girls are expected to study well, live responsibly, and grow in faith and character. We work closely with families to provide a boarding environment where learning and welfare remain clear priorities.", "name": context["principal_name"], "url": self.page_url("principal"), "image": SITE_IMAGES["principal"]}
        context["academic_preview"] = [{"title": "Junior Secondary", "text": "Strong foundations in literacy, numeracy, science, and disciplined study habits.", "url": self.page_url("junior-secondary")}, {"title": "Senior Secondary", "text": "Focused subject learning, examination readiness, and stronger personal responsibility.", "url": self.page_url("senior-secondary")}, {"title": "ICT & Digital Learning", "text": "Practical digital skills that support research, classwork, and CBT readiness.", "url": self.page_url("ict-digital-learning")}, {"title": "Clubs, Music & Sports", "text": "Co-curricular life that builds confidence, teamwork, and balanced student growth.", "url": self.page_url("clubs-co-curriculars")}]
        context["admissions_steps"] = ["Complete the online registration form.", "Choose the intended class and upload the required documents.", "Receive the current fee guidance from the school.", "Wait for screening or class-placement instruction.", "Move forward after school review and confirmation."]
        context["admissions_support"] = [{"title": "Fees & Charges", "text": "See the charge areas clearly before registration.", "url": self.page_url("fees")}, {"title": "Hostel & Boarding", "text": "Review boarding life, routines, and welfare expectations.", "url": self.page_url("hostel")}, {"title": "How to Apply", "text": "Prepare the right documents and know the sequence before you begin.", "url": self.page_url("how-to-apply")}]
        context["boarding_feature"] = {"eyebrow": "Boarding Life", "title": "A girls' boarding environment shaped by routine, study, and supervision.", "text": "Boarding is central to the NDGA experience. Girls live in a setting where daily order, welfare, chapel life, companionship, and academic follow-up are kept in view.", "image": SITE_IMAGES["campus"], "video": SITE_VIDEOS["ambient"], "bullets": ["Structured study and rest", "Close supervision and student welfare", "A community rhythm that builds responsibility"], "actions": [{"label": "View Hostel Life", "url": self.page_url("hostel"), "variant": "primary"}, {"label": "Contact Admissions", "url": self.page_url("contact"), "variant": "secondary"}]}
        context["facility_preview"] = [{**item, "url": self.facility_url(item["slug"])} for item in FACILITY_ITEMS.values()]
        context["gallery_preview"] = [{**item, "url": self.gallery_category_url(item["slug"])} for item in list(GALLERY_CATEGORY_ITEMS.values())[:6]]
        context["news_preview"] = [{**item, "url": self.news_url(item["slug"])} for item in NEWS_ITEMS.values()]
        context["event_preview"] = [{**item, "url": self.event_url(item["slug"])} for item in EVENT_ITEMS.values()]
        return context


class PublicStandardPageView(PublicWebsiteBaseView):
    template_name = "website/page_standard.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            page = STANDARD_PAGES[self.page_key]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = self.hydrate_page(page)
        return context


class PublicFacilitiesView(PublicWebsiteBaseView):
    template_name = "website/facilities.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {"eyebrow": "Facilities", "title": "Facilities are arranged to support serious learning, creativity, discipline, and boarding life.", "intro": "Science, ICT, reading, arts, sports, and hostel life all have spaces designed to serve the work of the school.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Labs and ICT spaces", "Library and arts", "Hostel and sports support"], "hero_actions": [{"label": "View Hostel & Boarding", "url": self.page_url("hostel"), "variant": "primary"}, {"label": "See the Gallery", "url": self.page_url("gallery"), "variant": "secondary"}]}
        context["facilities"] = [{**item, "url": self.facility_url(item["slug"])} for item in FACILITY_ITEMS.values()]
        return context


class PublicFacilityDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = FACILITY_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["summary"]}
        context["detail"] = {**item, "eyebrow": "Facility Detail", "back_url": self.page_url("facilities"), "back_label": "Back to Facilities", "related_items": [{**row, "url": self.facility_url(row["slug"])} for row in FACILITY_ITEMS.values() if row["slug"] != item["slug"]]}
        return context


class PublicGalleryView(PublicWebsiteBaseView):
    template_name = "website/gallery.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_category = self.request.GET.get("category", "").strip()
        if active_category and active_category not in GALLERY_CATEGORY_ITEMS:
            active_category = ""
        context["page"] = {"eyebrow": "Gallery", "title": "A closer look at academics, boarding life, student activity, and the NDGA environment.", "intro": "Browse the categories and open any image in the lightbox for a closer view.", "hero_image": SITE_IMAGES["school_life"], "hero_highlights": ["Academics", "Boarding life", "Events and facilities"], "hero_actions": [{"label": "Contact the School", "url": self.page_url("contact"), "variant": "primary"}, {"label": "Apply Now", "url": self.page_url("registration"), "variant": "secondary"}]}
        context["gallery_categories"] = [{**item, "url": self.gallery_category_url(item["slug"])} for item in GALLERY_CATEGORY_ITEMS.values()]
        context["gallery_images"] = [{**item, "category_titles": [GALLERY_CATEGORY_ITEMS[slug]["title"] for slug in item["categories"] if slug in GALLERY_CATEGORY_ITEMS]} for item in GALLERY_IMAGES if not active_category or active_category in item["categories"]]
        context["active_category"] = active_category
        return context


class PublicGalleryCategoryView(PublicGalleryView):
    def get_context_data(self, **kwargs):
        self.request.GET = self.request.GET.copy()
        self.request.GET["category"] = kwargs["slug"]
        context = super().get_context_data(**kwargs)
        category = GALLERY_CATEGORY_ITEMS.get(kwargs["slug"])
        if not category:
            raise Http404
        context["page"]["title"] = category["title"]
        context["page"]["intro"] = category["summary"]
        return context


class PublicNewsView(PublicWebsiteBaseView):
    template_name = "website/news.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_category = self.request.GET.get("category", "").strip()
        items = [{**item, "url": self.news_url(item["slug"])} for item in NEWS_ITEMS.values() if not selected_category or item["category"] == selected_category]
        context["page"] = {"eyebrow": "News", "title": "School updates, admissions guidance, and life around the academy.", "intro": "Notices stay useful, plain, and tied to what families and visitors actually need to know.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": ["Admissions updates", "Boarding life", "School activities"], "hero_actions": [{"label": "View Events", "url": self.page_url("events"), "variant": "primary"}, {"label": "Contact Us", "url": self.page_url("contact"), "variant": "secondary"}]}
        context["featured_story"] = items[0] if items else None
        context["news_items"] = items[1:] if len(items) > 1 else []
        context["news_categories"] = sorted({item["category"] for item in NEWS_ITEMS.values()})
        context["selected_category"] = selected_category
        return context


class PublicNewsDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = NEWS_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["excerpt"]}
        context["detail"] = {**item, "eyebrow": item["category"], "back_url": self.page_url("news"), "back_label": "Back to News", "related_items": [{**row, "url": self.news_url(row["slug"])} for row in NEWS_ITEMS.values() if row["slug"] != item["slug"]]}
        return context


class PublicEventsView(PublicWebsiteBaseView):
    template_name = "website/events.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = [{**item, "url": self.event_url(item["slug"])} for item in EVENT_ITEMS.values()]
        context["page"] = {"eyebrow": "Events", "title": "School notices, visits, screening guidance, and key moments families should watch for.", "intro": "Where a date is not yet ready, the page says so clearly instead of pretending otherwise.", "hero_image": SITE_IMAGES["hero"], "hero_highlights": ["Screening guidance", "School visits", "Orientation updates"], "hero_actions": [{"label": "Start Registration", "url": self.page_url("registration"), "variant": "primary"}, {"label": "Contact Admissions", "url": self.page_url("contact"), "variant": "secondary"}]}
        context["featured_event"] = items[0] if items else None
        context["event_items"] = items[1:] if len(items) > 1 else []
        return context


class PublicEventDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "school-life"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = EVENT_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["excerpt"]}
        context["detail"] = {**item, "eyebrow": item["status"], "back_url": self.page_url("events"), "back_label": "Back to Events", "related_items": [{**row, "url": self.event_url(row["slug"])} for row in EVENT_ITEMS.values() if row["slug"] != item["slug"]]}
        return context


class PublicContactView(PublicWebsiteBaseView, FormView):
    template_name = "website/contact.html"
    form_class = PublicContactForm
    current_nav_key = "school-life"

    def get_success_url(self):
        return reverse("dashboard:public-contact")

    def form_valid(self, form):
        submission = form.save(self.request)
        _send_public_notification(subject=f"NDGA enquiry: {submission.subject}", body=(f"Category: {submission.category}\nName: {submission.contact_name}\nEmail: {submission.contact_email}\nPhone: {submission.contact_phone}\n\n{submission.message}"))
        messages.success(self.request, "Your message has been sent. The school can now follow up with you directly.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {"eyebrow": "Contact Us", "title": "Speak with the school about admissions, boarding, fees, visits, or portal follow-up.", "intro": "Choose the right support route, send a message, or use the quick-help answers on this page.", "hero_image": SITE_IMAGES["campus"], "hero_highlights": [PRIMARY_PHONE, SECONDARY_PHONE, DISPLAY_EMAIL], "hero_actions": [{"label": "Apply Now", "url": self.page_url("registration"), "variant": "primary"}, {"label": "Get Directions", "url": context["map_url"], "variant": "secondary"}]}
        context["contact_cards"] = [{"title": "Phone", "value": PRIMARY_PHONE, "note": "Admissions and general enquiries", "url": f"tel:{PRIMARY_PHONE}"}, {"title": "Alternative line", "value": SECONDARY_PHONE, "note": "Follow-up and parent support", "url": f"tel:{SECONDARY_PHONE}"}, {"title": "Email", "value": DISPLAY_EMAIL, "note": "Formal enquiries and document follow-up", "url": f"mailto:{DISPLAY_EMAIL}"}, {"title": "Address", "value": DISPLAY_ADDRESS, "note": "Kuje, Abuja", "url": context["map_url"]}]
        context["contact_prompts"] = ["Admissions help", "Boarding questions", "Fees and charges", "Screening dates", "Portal support"]
        context["office_hours"] = OFFICE_HOURS
        context["support_routes"] = [
            {"title": "Admissions", "text": "Questions about registration, documents, class levels, and screening follow-up.", "url": self.page_url("admissions")},
            {"title": "Boarding", "text": "Hostel life, student welfare, routines, and boarding expectations.", "url": self.page_url("hostel")},
            {"title": "Fees", "text": "Fee structure, payment guidance, and what families should review before transfer.", "url": self.page_url("fees")},
        ]
        return context


class PublicRegistrationView(PublicWebsiteBaseView, FormView):
    template_name = "website/registration.html"
    form_class = PublicAdmissionRegistrationForm
    current_nav_key = "admissions"

    def get_success_url(self):
        return reverse("dashboard:public-registration")

    def form_valid(self, form):
        submission = form.save(self.request)
        _send_public_notification(subject=f"NDGA admission registration: {submission.applicant_name}", body=(f"Applicant: {submission.applicant_name}\nIntended class: {submission.intended_class}\nGuardian: {submission.guardian_name}\nGuardian email: {submission.guardian_email}\nGuardian phone: {submission.guardian_phone}\nBoarding option: {submission.boarding_option}\nPrevious school: {submission.previous_school}\n"))
        messages.success(self.request, "Registration has been submitted. The admissions team can now review it and guide you on fees, screening, and the next official step.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {"eyebrow": "Online Registration", "title": "Complete the admission form to begin the NDGA process properly.", "intro": "This form is for families applying into a girls' boarding school environment. Fill it carefully and wait for the school's next instruction after submission.", "hero_image": SITE_IMAGES["students"], "hero_highlights": ["Boarding school admission", "Class choice and documents", "School follow-up after review"], "hero_actions": [{"label": "View Fees", "url": self.page_url("fees"), "variant": "primary"}, {"label": "How to Apply", "url": self.page_url("how-to-apply"), "variant": "secondary"}]}
        context["registration_highlights"] = [{"title": "Who can apply", "text": "Families applying into junior or senior secondary classes can begin here, subject to school policy and available space."}, {"title": "Boarding only", "text": "This admissions flow is built around girls' boarding life, so hostel expectations matter from the start."}, {"title": "After submission", "text": "The admissions office reviews the form, confirms fee guidance, and issues the next instruction for screening or follow-up."}]
        context["class_levels"] = ["JSS1", "JSS2", "JSS3", "SS1", "SS2", "SS3"]
        context["required_documents"] = ["Passport photograph", "Birth certificate", "Last school result or transcript where required", "Any other document requested during review"]
        context["next_steps"] = ["The school reviews the submitted details and documents.", "Families receive guidance on the current approved fee schedule and the next payment step.", "Screening or class-placement guidance follows when the school is ready to issue it.", "Admission is confirmed only after review and the required follow-up steps are completed."]
        context["registration_support"] = [
            {"title": "Before you submit", "text": "Check names, class choice, guardian phone number, and files carefully before sending the form.", "url": self.page_url("how-to-apply")},
            {"title": "Fees and payment", "text": "Review the fee structure first. The school confirms the current approved amount before payment.", "url": self.page_url("fees")},
            {"title": "Need help now?", "text": f"Call {PRIMARY_PHONE} or {SECONDARY_PHONE} if you need guidance before submitting.", "url": self.page_url("contact")},
        ]
        return context


def _send_public_notification(*, subject: str, body: str):
    school_profile = _safe_school_profile()
    recipient = school_profile.contact_email or DISPLAY_EMAIL
    try:
        send_mail(subject=subject, message=body, from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@ndgakuje.org"), recipient_list=[recipient], fail_silently=True)
    except Exception:
        return


PUBLIC_ROUTE_NAMES = {"home": "public-home", "about": "public-about", "academics": "public-academics", "admissions": "public-admissions", "fees": "public-fees", "facilities": "public-facilities", "gallery": "public-gallery", "news": "public-news", "events": "public-events", "contact": "public-contact", "principal": "public-principal", "registration": "public-registration"}


__all__ = ["PUBLIC_INDEXABLE_PATHS", "PUBLIC_ROUTE_NAMES", "STANDARD_PAGE_PATHS", "PublicContactView", "PublicEventDetailView", "PublicEventsView", "PublicFacilitiesView", "PublicFacilityDetailView", "PublicGalleryCategoryView", "PublicGalleryView", "PublicHomeView", "PublicNewsDetailView", "PublicNewsView", "PublicRegistrationView", "PublicStandardPageView"]
