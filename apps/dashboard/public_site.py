from __future__ import annotations

from copy import deepcopy


PUBLIC_IMAGE = {
    "hero": "images/public/facility-campus-view.jpeg",
    "hero_alt": "images/public/campus-life-1.jpg",
    "hero_music": "images/public/social-clubs-1.jpg",
    "hero_students": "images/public/campus-life-2.jpg",
    "hero_video": "videos/ndga-campus.mp4",
    "principal": "images/public/principal-portrait.jpeg",
    "logo": "images/ndga/logo.png",
    "campus": "images/public/facility-entrance.jpeg",
    "campus_view": "images/public/facility-campus-view.jpeg",
    "campus_refectory": "images/public/facility-refectory.jpeg",
    "campus_block": "images/public/campus-block.jpg",
    "campus-life-1": "images/public/campus-life-1.jpg",
    "campus-life-2": "images/public/campus-life-2.jpg",
    "computer_lab": "images/public/academics-computer-senior.jpg",
    "computer_lab_junior": "images/public/academics-computer-junior.jpg",
    "hostel": "images/public/boarding-hostel-1.jpeg",
    "hostel_alt": "images/public/boarding-hostel-2.jpeg",
    "hostel_alt_two": "images/public/boarding-hostel-3.jpeg",
    "sports": "images/public/sports-1.jpeg",
    "sports_alt": "images/public/sports-2.jpeg",
    "sports_alt_two": "images/public/sports-3.jpeg",
    "science_lab": "images/public/academics-chemistry-lab.jpg",
    "physics_lab": "images/public/academics-physics-lab.jpg",
    "math_lab": "images/public/academics-math-lab.jpg",
    "library": "images/public/academics-library-main.jpg",
    "assembly": "images/public/faith-assembly-1.jpeg",
    "assembly_alt": "images/public/faith-assembly-2.jpeg",
    "socials": "images/public/social-clubs-1.jpg",
    "socials_alt": "images/public/social-clubs-2.jpg",
    "socials_alt_two": "images/public/social-clubs-3.jpg",
    "pioneers": "images/public/events-pioneers-1.jpg",
    "pioneers_alt": "images/public/events-pioneers-2.jpg",
}

PUBLIC_CONTACT = {
    "school_name": "Notre Dame Girls' Academy, Kuje-Abuja",
    "phone_primary": "+234 902 940 5413",
    "phone_secondary": "+234 813 341 3127",
    "email": "office@ndgakuje.org",
    "address": "Just after SS Simon and Jude Minor Seminary, Kuchiyako, Kuje-Abuja",
    "maps_url": "https://maps.app.goo.gl/t7Zx37KFpbYVZqtP6",
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
        "label": "About",
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
            "title": "Admissions are structured, guided, and easy to follow.",
            "text": "Families can review the process, screening subjects, boarding guidance, and registration steps clearly.",
            "image": PUBLIC_IMAGE["campus_view"],
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
        "label": "Explore",
        "url": "/life-at-ndga/",
        "children": [
            {"label": "Life at NDGA", "url": "/life-at-ndga/"},
            {"label": "Facilities", "url": "/facilities/"},
            {"label": "Gallery", "url": "/gallery/"},
            {"label": "News", "url": "/news/"},
            {"label": "Events", "url": "/events/"},
            {"label": "Hostel / Boarding", "url": "/hostel-boarding/"},
            {"label": "Contact", "url": "/contact/"},
        ],
    },
]

