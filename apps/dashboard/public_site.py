from __future__ import annotations

from copy import deepcopy


PUBLIC_IMAGE = {
    "hero": "images/ndga/hero-alt-3.jpg",
    "hero_alt": "images/ndga/hero-main.jpg",
    "hero_music": "images/ndga/hero-alt-1.jpg",
    "hero_students": "images/ndga/hero-alt-2.jpg",
    "principal": "images/ndga/principal.jpg",
    "logo": "images/ndga/logo.png",
    "campus": "images/public/campus-entrance.jpeg",
    "computer_lab": "images/public/computer-lab-senior.jpg",
    "hostel": "images/public/hostel-life.jpg",
    "sports": "images/public/sports-court.jpg",
    "science_lab": "images/public/biology-lab.jpg",
    "library": "images/public/library.jpg",
    "assembly": "images/public/assembly.jpg",
    "campus_block": "images/public/campus-block.jpg",
    "socials": "images/public/socials.jpg",
}

PUBLIC_CONTACT = {
    "school_name": "Notre Dame Girls' Academy, Kuje-Abuja",
    "phone_primary": "+234 902 940 5413",
    "phone_secondary": "+234 813 341 3127",
    "email": "office@ndgakuje.org",
    "address": "After SS Simon and Jude Minor Seminary, Kuchiyako, Kuje-Abuja",
    "maps_url": "https://maps.google.com/?q=Kuchiyako%2C+Kuje%2C+Abuja",
    "whatsapp_url": "https://wa.me/2349029405413",
}

PUBLIC_CLASS_OPTIONS = [
    ("JSS1", "JSS1"),
    ("JSS2", "JSS2"),
    ("JSS3", "JSS3"),
    ("SS1", "SS1"),
    ("SS2", "SS2"),
    ("SS3", "SS3"),
]

PUBLIC_NAVIGATION = [
    {"label": "Home", "url": "/"},
    {
        "label": "About Us",
        "url": "/about/",
        "children": [
            {"label": "About NDGA", "url": "/about/"},
            {"label": "Principal's Welcome", "url": "/principal/"},
            {"label": "Leadership", "url": "/about/leadership/"},
            {"label": "Mission, Vision & Values", "url": "/about/mission-vision-values/"},
            {"label": "School Life", "url": "/about/school-life/"},
        ],
    },
    {
        "label": "Academics",
        "url": "/academics/",
        "mega": True,
        "featured": {
            "title": "Guided learning from junior to senior secondary.",
            "text": "Students build strong academic habits, digital fluency, and disciplined study culture.",
            "image": PUBLIC_IMAGE["computer_lab"],
            "cta_label": "Explore Academics",
            "cta_url": "/academics/",
        },
        "columns": [
            {
                "title": "Academic Levels",
                "items": [
                    {"label": "Academics Overview", "url": "/academics/"},
                    {"label": "Junior Secondary", "url": "/academics/junior-secondary/"},
                    {"label": "Senior Secondary", "url": "/academics/senior-secondary/"},
                ],
            },
            {
                "title": "Learning Experience",
                "items": [
                    {"label": "Curriculum", "url": "/academics/curriculum/"},
                    {"label": "Subjects & Departments", "url": "/academics/subjects-departments/"},
                    {"label": "ICT / Digital Learning", "url": "/academics/ict-digital-learning/"},
                    {"label": "Co-curricular Activities", "url": "/academics/co-curricular-activities/"},
                ],
            },
            {
                "title": "Academic Support",
                "items": [
                    {"label": "Learning Support", "url": "/academics/learning-support/"},
                    {"label": "Examinations / Assessment", "url": "/academics/examinations-assessment/"},
                ],
            },
        ],
    },
    {
        "label": "Admissions",
        "url": "/admissions/",
        "mega": True,
        "featured": {
            "title": "Admissions made clear from enquiry to enrolment.",
            "text": "Families can review requirements, prepare documents, and begin registration online.",
            "image": PUBLIC_IMAGE["campus"],
            "cta_label": "Begin Registration",
            "cta_url": "/admissions/registration/",
            "secondary_label": "School Portal",
            "secondary_url": "/auth/login/?audience=student",
        },
        "columns": [
            {
                "title": "Admission Steps",
                "items": [
                    {"label": "Admissions Overview", "url": "/admissions/"},
                    {"label": "How to Apply", "url": "/admissions/how-to-apply/"},
                    {"label": "Online Registration", "url": "/admissions/registration/"},
                    {"label": "Entrance Exam / Screening", "url": "/events/"},
                ],
            },
            {
                "title": "Fees & Boarding",
                "items": [
                    {"label": "Fees & Charges", "url": "/fees/"},
                    {"label": "Hostel / Boarding", "url": "/hostel-boarding/"},
                    {"label": "Payment Information", "url": "/admissions/payment-information/"},
                    {"label": "Admission FAQs", "url": "/admissions/admission-faqs/"},
                ],
            },
        ],
    },
    {
        "label": "Life at NDGA",
        "url": "/life-at-ndga/",
        "children": [
            {"label": "Life at NDGA", "url": "/life-at-ndga/"},
            {"label": "Facilities", "url": "/facilities/"},
            {"label": "Gallery", "url": "/gallery/"},
            {"label": "Hostel / Boarding", "url": "/hostel-boarding/"},
            {"label": "Events", "url": "/events/"},
        ],
    },
    {
        "label": "News",
        "url": "/news/",
        "children": [
            {"label": "Latest News", "url": "/news/"},
            {"label": "Events", "url": "/events/"},
            {"label": "Admissions Updates", "url": "/news/admissions-guidance/"},
        ],
    },
    {"label": "Contact", "url": "/contact/"},
]

