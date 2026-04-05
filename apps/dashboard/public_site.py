from __future__ import annotations

from copy import deepcopy
from types import SimpleNamespace

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


def _image(filename: str) -> str:
    static_url = getattr(settings, "STATIC_URL", "/static/") or "/static/"
    if not static_url.endswith("/"):
        static_url = f"{static_url}/"
    return f"{static_url}images/ndga/{filename}"


SITE_IMAGES = {
    "hero": _image("hero-alt-2.jpg"),
    "campus": _image("hero-alt-1.jpg"),
    "students": _image("hero-alt-3.jpg"),
    "school_life": _image("hero-main.jpg"),
    "principal": _image("principal.jpg"),
    "signature": _image("principal-signature.png"),
    "logo": _image("logo.png"),
}

INTENDED_CLASS_CHOICES = [
    ("JSS1", "JSS1"),
    ("JSS2", "JSS2"),
    ("JSS3", "JSS3"),
    ("SS1", "SS1"),
    ("SS2", "SS2"),
    ("SS3", "SS3"),
]

BOARDING_CHOICES = [
    ("DAY", "Day"),
    ("BOARDING", "Boarding"),
]

CONTACT_CATEGORY_CHOICES = [
    ("General enquiry", "General enquiry"),
    ("Admissions enquiry", "Admissions enquiry"),
    ("Complaint or concern", "Complaint or concern"),
    ("Parent support", "Parent support"),
    ("Technical or portal support", "Technical or portal support"),
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

PUBLIC_INDEXABLE_PATHS = {
    "/",
    "/about/",
    "/academics/",
    "/admissions/",
    "/facilities/",
    "/gallery/",
    "/news/",
    "/events/",
    "/fees/",
    "/contact/",
    "/principal/",
}

ASSISTANT_TOPICS = [
    {
        "slug": "apply",
        "title": "How to apply",
        "prompt": "Ask about admissions",
        "response": (
            "Begin from the admissions or registration page, choose the intended class, submit the required "
            "applicant and guardian details, then wait for the school to guide you on the next payment and screening step."
        ),
        "url_key": "registration",
    },
    {
        "slug": "fees",
        "title": "Fees and charges",
        "prompt": "Ask about fees",
        "response": (
            "The public fees page explains the charge areas families should expect. Exact current amounts should "
            "come from the school's active fee schedule so the site does not display outdated figures."
        ),
        "url_key": "fees",
    },
    {
        "slug": "screening",
        "title": "Screening and exam dates",
        "prompt": "Ask about exam dates",
        "response": (
            "Screening and entrance dates are announced by the school after registration review. If the date "
            "for your class is not yet published, use the contact page so admissions can guide you directly."
        ),
        "url_key": "screening",
    },
    {
        "slug": "hostel",
        "title": "Hostel and boarding",
        "prompt": "Ask about hostel",
        "response": (
            "Families considering boarding can review the hostel page for welfare, supervision, and boarding "
            "expectations. Final placement guidance should come from the admissions office."
        ),
        "url_key": "hostel",
    },
    {
        "slug": "portal",
        "title": "Portal support",
        "prompt": "Ask about portal help",
        "response": (
            "The school portal is a separate service for approved accounts and school operations. If you need help "
            "signing in or waiting for activation, use the contact page and choose portal support."
        ),
        "url_key": "contact",
    },
]

FACILITY_ITEMS = {
    "science-laboratories": {
        "slug": "science-laboratories",
        "title": "Science Laboratories",
        "summary": "Spaces that support practical observation, guided experiments, and careful scientific learning.",
        "image": SITE_IMAGES["campus"],
        "body": [
            "Science learning is stronger when students can move beyond theory and see concepts demonstrated with care.",
            "These spaces support practical lessons, preparation, and classroom follow-up within a supervised school setting.",
        ],
        "highlights": [
            "Practical exposure that strengthens classroom science",
            "Guided routines that support safety and concentration",
            "An environment that encourages curiosity and careful work",
        ],
    },
    "ict-cbt-lab": {
        "slug": "ict-cbt-lab",
        "title": "ICT & CBT Lab",
        "summary": "Digital learning spaces for computer literacy, guided research, and technology-supported assessment.",
        "image": SITE_IMAGES["students"],
        "body": [
            "Students are introduced to digital tools in a way that supports classroom learning and responsible use of technology.",
            "The ICT space helps build confidence with practical computer work, research tasks, and structured digital assessment routines.",
        ],
        "highlights": [
            "Computer literacy and responsible digital habits",
            "Support for practical ICT learning and research",
            "Preparation for CBT and other technology-based tasks",
        ],
    },
    "library": {
        "slug": "library",
        "title": "Library",
        "summary": "A quiet reading environment that supports study habits, reflection, and independent learning.",
        "image": SITE_IMAGES["school_life"],
        "body": [
            "A strong reading culture supports serious learning, and the library helps students build that discipline over time.",
            "It is a place for reading, follow-up study, and the quiet habits that matter in school life.",
        ],
        "highlights": [
            "A calm setting for reading and revision",
            "Support for independent study and classroom follow-up",
            "A space that reinforces order and focus",
        ],
    },
    "music-arts": {
        "slug": "music-arts",
        "title": "Music & Arts",
        "summary": "Creative spaces for rehearsal, expression, performance, and disciplined participation.",
        "image": SITE_IMAGES["school_life"],
        "body": [
            "Music and arts help students grow in confidence, expression, and teamwork.",
            "Creative activity at school works best when it is organised well and connected to the wider life of the student.",
        ],
        "highlights": [
            "Room for practice, rehearsal, and presentation",
            "Creative expression within a guided school environment",
            "Support for confidence and balanced student growth",
        ],
    },
    "sports": {
        "slug": "sports",
        "title": "Sports",
        "summary": "Activities that support fitness, teamwork, discipline, and healthy participation.",
        "image": SITE_IMAGES["students"],
        "body": [
            "Sport is part of balanced student life and supports resilience, movement, and healthy routine.",
            "It also gives students another way to learn teamwork, discipline, and responsible participation.",
        ],
        "highlights": [
            "Physical activity and healthy routine",
            "Teamwork and organised participation",
            "A practical contribution to student wellbeing",
        ],
    },
    "hostel-boarding": {
        "slug": "hostel-boarding",
        "title": "Hostel & Boarding",
        "summary": "A supervised boarding environment shaped by routine, care, study, and student welfare.",
        "image": SITE_IMAGES["campus"],
        "body": [
            "Boarding is designed to support study, rest, supervision, and responsible daily habits.",
            "Families considering hostel placement should expect a structured environment that forms part of the wider life of the school.",
        ],
        "highlights": [
            "Structured routines and student supervision",
            "A study-friendly environment with clear expectations",
            "Support for personal care, discipline, and welfare",
        ],
    },
}

GALLERY_CATEGORY_ITEMS = {
    "academics": {"slug": "academics", "title": "Academics", "summary": "Learning moments from the classroom and guided study.", "image": SITE_IMAGES["school_life"]},
    "ict-science": {"slug": "ict-science", "title": "ICT & Science", "summary": "Practical and digital learning moments.", "image": SITE_IMAGES["students"]},
    "sports": {"slug": "sports", "title": "Sports", "summary": "Movement, fitness, and student participation.", "image": SITE_IMAGES["students"]},
    "music-arts": {"slug": "music-arts", "title": "Music & Arts", "summary": "Creative expression, rehearsal, and performance.", "image": SITE_IMAGES["school_life"]},
    "clubs": {"slug": "clubs", "title": "Clubs & Leadership", "summary": "Service, participation, and student voice.", "image": SITE_IMAGES["campus"]},
    "events-ceremonies": {"slug": "events-ceremonies", "title": "Events & Ceremonies", "summary": "Shared school moments and community life.", "image": SITE_IMAGES["campus"]},
    "hostel-life": {"slug": "hostel-life", "title": "Hostel Life", "summary": "Boarding routines, care, and student welfare.", "image": SITE_IMAGES["campus"]},
    "campus-facilities": {"slug": "campus-facilities", "title": "Campus & Facilities", "summary": "The spaces that support learning and daily school life.", "image": SITE_IMAGES["campus"]},
}

GALLERY_IMAGES = [
    {"title": "Learning in session", "caption": "A look at focused classroom life at NDGA.", "image": SITE_IMAGES["school_life"], "categories": ["academics", "music-arts"]},
    {"title": "Students on campus", "caption": "Students within the school environment.", "image": SITE_IMAGES["students"], "categories": ["campus-facilities", "sports", "ict-science"]},
    {"title": "Campus life", "caption": "Shared school moments across the wider campus.", "image": SITE_IMAGES["campus"], "categories": ["events-ceremonies", "campus-facilities", "hostel-life"]},
    {"title": "School atmosphere", "caption": "A calm and supportive school setting.", "image": SITE_IMAGES["hero"], "categories": ["academics", "clubs", "events-ceremonies"]},
    {"title": "Digital readiness", "caption": "A practical learning environment that supports modern study.", "image": SITE_IMAGES["students"], "categories": ["ict-science", "academics"]},
    {"title": "Creative formation", "caption": "Student life includes opportunities beyond the formal classroom.", "image": SITE_IMAGES["school_life"], "categories": ["music-arts", "clubs"]},
]

NEWS_ITEMS = {
    "admissions-guidance": {
        "slug": "admissions-guidance",
        "category": "Admissions",
        "meta": "Current guidance",
        "title": "Admissions guidance for new families",
        "excerpt": "Families can begin with the admissions overview, review the registration requirements, and contact the school when they need direct guidance.",
        "image": SITE_IMAGES["students"],
        "body": [
            "The public website is structured to help families understand the admissions path without confusion.",
            "Parents and guardians can begin with the admissions overview, move to registration, review the expected fee areas, and contact the school if a screening date or class-level clarification is still needed.",
        ],
    },
    "portal-support": {
        "slug": "portal-support",
        "category": "Announcements",
        "meta": "Public and portal access",
        "title": "School portal access remains a separate step",
        "excerpt": "The public website and the school portal now serve different purposes so visitors can find school information without landing inside the portal first.",
        "image": SITE_IMAGES["campus"],
        "body": [
            "The public website is for school information, admissions guidance, contact, facilities, and updates.",
            "The school portal is reserved for approved users and school processes. Where activation is required, the admissions or support team will guide families after review.",
        ],
    },
    "school-life-preview": {
        "slug": "school-life-preview",
        "category": "School Life",
        "meta": "Campus update",
        "title": "A clearer look at daily school life",
        "excerpt": "The gallery and about sections now help visitors see more of the school's learning environment, routines, and student life.",
        "image": SITE_IMAGES["school_life"],
        "body": [
            "Visitors often want to understand the tone of a school before they enquire.",
            "The updated public pages place more emphasis on school life, leadership, facilities, and the overall learning environment so families can make a better-informed first impression.",
        ],
    },
}

EVENT_ITEMS = {
    "screening-notices": {
        "slug": "screening-notices",
        "status": "Admissions",
        "timing": "Date to be announced by the school",
        "location": "NDGA, Kuje Abuja",
        "title": "Entrance screening and class-placement notices",
        "excerpt": "Screening information is shared after registration review. Families should complete registration first and watch for direct guidance from the school.",
        "image": SITE_IMAGES["students"],
        "body": [
            "Screening and entrance arrangements are published by the school when the schedule for a given intake is ready.",
            "Families who have completed registration should check their contact details carefully and follow the school's next instruction when the screening date is released.",
        ],
    },
    "family-visits": {
        "slug": "family-visits",
        "status": "Enquiries",
        "timing": "Scheduled by arrangement",
        "location": "Admissions and school office",
        "title": "School visits and guided family enquiries",
        "excerpt": "Parents and guardians who need clarification on admissions, hostel life, or class placement can contact the school for direct guidance.",
        "image": SITE_IMAGES["campus"],
        "body": [
            "Not every enquiry is best handled through a website page alone.",
            "Where families need help on admissions, boarding, documentation, or portal access, the school can guide them through direct follow-up after an enquiry is submitted.",
        ],
    },
    "orientation-updates": {
        "slug": "orientation-updates",
        "status": "School Life",
        "timing": "Published as the school calendar is confirmed",
        "location": "NDGA campus",
        "title": "Orientation and school-start updates",
        "excerpt": "Orientation and resumption guidance will be shared by the school when the relevant dates are ready for release.",
        "image": SITE_IMAGES["school_life"],
        "body": [
            "Orientation, arrival guidance, and school-start notices should reflect the actual school calendar rather than placeholder dates.",
            "For that reason, the site points families toward direct updates and the contact channel whenever the final schedule has not yet been published.",
        ],
    },
}

STANDARD_PAGES = {
    "about": {
        "nav_key": "about",
        "kicker": "About Notre Dame Girls Academy",
        "title": "A girls' secondary school committed to learning, discipline, and moral formation.",
        "intro": "Notre Dame Girls Academy serves families seeking a calm and well-guided environment where girls grow in knowledge, character, faith, and responsibility.",
        "hero_image": SITE_IMAGES["campus"],
        "sections": [
            {
                "layout": "split",
                "kicker": "School Story",
                "title": "An education rooted in learning, character, and care",
                "text": [
                    "Notre Dame Girls Academy is a Catholic girls' secondary school in Kuje, Abuja, dedicated to the education of the girl child.",
                    "The school brings academics, discipline, faith, leadership, and personal growth together in one environment.",
                ],
                "image": SITE_IMAGES["students"],
                "bullets": [
                    "A calm environment with clear expectations",
                    "A school culture shaped by order, care, and responsibility",
                    "A serious approach to both learning and student formation",
                ],
            },
            {
                "layout": "cards",
                "kicker": "Mission, Vision & Values",
                "title": "The convictions that shape school life",
                "intro": "The school's identity is expressed in the way it teaches, guides, and serves families.",
                "cards": [
                    {"title": "Mission", "text": "To provide quality education that forms young girls in knowledge, character, faith, and service."},
                    {"title": "Vision", "text": "To raise confident, responsible, and well-educated young women prepared to contribute positively to society."},
                    {"title": "Values", "text": "Faith, discipline, excellence in learning, responsibility, service, respect, and leadership."},
                ],
            },
            {
                "layout": "people",
                "kicker": "Leadership",
                "title": "Leadership that keeps learning and welfare in view",
                "intro": "Families should be able to see the people and priorities behind the daily life of the school.",
                "people": [
                    {"name": "School Principal", "role": "Principal", "text": "Provides overall direction for school culture, academics, and community leadership.", "image": SITE_IMAGES["principal"]},
                    {"name": "Vice Principal", "role": "Academic and Student Support", "text": "Supports teaching quality, student follow-up, and the daily academic rhythm of the school.", "image": SITE_IMAGES["campus"]},
                    {"name": "Admissions and Pastoral Team", "role": "Family Communication", "text": "Guides admissions enquiries, student welfare coordination, and family follow-up.", "image": SITE_IMAGES["students"]},
                ],
            },
        ],
        "cta": {"title": "Learn more about school life and admissions.", "links": [{"label": "View School Life", "url_key": "school-life"}, {"label": "Explore Admissions", "url_key": "admissions"}]},
    },
    "principal": {
        "nav_key": "about",
        "kicker": "Principal's Welcome",
        "title": "A welcome rooted in discipline, care, faith, and high expectations.",
        "intro": "The principal's message should reassure parents, guide students, and reflect the tone of the school with honesty and dignity.",
        "hero_image": SITE_IMAGES["principal"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Principal Profile",
                "title": "A welcome from the Principal",
                "text": [
                    "Welcome to Notre Dame Girls Academy. Our mission is to guide young girls in learning, discipline, faith, and leadership.",
                    "We work with parents and guardians to build a school community where every student is encouraged to do her best and grow with confidence and purpose.",
                ],
                "image": SITE_IMAGES["principal"],
                "bullets": [
                    "A disciplined and supportive school environment",
                    "Close partnership with parents and guardians",
                    "A school culture built on faith, learning, and service",
                ],
            },
            {
                "layout": "cards",
                "kicker": "School Direction",
                "title": "What guides the work of the school",
                "intro": "The principal's message points to the priorities behind daily school life.",
                "cards": [
                    {"title": "Learning", "text": "Students are expected to work steadily and take their studies seriously."},
                    {"title": "Character", "text": "Discipline, conduct, and responsibility remain central to student formation."},
                    {"title": "Leadership", "text": "Girls are guided toward confidence, service, and purposeful growth."},
                ],
            },
        ],
        "cta": {"title": "Continue to admissions or speak with the school.", "links": [{"label": "Explore Admissions", "url_key": "admissions"}, {"label": "Contact the School", "url_key": "contact"}]},
    },
    "leadership": {
        "nav_key": "about",
        "kicker": "Leadership",
        "title": "A school is strongest when leadership is visible, steady, and accountable.",
        "intro": "Leadership at NDGA supports teaching, student welfare, operations, and communication with families through a shared sense of purpose.",
        "hero_image": SITE_IMAGES["campus"],
        "sections": [
            {
                "layout": "people",
                "kicker": "Leadership Areas",
                "title": "How leadership supports the school",
                "intro": "Leadership is expressed through clear roles and dependable follow-up across school life.",
                "people": [
                    {"name": "Principal", "role": "School Direction", "text": "Provides overall guidance for academics, discipline, and the school community.", "image": SITE_IMAGES["principal"]},
                    {"name": "Academic Leadership", "role": "Teaching and Standards", "text": "Supports curriculum delivery, class oversight, and academic monitoring.", "image": SITE_IMAGES["students"]},
                    {"name": "Pastoral and Operations Team", "role": "Student Welfare and Communication", "text": "Keeps welfare, school readiness, and family communication in view.", "image": SITE_IMAGES["campus"]},
                ],
            },
        ],
    },
    "mission-values": {
        "nav_key": "about",
        "kicker": "Mission, Vision & Values",
        "title": "The school's purpose is expressed in how it teaches, guides, and serves.",
        "intro": "Mission and values are not decorative statements. They shape the tone of the school and the expectations placed before students.",
        "hero_image": SITE_IMAGES["students"],
        "sections": [
            {
                "layout": "cards",
                "kicker": "Core Statements",
                "title": "The principles that support school life",
                "intro": "These statements give parents and students a clearer picture of what NDGA is building.",
                "cards": [
                    {"title": "Mission", "text": "To provide quality education that forms young girls in knowledge, character, faith, and service."},
                    {"title": "Vision", "text": "To raise confident, responsible, and well-educated young women prepared to contribute positively to society."},
                    {"title": "Faith", "text": "A school life that values worship, reverence, and moral grounding."},
                    {"title": "Discipline", "text": "Orderly habits, respectful conduct, and responsibility in daily work."},
                    {"title": "Service", "text": "Students are encouraged to contribute meaningfully to others."},
                    {"title": "Leadership", "text": "Confidence, initiative, and integrity are nurtured as part of formation."},
                ],
            },
        ],
    },
    "school-life": {
        "nav_key": "about",
        "kicker": "School Life",
        "title": "Daily school life should feel calm, active, well-guided, and purposeful.",
        "intro": "The atmosphere of a school matters to families. It shapes how students learn, participate, and carry themselves each day.",
        "hero_image": SITE_IMAGES["school_life"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Daily Rhythm",
                "title": "Order and care matter in the ordinary parts of the school day",
                "text": [
                    "School life includes routines, assemblies, movement between classes, organised activities, and the moments in between lessons.",
                    "Parents should be able to picture a school environment where girls are guided with care and clear expectations.",
                ],
                "image": SITE_IMAGES["campus"],
                "bullets": [
                    "Attendance, punctuality, and readiness are taken seriously",
                    "Students learn through participation as well as formal instruction",
                    "Shared routines help keep the school environment calm and focused",
                ],
            },
        ],
    },
    "faith-character": {
        "nav_key": "about",
        "kicker": "Faith & Character Formation",
        "title": "Faith, conduct, and personal responsibility are part of the school's formation of the student.",
        "intro": "NDGA aims to guide girls not only in what they know, but also in how they live, respond, and carry themselves.",
        "hero_image": SITE_IMAGES["principal"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Formation",
                "title": "A school environment that takes character seriously",
                "text": [
                    "Faith-rooted education at NDGA includes respect for others, disciplined conduct, and habits that support responsible living.",
                    "Students are encouraged to grow in service, honesty, self-control, and care for the community around them.",
                ],
                "image": SITE_IMAGES["students"],
                "bullets": [
                    "Respect, service, and responsibility in daily conduct",
                    "Guidance that connects values with ordinary school life",
                    "A steady school tone shaped by faith and care",
                ],
            },
        ],
    },
    "academics": {
        "nav_key": "academics",
        "kicker": "Academics",
        "title": "Supporting girls through junior and senior secondary education with strong teaching and guided learning.",
        "intro": "Our academic programme helps students build strong foundations, think clearly, communicate well, and grow in responsibility and discipline.",
        "hero_image": SITE_IMAGES["students"],
        "sections": [
            {
                "layout": "cards",
                "kicker": "Academic Pathways",
                "title": "The main parts of the academic programme",
                "intro": "Families should be able to understand the structure of learning at NDGA at a glance.",
                "cards": [
                    {"title": "Junior Secondary", "text": "Building strong foundations in literacy, numeracy, sciences, and study habits.", "url_key": "junior-secondary"},
                    {"title": "Senior Secondary", "text": "Preparing students for focused subject study, exam readiness, and responsible leadership.", "url_key": "senior-secondary"},
                    {"title": "Subjects & Curriculum", "text": "Clear subject groups that support communication, analysis, and broader readiness.", "url_key": "curriculum"},
                    {"title": "ICT & Digital Learning", "text": "Helping students grow in digital skills and responsible technology use.", "url_key": "ict-digital-learning"},
                    {"title": "Clubs & Co-curriculars", "text": "Encouraging participation, creativity, and confidence beyond the classroom.", "url_key": "clubs-co-curriculars"},
                ],
            },
        ],
    },
    "junior-secondary": {
        "nav_key": "academics",
        "kicker": "Junior Secondary",
        "title": "Junior secondary helps students build strong habits for deeper academic growth.",
        "intro": "At this level, students strengthen core skills, improve classroom discipline, and develop the confidence needed for more advanced study.",
        "hero_image": SITE_IMAGES["students"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Foundation Years",
                "title": "A steady focus on core literacy, numeracy, and guided learning",
                "text": [
                    "Junior secondary provides the structure many girls need to strengthen classroom habits and grow more confident in their studies.",
                    "The emphasis is on sound teaching, follow-up, and personal discipline.",
                ],
                "image": SITE_IMAGES["school_life"],
                "bullets": [
                    "Strong foundations in English, Mathematics, and science",
                    "Guided classroom participation and study habits",
                    "Support for confidence, order, and responsibility",
                ],
            },
        ],
    },
    "senior-secondary": {
        "nav_key": "academics",
        "kicker": "Senior Secondary",
        "title": "Senior secondary prepares students for serious subject focus, exams, and life beyond school.",
        "intro": "Students at this level are expected to work with greater maturity as they prepare for examinations, leadership opportunities, and wider next steps.",
        "hero_image": SITE_IMAGES["hero"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Focused Learning",
                "title": "Preparation for exam readiness and purposeful growth",
                "text": [
                    "Senior secondary brings stronger subject focus and a greater expectation of consistent study.",
                    "Students are guided toward careful preparation, responsible conduct, and wider readiness for what comes next.",
                ],
                "image": SITE_IMAGES["campus"],
                "bullets": [
                    "Focused study within the senior secondary structure",
                    "Preparation for examinations and broader life direction",
                    "Leadership and maturity within school life",
                ],
            },
        ],
    },
    "curriculum": {
        "nav_key": "academics",
        "kicker": "Subjects & Curriculum",
        "title": "A clear curriculum helps students know what they are learning and why it matters.",
        "intro": "NDGA supports a broad learning experience across core academic areas, practical exposure, and moral formation.",
        "hero_image": SITE_IMAGES["school_life"],
        "sections": [
            {
                "layout": "table",
                "kicker": "Subject Groups",
                "title": "Main curriculum areas",
                "columns": ["Subject Area", "What students build"],
                "rows": [
                    ["English Studies", "Communication, reading, writing, and expression"],
                    ["Mathematics", "Numeracy, logic, and problem solving"],
                    ["Basic Science / Sciences", "Scientific understanding and practical reasoning"],
                    ["Social Studies / Arts / Humanities", "Context, culture, citizenship, and interpretation"],
                    ["ICT", "Digital skills and responsible technology use"],
                    ["Religious and Moral Instruction", "Moral grounding, reflection, and values"],
                    ["Business / Commercial Subjects", "Practical knowledge where applicable at class level"],
                ],
            },
        ],
    },
    "ict-digital-learning": {
        "nav_key": "academics",
        "kicker": "ICT & Digital Learning",
        "title": "Students should learn to use technology carefully, confidently, and responsibly.",
        "intro": "Digital learning at NDGA is meant to support classroom education, research habits, and practical readiness.",
        "hero_image": SITE_IMAGES["students"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Digital Readiness",
                "title": "Technology used to support real learning",
                "text": [
                    "ICT learning should help students work more carefully, not more casually.",
                    "The aim is practical familiarity, responsible use, and steady confidence with essential digital tools.",
                ],
                "image": SITE_IMAGES["students"],
                "bullets": [
                    "Basic computer literacy and digital confidence",
                    "Research support tied to classroom learning",
                    "Responsible use of technology within a supervised environment",
                ],
            },
        ],
    },
    "clubs-co-curriculars": {
        "nav_key": "academics",
        "kicker": "Clubs & Co-curriculars",
        "title": "Growth outside the classroom matters too.",
        "intro": "Clubs, music, arts, sports, and student activities give girls more room to build confidence, creativity, and teamwork.",
        "hero_image": SITE_IMAGES["school_life"],
        "sections": [
            {
                "layout": "cards",
                "kicker": "Beyond the Classroom",
                "title": "Activities that contribute to balanced student life",
                "intro": "Co-curricular life should strengthen learning, not distract from it.",
                "cards": [
                    {"title": "Clubs", "text": "Organised participation, service, teamwork, and student contribution."},
                    {"title": "Music & Arts", "text": "Creative expression, rehearsal, discipline, and performance."},
                    {"title": "Sports", "text": "Fitness, resilience, teamwork, and healthy routine."},
                    {"title": "Leadership Activities", "text": "Confidence, responsibility, and student initiative."},
                ],
            },
        ],
    },
    "admissions": {
        "nav_key": "admissions",
        "kicker": "Admissions",
        "title": "Begin your child's journey at Notre Dame Girls Academy through a clear and guided admission process.",
        "intro": "Parents and guardians should be able to understand the process, required information, and next steps without confusion.",
        "hero_image": SITE_IMAGES["hero"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Why NDGA",
                "title": "A disciplined school environment with strong academic support and moral formation",
                "text": [
                    "Notre Dame Girls Academy offers a school culture that supports learning, responsibility, and steady personal growth.",
                    "Families looking for clarity should find the admissions pathway straightforward from first enquiry to review.",
                ],
                "image": SITE_IMAGES["campus"],
                "bullets": [
                    "Clear admissions guidance for families",
                    "Strong academic and moral expectations",
                    "A supportive environment for girls' education",
                ],
            },
            {
                "layout": "process",
                "kicker": "Admission Process",
                "title": "A practical path from registration to review",
                "steps": [
                    "Start online registration",
                    "Select the intended class level",
                    "Complete applicant and guardian details",
                    "Review fee guidance and payment instructions",
                    "Receive screening or entrance guidance from the school",
                    "Await review and admission decision",
                    "Successful applicants receive activation and next steps",
                ],
            },
            {
                "layout": "cards",
                "kicker": "Class Levels",
                "title": "Admission interest may be registered for these classes",
                "intro": "Availability should still follow the school's active intake policy.",
                "cards": [
                    {"title": "JSS1", "text": "New-entry intake"},
                    {"title": "JSS2 / JSS3", "text": "Transfer consideration where space is available"},
                    {"title": "SS1", "text": "Senior secondary entry"},
                    {"title": "SS2 / SS3", "text": "Transfer consideration where policy and space allow"},
                ],
            },
        ],
        "cta": {"title": "Start registration or review the fee guidance.", "links": [{"label": "Start Registration", "url_key": "registration"}, {"label": "View Fees", "url_key": "fees"}, {"label": "View Hostel Information", "url_key": "hostel"}, {"label": "School Portal", "url_key": "portal"}]},
    },
    "how-to-apply": {
        "nav_key": "admissions",
        "kicker": "How to Apply",
        "title": "Families should know what to prepare before beginning registration.",
        "intro": "This page brings the admissions steps together in one place so the application process feels organised and manageable.",
        "hero_image": SITE_IMAGES["students"],
        "sections": [
            {
                "layout": "process",
                "kicker": "Application Steps",
                "title": "What families should expect",
                "steps": [
                    "Complete the online registration form",
                    "Choose the intended class level",
                    "Prepare the required documents",
                    "Follow the school's payment guidance",
                    "Wait for screening or entrance instructions",
                    "Watch for further contact from the school",
                ],
            },
            {
                "layout": "cards",
                "kicker": "Required Information",
                "title": "Details families should have ready",
                "intro": "Having the right information ready makes registration easier.",
                "cards": [
                    {"title": "Applicant details", "text": "Full name, date of birth, intended class, and previous school details."},
                    {"title": "Parent or guardian details", "text": "Name, email, phone number, and residential address."},
                    {"title": "Documents", "text": "Passport photograph, birth certificate, and recent school record where required."},
                ],
            },
        ],
    },
    "screening": {
        "nav_key": "admissions",
        "kicker": "Entrance Exam / Screening",
        "title": "Screening guidance should come from the school when the actual schedule is ready.",
        "intro": "The website should help families understand the process without inventing dates that have not yet been released.",
        "hero_image": SITE_IMAGES["campus"],
        "sections": [
            {
                "layout": "split",
                "kicker": "How Screening Works",
                "title": "Registration comes first, scheduling follows review",
                "text": [
                    "Applicants should complete registration and follow the school's instructions on the next step for screening or entrance assessment.",
                    "Where dates are not yet published, families should contact the school rather than rely on placeholder notices.",
                ],
                "image": SITE_IMAGES["students"],
                "bullets": [
                    "Complete registration first",
                    "Watch for direct guidance from admissions",
                    "Use the contact page if clarification is needed",
                ],
            },
        ],
    },
    "admission-faqs": {
        "nav_key": "admissions",
        "kicker": "Admission FAQs",
        "title": "Clear answers help families move through admissions with less uncertainty.",
        "intro": "These answers stay within what the website can honestly say without inventing school policy or unpublished schedules.",
        "hero_image": SITE_IMAGES["hero"],
        "sections": [
            {
                "layout": "faq",
                "kicker": "Frequently Asked Questions",
                "title": "Helpful admissions answers",
                "items": [
                    {"question": "How do we begin the application process?", "answer": "Start from the registration page, complete the applicant and guardian details, and submit the required documents."},
                    {"question": "Can we apply for boarding?", "answer": "Yes. Families can indicate day or boarding interest during registration and review the hostel information page before submission."},
                    {"question": "Are screening dates shown on the website?", "answer": "Only when the school has released them. If no date is shown, use the contact page for guidance."},
                    {"question": "Does registration immediately activate portal access?", "answer": "No. Public registration starts the admissions process. Portal activation follows school review and approval where applicable."},
                    {"question": "Where do we see current fee information?", "answer": "The fees page explains the charge areas families should expect. The school's current schedule remains the authoritative source for exact amounts."},
                ],
            },
        ],
    },
    "fees": {
        "nav_key": "admissions",
        "kicker": "Fees & Charges",
        "title": "Review tuition, boarding, and other school charges clearly before beginning the admission process.",
        "intro": "The public site should help families understand the structure of school charges without displaying invented or outdated amounts.",
        "hero_image": SITE_IMAGES["campus"],
        "sections": [
            {
                "layout": "table",
                "kicker": "Fee Structure",
                "title": "Charge areas families should expect",
                "columns": ["Charge Area", "What it may cover", "Current amount"],
                "rows": [
                    ["Tuition / School Fees", "Classroom teaching, school operations, and core school services", "Shared through the current school fee schedule"],
                    ["Boarding / Hostel Fees", "Accommodation, supervision, and boarding support where applicable", "Shared through the current school fee schedule"],
                    ["Registration / Application", "Admissions processing and related first-step costs where applicable", "Shared through admissions guidance"],
                    ["Examination / Activity Charges", "Specific assessments or approved school charges where applicable", "Shared when relevant"],
                ],
                "note": "Exact figures should come from the school's active fee schedule so families do not rely on outdated numbers.",
            },
            {
                "layout": "cards",
                "kicker": "Payment Information",
                "title": "How payment guidance is communicated",
                "intro": "Families should be guided clearly before making payment.",
                "cards": [
                    {"title": "During admissions", "text": "Payment guidance is provided during registration review and follow-up."},
                    {"title": "Before transfer", "text": "Families should confirm the current schedule and approved payment details with the school."},
                    {"title": "Portal continuation", "text": "Where the portal is part of the next step, access follows school review and activation."},
                ],
            },
        ],
    },
    "hostel": {
        "nav_key": "admissions",
        "kicker": "Hostel & Boarding",
        "title": "Our boarding environment is designed to support study, discipline, care, and daily routine in a safe and supervised setting.",
        "intro": "Families considering boarding should be able to understand the environment, welfare expectations, and how hostel life supports learning.",
        "hero_image": SITE_IMAGES["campus"],
        "sections": [
            {
                "layout": "split",
                "kicker": "Boarding Overview",
                "title": "A boarding environment shaped by routine, care, and responsibility",
                "text": [
                    "Boarding students are supported through structured supervision, daily routines, and an environment that encourages learning and personal responsibility.",
                    "Hostel life should feel organised, calm, and clearly guided.",
                ],
                "image": SITE_IMAGES["campus"],
                "bullets": [
                    "Supervised routines for study, rest, and welfare",
                    "A structured environment within the wider school culture",
                    "Clear expectations for conduct and daily living",
                ],
            },
        ],
        "cta": {"title": "Review fee guidance or begin the application process.", "links": [{"label": "View Fees", "url_key": "fees"}, {"label": "Apply Now", "url_key": "registration"}]},
    },
}