PUBLIC_NEWS = [
    {
        "slug": "third-term-resumption-2026",
        "category": "School Calendar",
        "date": "April 18, 2026",
        "title": "Third term for the 2025/2026 session resumes on April 18, 2026",
        "summary": "Families are encouraged to prepare uniforms, academic materials, and boarding essentials ahead of resumption.",
        "body": [
            "The second term has now been concluded, and the school is preparing to receive students for the third term of the 2025/2026 academic session on Friday, April 18, 2026.",
            "Parents and guardians are encouraged to confirm student travel arrangements, personal supplies, and all resumption requirements early so that students can settle back into school routine smoothly.",
        ],
        "image": PUBLIC_IMAGE["campus_view"],
    },
    {
        "slug": "waec-preparation-2026",
        "category": "Academics",
        "date": "April 7, 2026",
        "title": "Preparing our students for WAEC with focus, structure, and guided revision",
        "summary": "Revision support, supervised study, and subject-based guidance continue to shape exam preparation for senior students.",
        "body": [
            "Senior students are being prepared through subject revision, guided assessment practice, and close follow-up from teachers as they approach public examinations.",
            "The school's academic culture places emphasis on clarity, routine, and steady preparation so that students approach WAEC and related examinations with confidence and discipline.",
        ],
        "image": PUBLIC_IMAGE["science_lab"],
    },
    {
        "slug": "easter-message-2026",
        "category": "Community",
        "date": "April 5, 2026",
        "title": "A joyful Easter message to the NDGA family",
        "summary": "The school community marked Easter with gratitude, reflection, and renewed hope for the term ahead.",
        "body": [
            "As the Easter season concludes, the school gives thanks for the grace of the season and prays for peace, strength, and joy in every family connected to NDGA.",
            "The values of hope, sacrifice, service, and renewal continue to guide the spiritual and community life of the school.",
        ],
        "image": PUBLIC_IMAGE["assembly"],
    },
    {
        "slug": "girls-education-leadership",
        "category": "Girls' Education",
        "date": "April 2, 2026",
        "title": "Why focused girls' education matters for leadership and lifelong confidence",
        "summary": "An all-girls learning environment gives students room to grow in voice, leadership, and responsible independence.",
        "body": [
            "Notre Dame Girls' Academy remains committed to the education of the girl child through a learning environment where students are encouraged to think clearly, speak confidently, and lead responsibly.",
            "The school's boarding structure, academic discipline, and co-curricular opportunities are all designed to help girls grow in knowledge, character, service, and self-belief.",
        ],
        "image": PUBLIC_IMAGE["socials_alt"],
    },
]

PUBLIC_EVENTS = [
    {
        "slug": "third-term-resumption",
        "title": "Third term resumption",
        "summary": "Students resume for the third term of the 2025/2026 session on Friday, April 18, 2026.",
        "meta": "School Calendar",
        "date": "April 18, 2026",
        "location": "Notre Dame Girls' Academy, Kuje-Abuja",
    },
    {
        "slug": "entrance-exam-cycle",
        "title": "Entrance examination windows",
        "summary": "Entrance examinations are planned across March, May, July, and August, subject to school confirmation for each cycle.",
        "meta": "Admissions",
        "date": "March, May, July, August",
        "location": "Admissions Office",
    },
    {
        "slug": "orientation-weekend",
        "title": "New family orientation and onboarding guidance",
        "summary": "Families receive guidance on boarding routine, required items, communication, and school expectations before full resumption.",
        "meta": "Orientation",
        "date": "Before resumption",
        "location": "Campus",
    },
]

