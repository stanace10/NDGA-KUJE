from __future__ import annotations

from apps.cbt.models import CBTSimulationSourceProvider, CBTSimulationToolCategory


SUBJECT_ENGINE_MATRIX = [
    {
        "name": "Biology",
        "keywords": ["biology", "basic science", "health education"],
        "tool_categories": [CBTSimulationToolCategory.SCIENCE],
        "preferred_providers": [
            CBTSimulationSourceProvider.PHET,
            CBTSimulationSourceProvider.LABXCHANGE,
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["PhET", "LabXchange", "H5P"],
        "content_patterns": [
            "Diagram labeling",
            "Microscope/virtual lab practical",
            "Ecosystem and genetics simulation tasks",
        ],
    },
    {
        "name": "Chemistry",
        "keywords": ["chemistry"],
        "tool_categories": [CBTSimulationToolCategory.SCIENCE],
        "preferred_providers": [
            CBTSimulationSourceProvider.PHET,
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["PhET", "H5P"],
        "content_patterns": [
            "Balancing equations",
            "Acid/base and pH practical",
            "Atomic/molecular modeling",
        ],
    },
    {
        "name": "Physics",
        "keywords": ["physics", "basic technology", "electricity", "electronics"],
        "tool_categories": [
            CBTSimulationToolCategory.SCIENCE,
            CBTSimulationToolCategory.COMPUTER_SCIENCE,
        ],
        "preferred_providers": [
            CBTSimulationSourceProvider.PHET,
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["PhET", "H5P"],
        "content_patterns": [
            "Motion/waves/circuits practical",
            "Instrument and components labeling",
            "Interactive troubleshooting scenarios",
        ],
    },
    {
        "name": "Mathematics",
        "keywords": ["math", "mathematics", "further math", "statistics", "trigonometry", "geometry"],
        "tool_categories": [CBTSimulationToolCategory.MATHEMATICS],
        "preferred_providers": [
            CBTSimulationSourceProvider.PHET,
            CBTSimulationSourceProvider.GEOGEBRA,
            CBTSimulationSourceProvider.DESMOS,
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["GeoGebra", "Desmos", "H5P"],
        "content_patterns": [
            "Graphing and function analysis",
            "Geometry constructions",
            "Drag/drop concept reinforcement",
        ],
    },
    {
        "name": "Computer/ICT",
        "keywords": [
            "computer",
            "ict",
            "data processing",
            "programming",
            "coding",
            "information technology",
        ],
        "tool_categories": [CBTSimulationToolCategory.COMPUTER_SCIENCE],
        "preferred_providers": [
            CBTSimulationSourceProvider.PYODIDE,
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["Pyodide/Skulpt", "H5P", "Blockly/Scratch"],
        "content_patterns": [
            "Hardware/software labeling",
            "Coding sandbox practical",
            "Workflow sequencing",
        ],
    },
    {
        "name": "Business/Commercial",
        "keywords": [
            "accounting",
            "book keeping",
            "bookkeeping",
            "commerce",
            "economics",
            "marketing",
            "office practice",
            "entrepreneurship",
            "business",
            "financial accounting",
            "book-keeping",
            "store keeping",
        ],
        "tool_categories": [CBTSimulationToolCategory.BUSINESS],
        "preferred_providers": [CBTSimulationSourceProvider.H5P, CBTSimulationSourceProvider.OTHER],
        "engines": ["H5P", "Scenario Labs"],
        "content_patterns": [
            "Ledger/journal simulation tasks",
            "Case-study scenarios",
            "Matching and structured practicals",
        ],
    },
    {
        "name": "Agriculture",
        "keywords": [
            "agricultural science",
            "agriculture",
            "animal husbandry",
            "crop science",
            "fisheries",
            "forestry",
        ],
        "tool_categories": [
            CBTSimulationToolCategory.SCIENCE,
            CBTSimulationToolCategory.ARTS,
        ],
        "preferred_providers": [
            CBTSimulationSourceProvider.H5P,
            CBTSimulationSourceProvider.PHET,
            CBTSimulationSourceProvider.OTHER,
        ],
        "engines": ["H5P", "Virtual Labs"],
        "content_patterns": [
            "Farm planning and sequencing practicals",
            "Agric process and equipment identification",
            "Evidence/rubric-based practical scoring",
        ],
    },
    {
        "name": "Arts/Vocational",
        "keywords": [
            "home economics",
            "food",
            "nutrition",
            "clothing",
            "textiles",
            "fine art",
            "visual art",
            "music",
            "drama",
            "creative arts",
            "cultural",
            "technical drawing",
            "woodwork",
            "metalwork",
            "building construction",
            "visual arts",
        ],
        "tool_categories": [CBTSimulationToolCategory.ARTS],
        "preferred_providers": [CBTSimulationSourceProvider.H5P, CBTSimulationSourceProvider.OTHER],
        "engines": ["H5P", "Interactive Visual Labs"],
        "content_patterns": [
            "Image hotspots and drag/drop",
            "Interactive video and branching scenarios",
            "Rubric-based practical submissions",
        ],
    },
    {
        "name": "Humanities/Languages",
        "keywords": [
            "english",
            "literature",
            "history",
            "government",
            "civic",
            "geography",
            "crs",
            "irs",
            "irk",
            "yoruba",
            "hausa",
            "igbo",
            "french",
            "arabic",
            "social studies",
        ],
        "tool_categories": [CBTSimulationToolCategory.HUMANITIES],
        "preferred_providers": [CBTSimulationSourceProvider.H5P, CBTSimulationSourceProvider.OTHER],
        "engines": ["H5P", "Timeline/Map Simulations"],
        "content_patterns": [
            "Interactive timelines",
            "Language listening drills",
            "Scenario and essay preparation activities",
        ],
    },
]


DEFAULT_SUBJECT_PROFILE = {
    "name": "General",
    "tool_categories": [
        CBTSimulationToolCategory.SCIENCE,
        CBTSimulationToolCategory.MATHEMATICS,
        CBTSimulationToolCategory.ARTS,
        CBTSimulationToolCategory.HUMANITIES,
        CBTSimulationToolCategory.BUSINESS,
        CBTSimulationToolCategory.COMPUTER_SCIENCE,
    ],
    "preferred_providers": [
        CBTSimulationSourceProvider.PHET,
        CBTSimulationSourceProvider.GEOGEBRA,
        CBTSimulationSourceProvider.H5P,
        CBTSimulationSourceProvider.DESMOS,
        CBTSimulationSourceProvider.PYODIDE,
        CBTSimulationSourceProvider.LABXCHANGE,
        CBTSimulationSourceProvider.OTHER,
    ],
    "engines": ["PhET", "GeoGebra", "H5P"],
    "content_patterns": [
        "Objective and theory CBT tasks",
        "Practical simulation activities",
        "Structured scoring with auto/verify/rubric modes",
    ],
}


def _subject_name_tokens(subject):
    values = [getattr(subject, "name", ""), getattr(subject, "code", "")]
    combined = " ".join([item.lower().strip() for item in values if item]).strip()
    return combined


def resolve_subject_simulation_profile(subject):
    if subject is None:
        return DEFAULT_SUBJECT_PROFILE

    tokens = _subject_name_tokens(subject)
    for row in SUBJECT_ENGINE_MATRIX:
        if any(keyword in tokens for keyword in row["keywords"]):
            return row

    return DEFAULT_SUBJECT_PROFILE