class PublicContactForm(forms.Form):
    full_name = forms.CharField(max_length=180, label="Full name")
    email = forms.EmailField(required=False, label="Email address")
    phone = forms.CharField(max_length=40, required=False, label="Phone number")
    category = forms.ChoiceField(choices=CONTACT_CATEGORY_CHOICES)
    subject = forms.CharField(max_length=180)
    message = forms.CharField(widget=forms.Textarea(attrs={"rows": 5}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_public_form(self.fields)

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
    applicant_date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}), label="Applicant date of birth")
    intended_class = forms.ChoiceField(choices=INTENDED_CLASS_CHOICES)
    guardian_name = forms.CharField(max_length=180, label="Parent or guardian full name")
    guardian_email = forms.EmailField(required=False, label="Parent or guardian email")
    guardian_phone = forms.CharField(max_length=40, label="Parent or guardian phone")
    residential_address = forms.CharField(widget=forms.Textarea(attrs={"rows": 3}))
    previous_school = forms.CharField(max_length=180, required=False)
    boarding_option = forms.ChoiceField(choices=BOARDING_CHOICES)
    medical_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    passport_photo = forms.ImageField(required=False)
    birth_certificate = forms.FileField(required=False)
    school_result = forms.FileField(required=False, label="Last school result or transcript")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        _style_public_form(self.fields)

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
            boarding_option=cleaned["boarding_option"],
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
        existing = field.widget.attrs.get("class", "")
        field.widget.attrs["class"] = f"{existing} {css_class}".strip()
        if isinstance(field.widget, (forms.TextInput, forms.EmailInput)):
            field.widget.attrs.setdefault("placeholder", field.label)