PUBLIC_NEWS = [
    {
        "slug": "admissions-guidance",
        "category": "Admissions",
        "title": "Preparing for entrance screening at NDGA",
        "summary": "Families should complete registration early, gather school records, and watch for screening communication from the admissions office.",
        "body": [
            "The admissions office guides families through registration, document review, screening, and final communication. Parents are advised to complete the online form early so the school can review records in good time.",
            "Applicants are expected to submit recent school records and prepare for English Language, Mathematics, and General Paper. Screening dates are communicated after the application stage is complete.",
        ],
        "image": PUBLIC_IMAGE["hero_students"],
    },
    {
        "slug": "boarding-life-overview",
        "category": "Boarding",
        "title": "A closer look at boarding life and student care",
        "summary": "Boarding at NDGA is structured around supervision, study routine, student welfare, and a calm environment for growth.",
        "body": [
            "The boarding programme is designed for girls who need a safe and supervised environment that supports learning, discipline, and healthy routine.",
            "Students benefit from guided prep periods, pastoral care, house supervision, and a school culture that values respect, responsibility, and community life.",
        ],
        "image": PUBLIC_IMAGE["hostel"],
    },
    {
        "slug": "science-and-digital-learning",
        "category": "Academics",
        "title": "Science, ICT, and hands-on learning at NDGA",
        "summary": "Laboratories, digital learning spaces, and subject support help students learn with confidence and clarity.",
        "body": [
            "Science and ICT are taught as practical learning areas, not only as theory. Students are introduced to laboratory work, computer use, guided research, and responsible digital practice.",
            "This supports academic preparation while building confidence in communication, problem-solving, and independent study.",
        ],
        "image": PUBLIC_IMAGE["science_lab"],
    },
]

PUBLIC_EVENTS = [
    {
        "slug": "entrance-screening-windows",
        "title": "Entrance screening windows",
        "summary": "Entrance examinations and screening are usually organised in March, May, July, and August, subject to school confirmation.",
        "meta": "Admissions",
        "location": "Notre Dame Girls' Academy, Kuje-Abuja",
    },
    {
        "slug": "orientation-and-resumption",
        "title": "Orientation and resumption preparation",
        "summary": "New families receive orientation guidance on school routine, boarding expectations, uniforms, and required materials before resumption.",
        "meta": "Student Life",
        "location": "Main campus",
    },
    {
        "slug": "faith-and-community-life",
        "title": "Faith and community life calendar",
        "summary": "Assemblies, faith formation, school gatherings, and community activities remain part of the school year.",
        "meta": "School Life",
        "location": "Campus",
    },
]