PUBLIC_GALLERY = [
    {
        "slug": "campus-facilities",
        "title": "Campus & Facilities",
        "summary": "Academic blocks, refectory spaces, walkways, and the wider school environment.",
        "image": PUBLIC_IMAGE["campus_view"],
        "images": [
            PUBLIC_IMAGE["campus"],
            PUBLIC_IMAGE["campus_view"],
            PUBLIC_IMAGE["campus_refectory"],
            PUBLIC_IMAGE["campus_block"],
        ],
    },
    {
        "slug": "classroom-learning",
        "title": "Classroom Learning",
        "summary": "Focused teaching spaces for junior and senior secondary students.",
        "image": PUBLIC_IMAGE["computer_lab_junior"],
        "images": [
            PUBLIC_IMAGE["computer_lab_junior"],
            PUBLIC_IMAGE["computer_lab"],
            PUBLIC_IMAGE["campus-life-1"],
            PUBLIC_IMAGE["campus-life-2"],
        ],
    },
    {
        "slug": "science-ict",
        "title": "Science & ICT",
        "summary": "Laboratory learning, digital skills, and practical exposure.",
        "image": PUBLIC_IMAGE["science_lab"],
        "images": [
            PUBLIC_IMAGE["science_lab"],
            PUBLIC_IMAGE["physics_lab"],
            PUBLIC_IMAGE["math_lab"],
            PUBLIC_IMAGE["library"],
        ],
    },
    {
        "slug": "boarding-life",
        "title": "Boarding Life",
        "summary": "A supervised hostel environment that supports study, rest, and student welfare.",
        "image": PUBLIC_IMAGE["hostel"],
        "images": [
            PUBLIC_IMAGE["hostel"],
            PUBLIC_IMAGE["hostel_alt"],
            PUBLIC_IMAGE["hostel_alt_two"],
        ],
    },
    {
        "slug": "sports-games",
        "title": "Sports & Games",
        "summary": "Basketball, volleyball, table tennis, and healthy student activity.",
        "image": PUBLIC_IMAGE["sports"],
        "images": [
            PUBLIC_IMAGE["sports"],
            PUBLIC_IMAGE["sports_alt"],
            PUBLIC_IMAGE["sports_alt_two"],
        ],
    },
    {
        "slug": "clubs-activities",
        "title": "Clubs & Activities",
        "summary": "Student participation in creative, social, and leadership life.",
        "image": PUBLIC_IMAGE["socials"],
        "images": [
            PUBLIC_IMAGE["socials"],
            PUBLIC_IMAGE["socials_alt"],
            PUBLIC_IMAGE["socials_alt_two"],
        ],
    },
    {
        "slug": "faith-formation",
        "title": "Faith & Formation",
        "summary": "Assemblies, prayer, worship, and reflective school life.",
        "image": PUBLIC_IMAGE["assembly"],
        "images": [
            PUBLIC_IMAGE["assembly"],
            PUBLIC_IMAGE["assembly_alt"],
        ],
    },
    {
        "slug": "events-celebrations",
        "title": "Events & Celebrations",
        "summary": "Milestones, school gatherings, and moments from the NDGA community.",
        "image": PUBLIC_IMAGE["pioneers"],
        "images": [
            PUBLIC_IMAGE["pioneers"],
            PUBLIC_IMAGE["pioneers_alt"],
        ],
    },
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
        "description": "A broad academic programme shaped by discipline, strong teaching, practical learning, and preparation for life after school.",
        "hero_image": PUBLIC_IMAGE["computer_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "Academic pathways and teaching areas",
                "cards": [
                    {"title": "Junior Secondary", "text": "Strong foundations in language, numeracy, science, civic awareness, and disciplined study habits.", "image": PUBLIC_IMAGE["computer_lab_junior"], "href": "/academics/junior-secondary/"},
                    {"title": "Senior Secondary", "text": "Clear subject direction, guided exam preparation, and support for future academic choices.", "image": PUBLIC_IMAGE["science_lab"], "href": "/academics/senior-secondary/"},
                    {"title": "Curriculum", "text": "Formal and informal learning work together through classroom teaching, assemblies, clubs, and student formation.", "image": PUBLIC_IMAGE["physics_lab"], "href": "/academics/curriculum/"},
                    {"title": "Subjects Offered", "text": "A wide subject base including sciences, humanities, business, languages, ICT, and creative studies.", "image": PUBLIC_IMAGE["math_lab"], "href": "/academics/subjects-departments/"},
                    {"title": "ICT & Digital Learning", "text": "Computer use, CBT readiness, research, and responsible technology practice.", "image": PUBLIC_IMAGE["computer_lab"], "href": "/academics/ict-digital-learning/"},
                    {"title": "Clubs & Activities", "text": "Debating, science, music, press, French, justice and peace, gardening, and more.", "image": PUBLIC_IMAGE["socials"], "href": "/academics/co-curricular-activities/"},
                ],
            }
        ],
    },
    "junior-secondary": {
        "title": "Junior Secondary",
        "eyebrow": "Academic Levels",
        "description": "Junior secondary builds academic confidence through clear routine, strong teaching, and close attention to learning habits.",
        "hero_image": PUBLIC_IMAGE["hero_students"],
        "sections": [
            {
                "layout": "cards",
                "title": "Junior school learning focus",
                "cards": [
                    {"title": "Language & Communication", "text": "English Studies, French, reading culture, writing, and classroom discussion."},
                    {"title": "Numeracy & Logic", "text": "Mathematics and the habits of careful problem-solving."},
                    {"title": "Science Foundations", "text": "Basic Science, introductory practical learning, and observation skills."},
                    {"title": "Citizenship & Formation", "text": "Social Studies, History, CRS, civic learning, and responsible conduct."},
                    {"title": "Skills & Creativity", "text": "Business Studies, Home Economics, Cultural and Creative Arts, and digital literacy."},
                ],
            }
        ],
    },
    "senior-secondary": {
        "title": "Senior Secondary",
        "eyebrow": "Academic Levels",
        "description": "Senior secondary prepares students for public examinations, stronger subject depth, and leadership with responsibility.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "Senior school priorities",
                "cards": [
                    {"title": "Exam Preparation", "text": "WAEC and senior school readiness through revision structure, assessment, and subject follow-up."},
                    {"title": "Subject Depth", "text": "Students build stronger knowledge through science, arts, business, and practical learning pathways."},
                    {"title": "Independent Study", "text": "Prep routine, reading, revision, and closer responsibility for academic progress."},
                    {"title": "Leadership & Service", "text": "Students are encouraged to lead, serve, and participate responsibly in school life."},
                ],
            }
        ],
    },
    "curriculum": {
        "title": "Curriculum",
        "eyebrow": "Curriculum",
        "description": "The curriculum combines classroom teaching, practical learning, faith formation, assemblies, clubs, and the broader experience of school life.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "How learning is organised at NDGA",
                "cards": [
                    {"title": "Formal Curriculum", "text": "National curriculum coverage for junior and senior secondary subjects with assessment and classroom structure."},
                    {"title": "Practical Learning", "text": "Laboratories, ICT spaces, reading support, music, art, and sports enrich academic work."},
                    {"title": "Moral & Spiritual Formation", "text": "Religious studies, assemblies, retreats, and daily school culture form part of student growth."},
                    {"title": "Informal Curriculum", "text": "Assemblies, student leadership, peer learning, clubs, and school values support education for life."},
                ],
            }
        ],
    },
    "subjects-departments": {
        "title": "Subjects & Departments",
        "eyebrow": "Departments",
        "description": "NDGA offers a broad range of subjects across junior and senior secondary levels so that students grow in knowledge, practical skill, and academic readiness.",
        "hero_image": PUBLIC_IMAGE["science_lab"],
        "sections": [
            {
                "layout": "cards",
                "title": "Subject groups",
                "cards": [
                    {
                        "title": "Languages & Communication",
                        "text": "Language development, communication, reading, and writing.",
                        "items": ["English Language", "Literature", "French", "A major Nigerian Language"],
                    },
                    {
                        "title": "Science & Practical Learning",
                        "text": "Core and advanced science learning with laboratory support.",
                        "items": ["Basic Science", "Biology", "Chemistry", "Physics", "Agricultural Science", "Fisheries"],
                    },
                    {
                        "title": "Mathematics & Technical",
                        "text": "Reasoning, problem-solving, and technical thinking.",
                        "items": ["Mathematics", "Further Mathematics", "Basic Technology", "Technical Drawing", "Data Processing"],
                    },
                    {
                        "title": "Humanities & Social Studies",
                        "text": "Citizenship, social awareness, and reflective learning.",
                        "items": ["Social Studies", "History", "Government", "Civic Education", "Christian Religious Studies"],
                    },
                    {
                        "title": "Business & Home Studies",
                        "text": "Commercial and life skills that support practical competence.",
                        "items": ["Business Studies", "Commerce", "Economics", "Financial Accounting", "Home Economics", "Foods & Nutrition", "Catering Craft"],
                    },
                    {
                        "title": "Creative & Personal Development",
                        "text": "Expression, wellbeing, and all-round growth.",
                        "items": ["Cultural & Creative Arts", "Music", "Art", "Physical & Health Education", "Garment Making"],
                    },
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
        "description": "School clubs, arts, music, sport, and leadership roles help students build confidence, friendship, service, and expression.",
        "hero_image": PUBLIC_IMAGE["sports"],
        "sections": [
            {
                "layout": "cards",
                "title": "Clubs, arts, sports, and formation",
                "cards": [
                    {"title": "School Clubs", "text": "Students join clubs that extend interest, leadership, service, and friendship.", "items": ["Creative Writing", "Science Club", "Math Club", "Debating", "Press", "French Club", "Gardening", "Justice and Peace"]},
                    {"title": "Religious Societies", "text": "Students grow in faith through guided participation and spiritual formation.", "items": ["Sacred Heart of Jesus", "Legion of Mary", "Small Christian Community", "Catechism Classes"]},
                    {"title": "Music, Drama & Art", "text": "Creative spaces build confidence, voice, imagination, and disciplined practice."},
                    {"title": "Sports & Recreation", "text": "Basketball, volleyball, table tennis, badminton, and inter-house competition support healthy student development."},
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
        "description": "A clear admissions path for families seeking strong academics, disciplined boarding life, and a Catholic girls' school environment.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "timeline",
                "title": "Admission process",
                "timeline": [
                    {"title": "Register online", "text": "Complete applicant and parent details and upload key records."},
                    {"title": "Review fees and payment guidance", "text": "Families receive the approved fee path and payment guidance from the school."},
                    {"title": "Entrance examination or screening", "text": "Applicants are assessed in line with the school's admission process."},
                    {"title": "Admission review and activation", "text": "Successful applicants receive confirmation and next steps."},
                ],
            },
            {
                "layout": "cards",
                "title": "Entrance examination subjects",
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
        "description": "A simple guide to preparing, registering, sitting for screening, and completing admission requirements.",
        "hero_image": PUBLIC_IMAGE["campus"],
        "sections": [
            {
                "layout": "timeline",
                "title": "How families move through admissions",
                "timeline": [
                    {"title": "Choose the class level", "text": "Applications are open for JSS1, JSS2, SS1, and SS2 where spaces are available."},
                    {"title": "Prepare the required documents", "text": "Recent school result, birth certificate, and passport photograph should be ready."},
                    {"title": "Complete the online registration", "text": "Submit the form with parent or guardian details and student information."},
                    {"title": "Sit for screening", "text": "Applicants take the written examination and any required interview stage."},
                    {"title": "Confirm admission", "text": "Successful candidates complete the acceptance and fee process."},
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
        "description": "Families should be able to understand how fees are organised by class, boarding status, and other approved charges.",
        "hero_image": PUBLIC_IMAGE["campus_block"],
        "sections": [
            {
                "layout": "table",
                "title": "Class-by-class fee structure",
                "intro": "The school organises fees by class level so families can plan with clarity. The latest approved figure for each row is issued directly by the admissions office and bursary.",
                "columns": ["Class", "Tuition / School Fees", "Boarding / Hostel", "Other Charges"],
                "rows": [
                    ["JSS1", "Available from admissions office", "Available from admissions office", "Registration, uniforms, and approved extras where applicable"],
                    ["JSS2", "Available from admissions office", "Available from admissions office", "Class-based approved charges where applicable"],
                    ["JSS3", "Available from admissions office", "Available from admissions office", "Class-based approved charges where applicable"],
                    ["SS1", "Available from admissions office", "Available from admissions office", "Exam and approved class charges where applicable"],
                    ["SS2", "Available from admissions office", "Available from admissions office", "Exam and approved class charges where applicable"],
                    ["SS3", "Available from admissions office", "Available from admissions office", "Exam and approved class charges where applicable"],
                ],
            },
            {
                "layout": "cards",
                "title": "Fee guidance",
                "cards": [
                    {"title": "School Fees", "text": "Core tuition and class charges are issued by level for each student group."},
                    {"title": "Boarding", "text": "Boarding and hostel fees are shown separately from other school charges."},
                    {"title": "Other Approved Charges", "text": "Uniforms, examinations, and related approved items are clarified during admissions."},
                    {"title": "Payment Information", "text": "Payment guidance is shared through approved school channels and follow-up communication."},
                ],
            }
        ],
    },
    "hostel-boarding": {
        "title": "Hostel & Boarding",
        "eyebrow": "Boarding",
        "description": "Boarding at NDGA is built around routine, supervision, student welfare, and a calm atmosphere for study and formation.",
        "hero_image": PUBLIC_IMAGE["hostel"],
        "sections": [
            {
                "layout": "split",
                "title": "A supervised boarding environment for girls",
                "body": [
                    "The school is committed to boarding life that supports routine, study, prayer, rest, and healthy community living. Girls are assigned within a structured house and supervision system.",
                    "The hostel is organised to support welfare, communication with home, orderly daily living, and the personal growth of students within a calm school atmosphere.",
                ],
                "image": PUBLIC_IMAGE["hostel_alt"],
            },
            {
                "layout": "cards",
                "title": "What families expect from boarding",
                "cards": [
                    {"title": "Student Welfare", "text": "Close supervision, routines, and attention to wellbeing."},
                    {"title": "Study Support", "text": "Evening prep and a culture of responsible academic routine."},
                    {"title": "Communication", "text": "The school keeps close contact with parents and guardians."},
                    {"title": "Boarding Facilities", "text": "Spacious hostel accommodation, ventilation, and regular water supply."},
                ],
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
        "description": "Boarding, worship, sports, clubs, leadership, and community life shape how girls grow at NDGA.",
        "hero_image": PUBLIC_IMAGE["socials"],
        "sections": [
            {
                "layout": "cards",
                "title": "Life beyond the classroom",
                "cards": [
                    {"title": "Boarding Life", "text": "House life, prep, rest, welfare, and daily routine.", "image": PUBLIC_IMAGE["hostel"], "href": "/hostel-boarding/"},
                    {"title": "Spiritual Life", "text": "Assemblies, worship, retreats, liturgy, and faith formation remain central.", "image": PUBLIC_IMAGE["assembly"], "href": "/about/school-life/"},
                    {"title": "Clubs & Leadership", "text": "Students grow through clubs, service, responsibility, and peer interaction.", "image": PUBLIC_IMAGE["socials"], "href": "/academics/co-curricular-activities/"},
                    {"title": "Sports & Recreation", "text": "Basketball, volleyball, badminton, table tennis, and inter-house competition.", "image": PUBLIC_IMAGE["sports"], "href": "/facilities/"},
                ],
            }
        ],
    },
    "facilities": {
        "title": "Facilities",
        "eyebrow": "Facilities",
        "description": "The school environment is designed to support learning, practical work, boarding life, reading, recreation, and orderly daily routine.",
        "hero_image": PUBLIC_IMAGE["campus_block"],
        "sections": [
            {
                "layout": "cards",
                "title": "Spaces designed to support school life",
                "cards": [
                    {"title": "Science Laboratories", "text": "Laboratories for science and practical learning.", "image": PUBLIC_IMAGE["science_lab"]},
                    {"title": "ICT / CBT Lab", "text": "Computer learning and CBT-ready digital spaces.", "image": PUBLIC_IMAGE["computer_lab"]},
                    {"title": "Library", "text": "A reading and study space that supports revision and quiet work.", "image": PUBLIC_IMAGE["library"]},
                    {"title": "Sports Areas", "text": "Spaces for basketball, volleyball, badminton, and student recreation.", "image": PUBLIC_IMAGE["sports"]},
                    {"title": "Hostel & Boarding Areas", "text": "Student accommodation and welfare spaces within the boarding routine.", "image": PUBLIC_IMAGE["hostel_alt"]},
                    {"title": "Refectory & Campus", "text": "Shared spaces and physical environment that support daily school life.", "image": PUBLIC_IMAGE["campus_refectory"]},
                ],
            }
        ],
    },
    "gallery": {
        "title": "Gallery",
        "eyebrow": "Gallery",
        "description": "Explore NDGA through category-based albums covering academics, facilities, boarding, school life, sports, and community moments.",
        "hero_image": PUBLIC_IMAGE["pioneers"],
        "sections": [
            {
                "layout": "list",
                "title": "Gallery categories",
                "items": [
                    "Campus & Facilities",
                    "Classroom Learning",
                    "Science & ICT",
                    "Boarding Life",
                    "Sports & Games",
                    "Clubs & Activities",
                    "Faith & Formation",
                    "Events & Celebrations",
                ],
            }
        ],
    },
    "news": {
        "title": "News",
        "eyebrow": "News",
        "description": "A curated stream of school notices, admissions updates, girls' education perspectives, and community highlights.",
        "hero_image": PUBLIC_IMAGE["assembly"],
        "sections": [],
    },
    "events": {
        "title": "Events",
        "eyebrow": "Events",
        "description": "Key dates for admissions, resumption, orientation, and the school calendar.",
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
    {"label": "Hostel & Boarding", "url": "/hostel-boarding/", "group": "Explore"},
    {"label": "Facilities", "url": "/facilities/", "group": "Explore"},
    {"label": "Gallery", "url": "/gallery/", "group": "Explore"},
    {"label": "Campus & Facilities Album", "url": "/gallery/campus-facilities/", "group": "Gallery"},
    {"label": "Science & ICT Album", "url": "/gallery/science-ict/", "group": "Gallery"},
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
    "/gallery/campus-facilities/",
    "/gallery/classroom-learning/",
    "/gallery/science-ict/",
    "/gallery/boarding-life/",
    "/gallery/sports-games/",
    "/gallery/clubs-activities/",
    "/gallery/faith-formation/",
    "/gallery/events-celebrations/",
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


def get_public_gallery_category(slug: str):
    for item in PUBLIC_GALLERY:
        if item["slug"] == slug:
            return deepcopy(item)
    return None


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
        "public_live_chat_url": "/live-chat/",
    }