def _request_metadata(request):
    return {
        "path": getattr(request, "path", "/"),
        "host": request.get_host(),
        "user_agent": request.META.get("HTTP_USER_AGENT", ""),
        "referrer": request.META.get("HTTP_REFERER", ""),
    }


def _safe_school_profile():
    try:
        return SchoolProfile.load()
    except (OperationalError, ProgrammingError):
        return SimpleNamespace(
            school_name="Notre Dame Girls Academy",
            address="Kuje, Abuja",
            contact_email="office@ndgakuje.org",
            contact_phone="",
            principal_name="The Principal",
        )


def _safe_finance_profile():
    try:
        return FinanceInstitutionProfile.load()
    except (OperationalError, ProgrammingError):
        return SimpleNamespace(
            school_bank_name="",
            school_account_name="",
            school_account_number="",
        )


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

    def _assistant_topics(self):
        rows = []
        for item in ASSISTANT_TOPICS:
            row = dict(item)
            row["url"] = self.page_url(item["url_key"])
            rows.append(row)
        return rows

    def _page_meta(self):
        if self.page_key and self.page_key in STANDARD_PAGES:
            return deepcopy(STANDARD_PAGES[self.page_key])
        return {"title": "Notre Dame Girls Academy", "intro": "Official public website for Notre Dame Girls Academy, Kuje Abuja."}

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        school_profile = _safe_school_profile()
        finance_profile = _safe_finance_profile()
        context.update(
            {
                "page": self._page_meta(),
                "public_root_url": self.page_url("home"),
                "public_portal_url": self.page_url("portal"),
                "apply_now_url": self.page_url("registration"),
                "contact_email": school_profile.contact_email or "office@ndgakuje.org",
                "contact_phone": school_profile.contact_phone or "Admissions follow-up available by request",
                "school_address": school_profile.address or "Kuje, Abuja",
                "school_name": school_profile.school_name or "Notre Dame Girls Academy",
                "principal_name": school_profile.principal_name or "The Principal",
                "finance_profile": finance_profile,
                "assistant_topics": self._assistant_topics(),
                "nav_about_active": self.current_nav_key == "about",
                "nav_academics_active": self.current_nav_key == "academics",
                "nav_admissions_active": self.current_nav_key == "admissions",
                "nav_facilities_active": self.current_nav_key == "facilities",
                "nav_gallery_active": self.current_nav_key == "gallery",
                "nav_news_events_active": self.current_nav_key == "news-events",
                "nav_contact_active": self.current_nav_key == "contact",
            }
        )
        return context

    def hydrate_page(self, page):
        hydrated = deepcopy(page)
        for section in hydrated.get("sections", []):
            if section.get("layout") == "cards":
                for card in section.get("cards", []):
                    if card.get("url_key"):
                        card["url"] = self.page_url(card["url_key"])
        if hydrated.get("cta"):
            for link in hydrated["cta"].get("links", []):
                link["url"] = self.page_url(link["url_key"])
        return hydrated