PUBLIC_GALLERY = [
    {"title": "Music & Arts", "image": PUBLIC_IMAGE["hero_music"], "category": "Creative Life"},
    {"title": "Campus Approach", "image": PUBLIC_IMAGE["campus"], "category": "Campus"},
    {"title": "ICT / CBT Lab", "image": PUBLIC_IMAGE["computer_lab"], "category": "Academics"},
    {"title": "Boarding", "image": PUBLIC_IMAGE["hostel"], "category": "Hostel"},
    {"title": "Sports", "image": PUBLIC_IMAGE["sports"], "category": "Sports"},
    {"title": "Science Lab", "image": PUBLIC_IMAGE["science_lab"], "category": "Facilities"},
    {"title": "Library", "image": PUBLIC_IMAGE["library"], "category": "Facilities"},
    {"title": "Assembly", "image": PUBLIC_IMAGE["assembly"], "category": "School Life"},
]

PUBLIC_FAQS = [
    {
        "question": "Who can apply to NDGA?",
        "answer": "Applications are accepted for junior and senior secondary entry levels, subject to available spaces and school policy for each class.",
    },
    {
        "question": "Is NDGA a boarding school?",
        "answer": "Yes. NDGA offers a boarding environment with structured supervision, study routine, and student welfare support.",
    },
    {
        "question": "What documents are required for registration?",
        "answer": "Parents should prepare a passport photograph, birth certificate, and recent school result or transcript for the applicant.",
    },
    {
        "question": "How are entrance screening dates communicated?",
        "answer": "After registration and document review, the school communicates the next step for screening or entrance examination.",
    },
]