class PublicHomeView(PublicWebsiteBaseView):
    template_name = "website/home.html"
    current_nav_key = "home"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {
            "title": "Notre Dame Girls Academy | Kuje Abuja",
            "intro": "Official school website for Notre Dame Girls Academy, Kuje Abuja. Learn about academics, admissions, facilities, school life, and contact guidance.",
        }
        context["hero"] = {
            "eyebrow": "Welcome to Notre Dame Girls Academy",
            "title": "A Catholic girls' secondary school in Kuje, Abuja",
            "text": "We provide a disciplined and supportive environment where girls grow in knowledge, character, faith, and confidence.",
            "image": SITE_IMAGES["hero"],
        }
        context["about_preview"] = {
            "title": "An education rooted in learning, character, and care",
            "text": "Notre Dame Girls Academy is committed to the education of the girl child through sound academics, moral formation, and a safe school environment that helps every student grow and succeed.",
            "image": SITE_IMAGES["campus"],
            "about_url": self.page_url("about"),
            "life_url": self.page_url("school-life"),
        }
        context["principal_preview"] = {
            "title": "A welcome from the Principal",
            "message": "Welcome to Notre Dame Girls Academy. Our mission is to guide young girls in learning, discipline, faith, and leadership. We work with parents and guardians to build a school community where every student is encouraged to do her best and grow with confidence and purpose.",
            "url": self.page_url("principal"),
            "image": SITE_IMAGES["principal"],
            "signature": SITE_IMAGES["signature"],
        }
        context["academic_preview"] = [
            {"title": "Junior Secondary", "text": "Building strong foundations in literacy, numeracy, science, and responsible study habits.", "url": self.page_url("junior-secondary")},
            {"title": "Senior Secondary", "text": "Preparing students for academic excellence, leadership, and life beyond school.", "url": self.page_url("senior-secondary")},
            {"title": "ICT & Digital Learning", "text": "Helping students grow in digital skills, research, and responsible use of technology.", "url": self.page_url("ict-digital-learning")},
            {"title": "Clubs & Co-curriculars", "text": "Encouraging creativity, teamwork, confidence, and student participation through school activities.", "url": self.page_url("clubs-co-curriculars")},
        ]
        context["admissions_steps"] = [
            "Register online",
            "Choose class level",
            "Review fees and payment guidance",
            "Receive screening or exam schedule",
            "Await review and admission decision",
        ]
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
        hydrated = self.hydrate_page(page)
        context["page"] = hydrated
        context["nav_about_active"] = hydrated["nav_key"] == "about"
        context["nav_academics_active"] = hydrated["nav_key"] == "academics"
        context["nav_admissions_active"] = hydrated["nav_key"] == "admissions"
        return context


class PublicFacilitiesView(PublicWebsiteBaseView):
    template_name = "website/facilities.html"
    current_nav_key = "facilities"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {
            "kicker": "Facilities",
            "title": "Spaces designed to support learning, creativity, discipline, and student life.",
            "intro": "Notre Dame Girls Academy provides facilities that support practical learning, digital education, reading culture, creative development, sports, and student welfare.",
            "hero_image": SITE_IMAGES["campus"],
        }
        context["facilities"] = [{**item, "url": self.facility_url(item["slug"])} for item in FACILITY_ITEMS.values()]
        return context


class PublicFacilityDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "facilities"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = FACILITY_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["summary"]}
        context["detail"] = {
            **item,
            "kicker": "Facility Detail",
            "back_url": self.page_url("facilities"),
            "back_label": "Back to Facilities",
            "related_items": [{**row, "url": self.facility_url(row["slug"])} for row in FACILITY_ITEMS.values() if row["slug"] != item["slug"]],
        }
        return context


class PublicGalleryView(PublicWebsiteBaseView):
    template_name = "website/gallery.html"
    current_nav_key = "gallery"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        active_category = self.request.GET.get("category", "").strip()
        if active_category and active_category not in GALLERY_CATEGORY_ITEMS:
            active_category = ""
        context["page"] = {
            "kicker": "Gallery",
            "title": "A closer look at academics, school life, events, and student activities at NDGA.",
            "intro": "Browse the image categories and open each image in a clean lightbox view.",
            "hero_image": SITE_IMAGES["school_life"],
        }
        context["gallery_categories"] = [{**item, "url": self.gallery_category_url(item["slug"])} for item in GALLERY_CATEGORY_ITEMS.values()]
        context["gallery_images"] = [
            {
                **item,
                "category_titles": [GALLERY_CATEGORY_ITEMS[slug]["title"] for slug in item["categories"] if slug in GALLERY_CATEGORY_ITEMS],
            }
            for item in GALLERY_IMAGES
            if not active_category or active_category in item["categories"]
        ]
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
    current_nav_key = "news-events"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        selected_category = self.request.GET.get("category", "").strip()
        items = [
            {**item, "url": self.news_url(item["slug"])}
            for item in NEWS_ITEMS.values()
            if not selected_category or item["category"] == selected_category
        ]
        context["page"] = {
            "kicker": "News",
            "title": "Updates, announcements, achievements, and stories from school life.",
            "intro": "News content on the public site should stay useful, clear, and tied to what the school is ready to share.",
            "hero_image": SITE_IMAGES["campus"],
        }
        context["featured_story"] = items[0] if items else None
        context["news_items"] = items[1:] if len(items) > 1 else []
        context["news_categories"] = sorted({item["category"] for item in NEWS_ITEMS.values()})
        context["selected_category"] = selected_category
        return context


class PublicNewsDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "news-events"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = NEWS_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["excerpt"]}
        context["detail"] = {
            **item,
            "kicker": item["category"],
            "back_url": self.page_url("news"),
            "back_label": "Back to News",
            "related_items": [{**row, "url": self.news_url(row["slug"])} for row in NEWS_ITEMS.values() if row["slug"] != item["slug"]],
        }
        return context


class PublicEventsView(PublicWebsiteBaseView):
    template_name = "website/events.html"
    current_nav_key = "news-events"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        items = [{**item, "url": self.event_url(item["slug"])} for item in EVENT_ITEMS.values()]
        context["page"] = {
            "kicker": "Events",
            "title": "School activities, important dates, ceremonies, competitions, and student events.",
            "intro": "Where specific dates are not yet published, the site says so clearly instead of displaying placeholders as fact.",
            "hero_image": SITE_IMAGES["hero"],
        }
        context["featured_event"] = items[0] if items else None
        context["event_items"] = items[1:] if len(items) > 1 else []
        return context


class PublicEventDetailView(PublicWebsiteBaseView):
    template_name = "website/detail.html"
    current_nav_key = "news-events"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        try:
            item = EVENT_ITEMS[kwargs["slug"]]
        except KeyError as exc:
            raise Http404 from exc
        context["page"] = {"title": item["title"], "intro": item["excerpt"]}
        context["detail"] = {
            **item,
            "kicker": item["status"],
            "back_url": self.page_url("events"),
            "back_label": "Back to Events",
            "related_items": [{**row, "url": self.event_url(row["slug"])} for row in EVENT_ITEMS.values() if row["slug"] != item["slug"]],
        }
        return context