PUBLIC_PAGE_CONTENT = {
    "about": {
        "title": "About Notre Dame Girls' Academy",
        "eyebrow": "About NDGA",
        "description": "A Catholic girls' secondary school in Kuje-Abuja shaped by learning, discipline, care, and faith formation.",
        "hero_image": PUBLIC_IMAGE["campus_block"],
        "sections": [
            {
                "layout": "split",
                "eyebrow": "The School Story",
                "title": "A girls' school shaped by purpose, discipline, and care",
                "body": [
                    "Notre Dame Girls' Academy, Kuje-Abuja is a Catholic girls' secondary school committed to the education of the girl child through sound academics, moral formation, and a safe boarding environment.",
                    "The school belongs to a wider Notre Dame educational tradition inspired by the Sisters of Notre Dame de Namur, a congregation founded in 1804 with a long commitment to faith, education, service, and the dignity of young people.",
                ],
                "image": PUBLIC_IMAGE["campus"],
            },
            {
                "layout": "cards",
                "eyebrow": "Mission, Vision & Values",
                "title": "What guides the life of the school",
                "cards": [
                    {"title": "Mission", "text": "To form young girls in knowledge, character, faith, and service through disciplined secondary education."},
                    {"title": "Vision", "text": "To raise confident, responsible, and well-educated young women prepared to contribute positively to society."},
                    {"title": "Values", "text": "Faith, discipline, responsibility, respect, service, and excellence in learning shape school life."},
                ],
            },
            {
                "layout": "list",
                "eyebrow": "Why Families Choose NDGA",
                "title": "A school environment that balances guidance and growth",
                "items": [
                    "A disciplined Catholic setting for girls.",
                    "Strong focus on learning and moral formation.",
                    "Boarding structure that supports routine and welfare.",
                    "Academic, social, and personal development in one community.",
                ],
            },
        ],
    },
    "principal": {
        "title": "Principal's Welcome",
        "eyebrow": "Leadership",
        "description": "A welcome from the Principal of Notre Dame Girls' Academy.",
        "hero_image": PUBLIC_IMAGE["principal"],
        "sections": [
            {
                "layout": "split",
                "eyebrow": "A Message from the Principal",
                "title": "Guiding girls in faith, learning, and responsible living",
                "body": [
                    "Welcome to Notre Dame Girls' Academy. We are committed to helping every student grow in discipline, knowledge, faith, and self-respect within a caring school community.",
                    "Our work with parents and guardians is built on trust, clear guidance, and the shared desire to help each girl discover her strengths and use them well.",
                    "At NDGA, learning goes together with character formation, healthy routine, and a sense of responsibility to others.",
                ],
                "image": PUBLIC_IMAGE["principal"],
                "quote_author": "Office of the Principal",
                "quote_role": "Notre Dame Girls' Academy, Kuje-Abuja",
            }
        ],
    },
    "mission-vision-values": {
        "title": "Mission, Vision & Values",
        "eyebrow": "Identity",
        "description": "The convictions that shape teaching, discipline, leadership, and school life at NDGA.",
        "hero_image": PUBLIC_IMAGE["assembly"],
        "sections": [
            {
                "layout": "cards",
                "title": "The convictions behind daily school life",
                "cards": [
                    {"title": "Mission", "text": "To provide quality education that forms young girls in knowledge, character, faith, and service."},
                    {"title": "Vision", "text": "To raise confident, responsible, and well-educated young women prepared for life and contribution to society."},
                    {"title": "Faith", "text": "School life is rooted in Christian values, prayer, and respect for the dignity of every person."},
                    {"title": "Discipline", "text": "Routine, responsibility, and order remain essential to how students learn and grow."},
                    {"title": "Learning", "text": "Students are taught to think clearly, work hard, and take pride in honest effort."},
                    {"title": "Service", "text": "Leadership at NDGA is linked to care for others, humility, and community life."},
                ],
            }
        ],
    },
    "leadership": {
        "title": "Leadership",
        "eyebrow": "Leadership",
        "description": "School leadership at NDGA combines pastoral care, academic seriousness, and institutional responsibility.",
        "hero_image": PUBLIC_IMAGE["principal"],
        "sections": [
            {
                "layout": "cards",
                "title": "Leadership is visible in school culture, not only in offices",
                "cards": [
                    {"title": "Principal", "text": "Provides school-wide direction, academic oversight, and pastoral leadership.", "image": PUBLIC_IMAGE["principal"]},
                    {"title": "Vice Principal", "text": "Supports academic coordination, school routine, and student development."},
                    {"title": "Bursar & Admin Team", "text": "Supports finance, records, welfare coordination, and communication with families."},
                ],
            }
        ],
    },
    "school-life": {
        "title": "School Life",
        "eyebrow": "Life at NDGA",
        "description": "A balanced life of study, boarding, sports, faith formation, and healthy routine.",
        "hero_image": PUBLIC_IMAGE["socials"],
        "sections": [
            {
                "layout": "split",
                "title": "Daily life designed for learning and growth",
                "body": [
                    "School life at NDGA combines classroom learning with supervised boarding life, sports, music, assemblies, faith activities, and community routines that help girls grow with confidence and structure.",
                    "Students learn to manage time, live respectfully with others, and take part in the wider life of the school beyond the classroom.",
                ],
                "image": PUBLIC_IMAGE["socials"],
            }
        ],
    },
    "academics": {
        "title": "Academics",
        "eyebrow": "Academics",
        "description": "Strong foundations, guided learning, digital readiness, and broad student development from junior to senior secondary.",
        "hero_image": PUBLIC_IMAGE["computer_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "Academic pathways and support",
                "cards": [
                    {"title": "Junior Secondary", "text": "Building strong foundations in literacy, numeracy, science, communication, and study habits.", "image": PUBLIC_IMAGE["hero_students"], "href": "/academics/junior-secondary/"},
                    {"title": "Senior Secondary", "text": "Supporting deeper subject focus, examination readiness, leadership, and future preparation.", "image": PUBLIC_IMAGE["hero_alt"], "href": "/academics/senior-secondary/"},
                    {"title": "Curriculum", "text": "A structured curriculum with classroom teaching, practical work, reading culture, and guided assessment.", "image": PUBLIC_IMAGE["science_lab"], "href": "/academics/curriculum/"},
                    {"title": "ICT / Digital Learning", "text": "Introducing students to computer use, research, digital responsibility, and CBT readiness.", "image": PUBLIC_IMAGE["computer_lab"], "href": "/academics/ict-digital-learning/"},
                    {"title": "Co-curricular Activities", "text": "Music, clubs, sports, and social formation remain part of education at NDGA.", "image": PUBLIC_IMAGE["hero_music"], "href": "/academics/co-curricular-activities/"},
                ],
            }
        ],
    },
    "junior-secondary": {
        "title": "Junior Secondary",
        "eyebrow": "Academic Levels",
        "description": "Junior secondary builds confident learners through clear routines and strong foundational teaching.",
        "hero_image": PUBLIC_IMAGE["hero_students"],
        "sections": [
            {
                "layout": "list",
                "title": "Junior secondary focus",
                "items": [
                    "English Studies and communication skills",
                    "Mathematics and logical thinking",
                    "Basic Science and practical introduction",
                    "Social Studies and human development",
                    "ICT, study habits, and classroom discipline",
                ],
            }
        ],
    },
    "senior-secondary": {
        "title": "Senior Secondary",
        "eyebrow": "Academic Levels",
        "description": "Senior secondary prepares students for stronger subject focus, responsible leadership, and life beyond school.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "list",
                "title": "Senior secondary focus",
                "items": [
                    "Focused subject preparation and guided academic support",
                    "Exam readiness and disciplined study structure",
                    "Leadership opportunities and student responsibility",
                    "Preparation for higher studies and informed decision-making",
                ],
            }
        ],
    },
    "curriculum": {
        "title": "Curriculum",
        "eyebrow": "Curriculum",
        "description": "The curriculum at NDGA combines core classroom instruction with practical learning and responsible study culture.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "Main subject groups",
                "cards": [
                    {"title": "English Studies", "text": "Reading, writing, grammar, comprehension, and communication."},
                    {"title": "Mathematics", "text": "Numeracy, reasoning, and problem-solving."},
                    {"title": "Sciences", "text": "Basic Science, Biology, Chemistry, Physics, and related practical learning."},
                    {"title": "Arts & Humanities", "text": "Social Studies, Religious and Moral Instruction, History, and related fields."},
                    {"title": "Business & Commercial", "text": "Subject options that prepare students for broader academic and practical competence."},
                    {"title": "ICT", "text": "Digital literacy, research, productivity tools, and CBT familiarity."},
                ],
            }
        ],
    },
    "subjects-departments": {
        "title": "Subjects & Departments",
        "eyebrow": "Departments",
        "description": "Subject teaching at NDGA is organised to give students clarity, progression, and support.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "list",
                "title": "Departments and learning areas",
                "items": [
                    "Languages and Communication",
                    "Mathematics and Quantitative Thinking",
                    "Science and Practical Learning",
                    "Social Sciences, Arts, and Humanities",
                    "ICT and Digital Learning",
                    "Creative and Co-curricular Development",
                ],
            }
        ],
    },
    "ict-digital-learning": {
        "title": "ICT / Digital Learning",
        "eyebrow": "Digital Learning",
        "description": "ICT learning supports research, computer literacy, responsible technology use, and CBT readiness.",
        "hero_image": PUBLIC_IMAGE["computer_lab"],
        "sections": [
            {
                "layout": "split",
                "title": "Digital skills are taught as part of school readiness",
                "body": [
                    "Students are introduced to digital tools in a guided way so that technology supports classroom learning rather than distracts from it.",
                    "ICT spaces also support computer-based testing, digital assignments, research, and responsible technology habits.",
                ],
                "image": PUBLIC_IMAGE["computer_lab"],
            }
        ],
    },
    "co-curricular-activities": {
        "title": "Co-curricular Activities",
        "eyebrow": "Beyond the Classroom",
        "description": "Clubs, sports, music, and school activities help students grow in confidence, teamwork, and expression.",
        "hero_image": PUBLIC_IMAGE["sports"],
        "sections": [
            {
                "layout": "cards",
                "title": "Activities that support the whole student",
                "cards": [
                    {"title": "Clubs", "text": "Students explore interests, service, leadership, and collaboration."},
                    {"title": "Music & Creative Arts", "text": "Creative spaces help students express talent and confidence."},
                    {"title": "Sports", "text": "Basketball, volleyball, table tennis, and physical activity support fitness and teamwork."},
                ],
            }
        ],
    },
    "learning-support": {
        "title": "Learning Support",
        "eyebrow": "Learning Support",
        "description": "Students learn best with structure, guidance, and timely academic support.",
        "hero_image": PUBLIC_IMAGE["library"],
        "sections": [
            {
                "layout": "list",
                "title": "How support happens",
                "items": [
                    "Classroom guidance and teacher follow-up",
                    "Clear routines for study and prep",
                    "Reading support and supervised revision",
                    "Parent-school communication where needed",
                ],
            }
        ],
    },
    "examinations-assessment": {
        "title": "Examinations & Assessment",
        "eyebrow": "Assessment",
        "description": "Assessment at NDGA combines continuous work, school examinations, and responsible academic monitoring.",
        "hero_image": PUBLIC_IMAGE["hero_alt"],
        "sections": [
            {
                "layout": "list",
                "title": "Assessment structure",
                "items": [
                    "Continuous assessment and classwork",
                    "Tests and examination preparation",
                    "Guided feedback from teachers",
                    "Result review and structured reporting",
                ],
            }
        ],
    },
    "admissions": {
        "title": "Admissions",
        "eyebrow": "Admissions",
        "description": "A clear admissions path for families seeking disciplined boarding education, sound academics, and moral formation.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "timeline",
                "title": "Admission process",
                "timeline": [
                    {"title": "Register online", "text": "Complete applicant and parent details and upload key records."},
                    {"title": "Review fees and payment guidance", "text": "Admissions guidance includes prescribed fees and next payment steps."},
                    {"title": "Screening or entrance examination", "text": "Applicants are scheduled after review and school communication."},
                    {"title": "Admission review and activation", "text": "Successful applicants receive confirmation and next steps."},
                ],
            },
            {
                "layout": "cards",
                "title": "Screening subjects",
                "cards": [
                    {"title": "English Language / Verbal", "text": "Reading, comprehension, language, and basic verbal reasoning."},
                    {"title": "Mathematics / Quantitative", "text": "Number sense, reasoning, and applied problem-solving."},
                    {"title": "General Paper", "text": "General awareness and age-appropriate written response."},
                ],
            },
        ],
    },
    "how-to-apply": {
        "title": "How to Apply",
        "eyebrow": "Admissions Guide",
        "description": "A simple guide to preparing, registering, and following through with the admissions process.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "list",
                "title": "Before you begin",
                "items": [
                    "Choose the intended class level.",
                    "Prepare passport photograph, birth certificate, and recent school result.",
                    "Keep parent or guardian contact details ready.",
                    "Submit the online registration form and watch for admissions communication.",
                ],
            }
        ],
    },
    "registration": {
        "title": "Online Registration",
        "eyebrow": "Admissions Form",
        "description": "Begin the admission process online with applicant details, boarding preference, and supporting documents.",
        "hero_image": PUBLIC_IMAGE["hero_students"],
        "sections": [],
    },
    "fees": {
        "title": "Fees & Charges",
        "eyebrow": "Fees",
        "description": "Review the main payment areas families should plan for before admission is completed.",
        "hero_image": PUBLIC_IMAGE["campus_block"],
        "sections": [
            {
                "layout": "cards",
                "title": "Fee visibility for families",
                "cards": [
                    {"title": "School Fees", "text": "Tuition and core school charges are communicated clearly during admissions and payment guidance."},
                    {"title": "Hostel / Boarding", "text": "Boarding-related charges are separated so families can plan accurately."},
                    {"title": "Other Charges", "text": "Where applicable, registration, examinations, uniforms, and related items are clarified."},
                    {"title": "Payment Information", "text": "Approved payment channels and next steps are shared during the admission process."},
                ],
            }
        ],
    },
    "hostel-boarding": {
        "title": "Hostel & Boarding",
        "eyebrow": "Boarding",
        "description": "Boarding at NDGA is designed around routine, supervision, welfare, and a calm environment for study.",
        "hero_image": PUBLIC_IMAGE["hostel"],
        "sections": [
            {
                "layout": "split",
                "title": "A boarding environment built for care and order",
                "body": [
                    "Boarding students live within a supervised environment that supports routine, study, rest, and student welfare.",
                    "The aim is to provide a safe setting where girls can grow in responsibility, community life, and disciplined study habits.",
                ],
                "image": PUBLIC_IMAGE["hostel"],
            }
        ],
    },
    "payment-information": {
        "title": "Payment Information",
        "eyebrow": "Payments",
        "description": "Payment guidance for admissions and fees is shared in a controlled and clear process.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "list",
                "title": "What families should expect",
                "items": [
                    "Admissions guidance provides approved payment channels.",
                    "Online registration can be completed before the payment stage.",
                    "Parents should keep payment evidence and reference details where required.",
                    "The student portal remains the secure route for parent-facing visibility after onboarding.",
                ],
            }
        ],
    },
    "admission-faqs": {
        "title": "Admission FAQs",
        "eyebrow": "Admissions Support",
        "description": "Common questions from parents and guardians preparing for admission.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "faq",
                "title": "Questions families ask most often",
                "faqs": PUBLIC_FAQS,
            }
        ],
    },
    "life-at-ndga": {
        "title": "Life at NDGA",
        "eyebrow": "School Life",
        "description": "Boarding, sports, clubs, worship, assemblies, and community routines all shape the experience at NDGA.",
        "hero_image": PUBLIC_IMAGE["socials"],
        "sections": [
            {
                "layout": "cards",
                "title": "What school life looks like",
                "cards": [
                    {"title": "Boarding Life", "text": "Structured supervision, study time, and pastoral support.", "image": PUBLIC_IMAGE["hostel"], "href": "/hostel-boarding/"},
                    {"title": "Facilities", "text": "Labs, library, classrooms, sports areas, and boarding spaces.", "image": PUBLIC_IMAGE["campus_block"], "href": "/facilities/"},
                    {"title": "Gallery", "text": "A closer look at the school in pictures.", "image": PUBLIC_IMAGE["hero_music"], "href": "/gallery/"},
                ],
            }
        ],
    },
    "facilities": {
        "title": "Facilities",
        "eyebrow": "Facilities",
        "description": "The physical spaces at NDGA support learning, student life, and everyday discipline.",
        "hero_image": PUBLIC_IMAGE["campus_block"],
        "sections": [
            {
                "layout": "cards",
                "title": "Spaces designed to support school life",
                "cards": [
                    {"title": "Science Laboratories", "text": "Practical learning spaces for science subjects.", "image": PUBLIC_IMAGE["science_lab"]},
                    {"title": "ICT / CBT Lab", "text": "Computer spaces for digital learning and assessment.", "image": PUBLIC_IMAGE["computer_lab"]},
                    {"title": "Library", "text": "A calm reading environment for research and revision.", "image": PUBLIC_IMAGE["library"]},
                    {"title": "Sports Spaces", "text": "Physical activity areas that encourage fitness and teamwork.", "image": PUBLIC_IMAGE["sports"]},
                    {"title": "Hostel", "text": "Boarding facilities designed for safe student welfare and routine.", "image": PUBLIC_IMAGE["hostel"]},
                    {"title": "Campus Environment", "text": "Open spaces and school buildings that support order and calm.", "image": PUBLIC_IMAGE["campus"]},
                ],
            }
        ],
    },
    "gallery": {
        "title": "Gallery",
        "eyebrow": "Gallery",
        "description": "A visual look at academics, boarding, campus life, facilities, sports, and student activities.",
        "hero_image": PUBLIC_IMAGE["hero_music"],
        "sections": [],
    },
    "news": {
        "title": "News",
        "eyebrow": "News",
        "description": "School updates, admissions guidance, boarding highlights, and stories from NDGA life.",
        "hero_image": PUBLIC_IMAGE["assembly"],
        "sections": [],
    },
    "events": {
        "title": "Events",
        "eyebrow": "Events",
        "description": "Important admissions windows, orientation planning, and school calendar highlights.",
        "hero_image": PUBLIC_IMAGE["assembly"],
        "sections": [],
    },
    "contact": {
        "title": "Contact Us",
        "eyebrow": "Contact",
        "description": "Admissions enquiries, school information, and support for parents and guardians.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [],
    },
}

PUBLIC_SEARCH_LINKS = [
    {"label": "About NDGA", "url": "/about/", "group": "About"},
    {"label": "Principal's Welcome", "url": "/principal/", "group": "About"},
    {"label": "Academics Overview", "url": "/academics/", "group": "Academics"},
    {"label": "Junior Secondary", "url": "/academics/junior-secondary/", "group": "Academics"},
    {"label": "Senior Secondary", "url": "/academics/senior-secondary/", "group": "Academics"},
    {"label": "Admissions Overview", "url": "/admissions/", "group": "Admissions"},
    {"label": "How to Apply", "url": "/admissions/how-to-apply/", "group": "Admissions"},
    {"label": "Online Registration", "url": "/admissions/registration/", "group": "Admissions"},
    {"label": "Fees & Charges", "url": "/fees/", "group": "Admissions"},
    {"label": "Hostel & Boarding", "url": "/hostel-boarding/", "group": "School Life"},
    {"label": "Facilities", "url": "/facilities/", "group": "School Life"},
    {"label": "Gallery", "url": "/gallery/", "group": "School Life"},
    {"label": "News", "url": "/news/", "group": "News"},
    {"label": "Events", "url": "/events/", "group": "News"},
    {"label": "Contact", "url": "/contact/", "group": "Contact"},
]