class PublicContactView(PublicWebsiteBaseView, FormView):
    template_name = "website/contact.html"
    form_class = PublicContactForm
    current_nav_key = "contact"

    def get_success_url(self):
        return reverse("dashboard:public-contact")

    def form_valid(self, form):
        submission = form.save(self.request)
        _send_public_notification(
            subject=f"NDGA website enquiry: {submission.subject}",
            body=(
                f"Category: {submission.category}\n"
                f"Name: {submission.contact_name}\n"
                f"Email: {submission.contact_email}\n"
                f"Phone: {submission.contact_phone}\n\n"
                f"{submission.message}"
            ),
        )
        messages.success(self.request, "Your enquiry has been sent. The school can now follow up with you directly.")
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {
            "kicker": "Contact Us",
            "title": "We are here to help with admissions, enquiries, and general school information.",
            "intro": "Send a message to the school office, choose the right support category, or use the quick-help topics below.",
            "hero_image": SITE_IMAGES["campus"],
        }
        context["contact_cards"] = [
            {"title": "Email", "value": context["contact_email"]},
            {"title": "Phone", "value": context["contact_phone"]},
            {"title": "Address", "value": context["school_address"]},
            {"title": "Admissions Office", "value": "Use admissions enquiry for registration, screening, fees, or hostel guidance."},
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
        _send_public_notification(
            subject=f"NDGA admission registration: {submission.applicant_name}",
            body=(
                f"Applicant: {submission.applicant_name}\n"
                f"Intended class: {submission.intended_class}\n"
                f"Guardian: {submission.guardian_name}\n"
                f"Guardian email: {submission.guardian_email}\n"
                f"Guardian phone: {submission.guardian_phone}\n"
                f"Boarding option: {submission.boarding_option}\n"
                f"Previous school: {submission.previous_school}\n"
            ),
        )
        messages.success(
            self.request,
            "Registration has been submitted. The admissions team can now review it and guide you on screening, payment, or the next official step.",
        )
        return super().form_valid(form)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page"] = {
            "kicker": "Online Registration",
            "title": "Complete the application form to begin the admission process.",
            "intro": "Parents and guardians can register applicants online by completing the required details, selecting the intended class, and following the next steps for school guidance.",
            "hero_image": SITE_IMAGES["students"],
        }
        context["required_documents"] = [
            "Passport photograph",
            "Birth certificate",
            "Last school result or transcript where required",
            "Any additional document requested by the school",
        ]
        context["next_steps"] = [
            "The school reviews the submitted details and documents.",
            "Families receive guidance on the relevant payment and screening step.",
            "Applications remain under review until the admission process is completed.",
        ]
        return context