PUBLIC_INDEXABLE_PATHS = {
    "/",
    "/about/",
    "/principal/",
    "/about/leadership/",
    "/about/mission-vision-values/",
    "/about/school-life/",
    "/academics/",
    "/academics/junior-secondary/",
    "/academics/senior-secondary/",
    "/academics/curriculum/",
    "/academics/subjects-departments/",
    "/academics/ict-digital-learning/",
    "/academics/co-curricular-activities/",
    "/academics/learning-support/",
    "/academics/examinations-assessment/",
    "/admissions/",
    "/admissions/how-to-apply/",
    "/admissions/registration/",
    "/fees/",
    "/hostel-boarding/",
    "/admissions/payment-information/",
    "/admissions/admission-faqs/",
    "/life-at-ndga/",
    "/facilities/",
    "/gallery/",
    "/news/",
    "/events/",
    "/contact/",
}


def public_site_enabled():
    from django.conf import settings

    return bool(getattr(settings, "PUBLIC_WEBSITE_ENABLED", False))


def get_public_contact(*, school_profile=None):
    payload = deepcopy(PUBLIC_CONTACT)
    if school_profile is None:
        return payload
    if school_profile.school_name:
        payload["school_name"] = school_profile.school_name
    if school_profile.contact_email:
        payload["email"] = school_profile.contact_email
    if school_profile.contact_phone:
        payload["phone_primary"] = school_profile.contact_phone
    if school_profile.address:
        payload["address"] = school_profile.address
    return payload