def _send_public_notification(*, subject: str, body: str):
    school_profile = _safe_school_profile()
    recipient = school_profile.contact_email or "office@ndgakuje.org"
    try:
        send_mail(
            subject=subject,
            message=body,
            from_email=getattr(settings, "DEFAULT_FROM_EMAIL", "no-reply@ndgakuje.org"),
            recipient_list=[recipient],
            fail_silently=True,
        )
    except Exception:
        return


PUBLIC_ROUTE_NAMES = {
    "home": "public-home",
    "about": "public-about",
    "academics": "public-academics",
    "admissions": "public-admissions",
    "fees": "public-fees",
    "facilities": "public-facilities",
    "gallery": "public-gallery",
    "news": "public-news",
    "events": "public-events",
    "contact": "public-contact",
    "principal": "public-principal",
    "registration": "public-registration",
}


__all__ = [
    "PUBLIC_INDEXABLE_PATHS",
    "PUBLIC_ROUTE_NAMES",
    "STANDARD_PAGE_PATHS",
    "PublicContactView",
    "PublicEventDetailView",
    "PublicEventsView",
    "PublicFacilitiesView",
    "PublicFacilityDetailView",
    "PublicGalleryCategoryView",
    "PublicGalleryView",
    "PublicHomeView",
    "PublicNewsDetailView",
    "PublicNewsView",
    "PublicRegistrationView",
    "PublicStandardPageView",
]