def get_public_page(slug: str):
    return deepcopy(PUBLIC_PAGE_CONTENT.get(slug))


def get_public_news():
    return deepcopy(PUBLIC_NEWS)


def get_public_news_item(slug: str):
    for item in PUBLIC_NEWS:
        if item["slug"] == slug:
            return deepcopy(item)
    return None


def get_public_events():
    return deepcopy(PUBLIC_EVENTS)


def get_public_gallery():
    return deepcopy(PUBLIC_GALLERY)


def get_public_site_context(*, school_profile=None):
    principal_name = ""
    if school_profile is not None:
        principal_name = (school_profile.principal_name or "").strip()

    return {
        "public_navigation": deepcopy(PUBLIC_NAVIGATION),
        "public_contact": get_public_contact(school_profile=school_profile),
        "public_gallery": get_public_gallery(),
        "public_news": get_public_news(),
        "public_events": get_public_events(),
        "public_search_links": deepcopy(PUBLIC_SEARCH_LINKS),
        "public_faqs": deepcopy(PUBLIC_FAQS),
        "public_principal_name": principal_name or "Office of the Principal",
        "public_images": deepcopy(PUBLIC_IMAGE),
        "public_class_options": deepcopy(PUBLIC_CLASS_OPTIONS),
        "public_apply_url": "/admissions/registration/",
        "public_portal_url": "/auth/login/?audience=student",
        "public_portal_text": "School Portal",
    }
