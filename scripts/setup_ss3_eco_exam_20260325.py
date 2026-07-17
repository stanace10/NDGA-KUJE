from datetime import datetime
import base64
from decimal import Decimal
from pathlib import Path
from zoneinfo import ZoneInfo

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.academics.models import AcademicClass, AcademicSession, Subject, TeacherSubjectAssignment, Term
from apps.cbt.models import (
    CBTExamStatus,
    CBTExamType,
    CBTQuestionType,
    CBTWritebackTarget,
    CorrectAnswer,
    Exam,
    ExamBlueprint,
    ExamQuestion,
    Option,
    Question,
    QuestionBank,
)


TITLE = "WED 1:45-3:00 SS3 Economics Second Term Exam"
DESCRIPTION = "SS3 ECONOMICS SECOND TERM EXAMINATION"
BANK_NAME = "SS3 Economics Second Term Exam 2025/2026"
INSTRUCTIONS = (
    "Answer all objective questions in Section A. In Section B, answer one question. "
    "In Section C, answer any three questions. Timer is 75 minutes. "
    "Exam window closes at 3:00 PM WAT on Wednesday, March 25, 2026."
)

OBJECTIVE_TABLE_TEXT = (
    "Use the table below to answer Questions 1 and 2.\n"
    "Output (units): 50, 60, 70, 80, 90\n"
    "Total Revenue (N): 85, 102, 119, 136, 153"
)

OBJECTIVE_TABLE_HTML = """
<p><strong>Use the table below to answer Questions 1 and 2.</strong></p>
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr>
    <th>Output (units)</th>
    <td>50</td>
    <td>60</td>
    <td>70</td>
    <td>80</td>
    <td>90</td>
  </tr>
  <tr>
    <th>Total Revenue (N)</th>
    <td>85</td>
    <td>102</td>
    <td>119</td>
    <td>136</td>
    <td>153</td>
  </tr>
</table>
"""


def _exam_assets_root():
    return Path.cwd() / "EXAM"


def _image_data_uri(image_name):
    image_path = _exam_assets_root() / image_name
    if not image_path.exists():
        raise FileNotFoundError(f"Missing exam image: {image_path}")
    encoded = base64.b64encode(image_path.read_bytes()).decode("ascii")
    return f"data:image/png;base64,{encoded}"


def _rich_block_with_image(text, *, image_name, caption=""):
    body = "<br>".join(text.splitlines())
    image_url = _image_data_uri(image_name)
    caption_html = (
        f"<figcaption style=\"margin-top:8px;font-size:0.9rem;color:#475569;\">{caption}</figcaption>"
        if caption
        else ""
    )
    return (
        f"<div>{body}</div>"
        f"<figure class=\"cbt-inline-figure\" style=\"margin-top:12px;\">"
        f"<img src=\"{image_url}\" alt=\"Question diagram\" "
        f"style=\"max-width:100%;height:auto;border:1px solid #cbd5e1;border-radius:12px;padding:8px;background:#fff;\">"
        f"{caption_html}"
        f"</figure>"
    )

SECTION_B_TABLE_TEXT = (
    "No of Workers | Total Product | Marginal Product | Average Product\n"
    "0 | 0 | 0 | 0\n"
    "1 | 20 | 20 | 20\n"
    "2 | 50 | 30 | Z\n"
    "3 | 70 | 20 | 23.3\n"
    "4 | 80 | Y | 20\n"
    "5 | 80 | 0 | 16\n"
    "6 | X | -9.8 | 11.7"
)

SECTION_B_TABLE_HTML = """
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr>
    <th>No of Workers</th>
    <th>Total Product</th>
    <th>Marginal Product</th>
    <th>Average Product</th>
  </tr>
  <tr><td>0</td><td>0</td><td>0</td><td>0</td></tr>
  <tr><td>1</td><td>20</td><td>20</td><td>20</td></tr>
  <tr><td>2</td><td>50</td><td>30</td><td>Z</td></tr>
  <tr><td>3</td><td>70</td><td>20</td><td>23.3</td></tr>
  <tr><td>4</td><td>80</td><td>Y</td><td>20</td></tr>
  <tr><td>5</td><td>80</td><td>0</td><td>16</td></tr>
  <tr><td>6</td><td>X</td><td>-9.8</td><td>11.7</td></tr>
</table>
"""

SECTION_B2_TABLE_TEXT = (
    "Income (N) | Quantity Demanded (Kg)\n"
    "20,000 | 120\n"
    "36,000 | 96\n"
    "40,000 | 160\n"
    "44,000 | 200\n"
    "45,000 | 240\n"
    "47,000 | 252"
)

SECTION_B2_TABLE_HTML = """
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr>
    <th>Income (N)</th>
    <th>Quantity Demanded (Kg)</th>
  </tr>
  <tr><td>20,000</td><td>120</td></tr>
  <tr><td>36,000</td><td>96</td></tr>
  <tr><td>40,000</td><td>160</td></tr>
  <tr><td>44,000</td><td>200</td></tr>
  <tr><td>45,000</td><td>240</td></tr>
  <tr><td>47,000</td><td>252</td></tr>
</table>
"""

SECTION_C5_TABLE_TEXT = (
    "Quantity of eggs (in crates) | Total cost (N)\n"
    "0 | 50\n"
    "1 | 55\n"
    "2 | 62\n"
    "3 | 75\n"
    "4 | 96\n"
    "5 | 125\n"
    "6 | 162\n"
    "7 | 203\n"
    "8 | 248"
)

SECTION_C5_TABLE_HTML = """
<table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;">
  <tr>
    <th>Quantity of eggs (in crates)</th>
    <th>Total cost (N)</th>
  </tr>
  <tr><td>0</td><td>50</td></tr>
  <tr><td>1</td><td>55</td></tr>
  <tr><td>2</td><td>62</td></tr>
  <tr><td>3</td><td>75</td></tr>
  <tr><td>4</td><td>96</td></tr>
  <tr><td>5</td><td>125</td></tr>
  <tr><td>6</td><td>162</td></tr>
  <tr><td>7</td><td>203</td></tr>
  <tr><td>8</td><td>248</td></tr>
</table>
"""

OBJECTIVES = [
    {
        "stem": "What is the unit price of the firm's output?",
        "rich_prefix": _rich_block_with_image(
            "Use the table below to answer Questions 1 and 2.",
            image_name="question 1 and 2.png",
            caption="Revenue table for Questions 1 and 2",
        ),
        "plain_prefix": OBJECTIVE_TABLE_TEXT,
        "options": {"A": "10.00", "B": "2.70", "C": "2.00", "D": "1.70"},
        "answer": "D",
    },
    {
        "stem": "What is the firm's marginal revenue?",
        "rich_prefix": _rich_block_with_image(
            "Use the table below to answer Questions 1 and 2.",
            image_name="question 1 and 2.png",
            caption="Revenue table for Questions 1 and 2",
        ),
        "plain_prefix": OBJECTIVE_TABLE_TEXT,
        "options": {"A": "153", "B": "17", "C": "10", "D": "1.7"},
        "answer": "D",
    },
    {"stem": "The concept of scarcity implies that ______.", "options": {"A": "wants are limited", "B": "resources are unlimited", "C": "wants exceed available resources", "D": "production is constant"}, "answer": "C"},
    {"stem": "A point inside the production possibility curve indicates ______.", "options": {"A": "efficiency", "B": "inefficiency", "C": "full employment", "D": "equilibrium"}, "answer": "B"},
    {"stem": "Opportunity cost increases because of ______.", "options": {"A": "specialization", "B": "increasing returns", "C": "diminishing returns", "D": "fixed costs"}, "answer": "C"},
    {"stem": "Economic goods are goods that are ______.", "options": {"A": "abundant", "B": "scarce and useful", "C": "free", "D": "unlimited"}, "answer": "B"},
    {"stem": "The central problem of 'how to produce' relates to ______.", "options": {"A": "method of production", "B": "allocation", "C": "distribution", "D": "consumption"}, "answer": "A"},
    {"stem": "Capital formation involves ______.", "options": {"A": "consumption", "B": "savings and investment", "C": "taxation", "D": "importation"}, "answer": "B"},
    {"stem": "A mixed economy combines ______.", "options": {"A": "agriculture and industry", "B": "private and public sectors", "C": "exports and imports", "D": "labour and capital"}, "answer": "B"},
    {"stem": "Microeconomics studies ______.", "options": {"A": "economy as a whole", "B": "individual units", "C": "global trade", "D": "inflation"}, "answer": "B"},
    {"stem": "Macroeconomics studies ______.", "options": {"A": "firms", "B": "households", "C": "aggregates", "D": "individuals"}, "answer": "C"},
    {"stem": "Which of the following may make the demand for a normal good X shift from D1D1 to D2D2 (to the right)?", "options": {"A": "fall in income of consumer", "B": "rise in price of substitute", "C": "rise in price of complement", "D": "fall in the demand of commodity X"}, "answer": "B"},
    {"stem": "A rational consumer aims to ______.", "options": {"A": "minimize utility", "B": "maximize satisfaction", "C": "reduce income", "D": "avoid goods"}, "answer": "B"},
    {"stem": "The law of diminishing marginal utility states that ______.", "options": {"A": "utility increases constantly", "B": "utility decreases with consumption", "C": "utility is fixed", "D": "utility doubles"}, "answer": "B"},
    {"stem": "Total utility is maximum when marginal utility is ______.", "options": {"A": "zero", "B": "negative", "C": "positive", "D": "constant"}, "answer": "A"},
    {"stem": "Indifference curve shows ______.", "options": {"A": "production", "B": "cost", "C": "combinations giving equal satisfaction", "D": "price levels"}, "answer": "C"},
    {"stem": "A good is said to be inferior if its demand ______.", "options": {"A": "decreases as price falls", "B": "increases as income increases", "C": "decreases as income rises", "D": "increases as price rises"}, "answer": "C"},
    {"stem": "The function of a wholesaler that allows it to stabilize price is ______.", "options": {"A": "warehousing goods", "B": "advertising goods", "C": "granting credit to retailer", "D": "transporting goods"}, "answer": "A"},
    {"stem": "An increase in the price of crude oil led to an increase in the prices of kerosene and grease; kerosene and grease are said to be ______.", "options": {"A": "competitive supply", "B": "joint supply", "C": "market supply", "D": "composite supply"}, "answer": "B"},
    {"stem": "Supply increases when ______.", "options": {"A": "cost rises", "B": "technology improves", "C": "tax increases", "D": "price falls"}, "answer": "B"},
    {"stem": "A seller increases the quantity offered for sale from 200 units to 250 units when the price of his product increased by 12.5%. What is the price elasticity of supply?", "options": {"A": "2.00", "B": "1.50", "C": "1.00", "D": "0.50"}, "answer": "A"},
    {"stem": "If the average fixed cost (AFC) of producing 5 bags of rice is N20, the average fixed cost of producing 10 bags will be ______.", "options": {"A": "N2", "B": "N4", "C": "N10", "D": "N20"}, "answer": "C"},
    {"stem": "When both demand and supply increase, price will ______.", "options": {"A": "always rise", "B": "always fall", "C": "be indeterminate", "D": "be zero"}, "answer": "C"},
    {"stem": "Labour productivity is defined as ______.", "options": {"A": "output per man hour", "B": "average output", "C": "maximum number of hours worked", "D": "total output of labour"}, "answer": "A"},
    {"stem": "The location of iron and steel at a place is due to ______.", "options": {"A": "easy access to raw materials", "B": "easy access to cheap labour", "C": "government policy", "D": "good infrastructure"}, "answer": "A"},
    {"stem": "Which of the following are intermediate products?", "options": {"A": "cement and steel", "B": "furniture and shirt", "C": "handkerchief and shoe", "D": "table and door"}, "answer": "A"},
    {"stem": "How is NNP at factor cost derived from GNP at market price?", "options": {"A": "GNP - Depreciation + Indirect taxes + Subsidies", "B": "GNP - Depreciation - Indirect taxes + Subsidies", "C": "GNP - Depreciation + Indirect taxes - Subsidies", "D": "GNP + Depreciation - Indirect taxes + Subsidies"}, "answer": "B"},
    {"stem": "Government in West Africa can curtail inflation by ______.", "options": {"A": "selling securities in the open market", "B": "purchasing securities in the open market", "C": "encouraging importation of goods from all countries", "D": "encouraging banks to lend"}, "answer": "A"},
    {"stem": "Mr X and Mrs Y pay N500 and N1400 as taxes on their earnings of N5000 and N7000 respectively. The type of tax employed is ______.", "options": {"A": "specific tax", "B": "regressive tax", "C": "proportional tax", "D": "progressive tax"}, "answer": "D"},
    {"stem": "A country is allowed to import 50,000 tonnes of rice annually. This describes ______.", "options": {"A": "devaluation", "B": "tariff", "C": "embargo", "D": "quota"}, "answer": "D"},
    {"stem": "Dumping is selling goods in a foreign market at a price ______.", "options": {"A": "it is sold at home market", "B": "equal to the cost of production", "C": "below the price at home market", "D": "above the price at home market"}, "answer": "C"},
    {"stem": "Income elasticity for luxury goods is ______.", "options": {"A": "negative", "B": "zero", "C": "greater than 1", "D": "less than 1"}, "answer": "C"},
    {"stem": "A subsidy causes the supply curve to shift ______.", "options": {"A": "left", "B": "right", "C": "upward", "D": "downward"}, "answer": "B"},
    {"stem": "Tax on goods shifts the supply curve ______.", "options": {"A": "right", "B": "left", "C": "downward", "D": "horizontal"}, "answer": "B"},
    {"stem": "Consumer surplus is ______.", "options": {"A": "price paid", "B": "extra benefit", "C": "cost", "D": "loss"}, "answer": "B"},
    {"stem": "Diminishing returns begin when ______.", "options": {"A": "MP rises", "B": "MP falls", "C": "TP rises", "D": "TP is constant"}, "answer": "B"},
    {"stem": "Fixed cost includes ______.", "options": {"A": "wages", "B": "raw materials", "C": "rent", "D": "fuel"}, "answer": "C"},
    {"stem": "MC curve intersects AC at ______.", "options": {"A": "minimum AC", "B": "maximum AC", "C": "zero", "D": "constant"}, "answer": "A"},
    {"stem": "When MC is less than AC, AC is ______.", "options": {"A": "rising", "B": "falling", "C": "constant", "D": "zero"}, "answer": "B"},
    {"stem": "Total revenue equals ______.", "options": {"A": "P x Q", "B": "P + Q", "C": "Q/P", "D": "P - Q"}, "answer": "A"},
    {"stem": "Economies of scale arise due to ______.", "options": {"A": "large production", "B": "small production", "C": "no production", "D": "scarcity"}, "answer": "A"},
    {"stem": "A firm in perfect competition is a ______.", "options": {"A": "price maker", "B": "price taker", "C": "monopolist", "D": "regulator"}, "answer": "B"},
    {"stem": "Monopoly demand curve is ______.", "options": {"A": "horizontal", "B": "downward", "C": "vertical", "D": "upward"}, "answer": "B"},
    {"stem": "Oligopoly firms are ______.", "options": {"A": "interdependent", "B": "independent", "C": "isolated", "D": "fixed"}, "answer": "A"},
    {"stem": "Collusion occurs in ______.", "options": {"A": "monopoly", "B": "oligopoly", "C": "perfect competition", "D": "agriculture"}, "answer": "B"},
    {"stem": "Product differentiation is common in ______.", "options": {"A": "monopoly", "B": "monopolistic competition", "C": "perfect competition", "D": "socialism"}, "answer": "B"},
    {"stem": "Barriers to entry include ______.", "options": {"A": "patents", "B": "wages", "C": "rent", "D": "cost"}, "answer": "A"},
    {"stem": "Price discrimination means ______.", "options": {"A": "same price", "B": "different prices", "C": "no price", "D": "fixed price"}, "answer": "B"},
    {"stem": "Natural monopoly arises due to ______.", "options": {"A": "high cost", "B": "low cost", "C": "demand", "D": "labour"}, "answer": "A"},
    {"stem": "A cartel is ______.", "options": {"A": "an agreement among firms", "B": "government policy", "C": "tax system", "D": "labour union"}, "answer": "A"},
    {"stem": "Long-run profit in perfect competition is ______.", "options": {"A": "supernormal", "B": "normal", "C": "loss", "D": "zero output"}, "answer": "B"},
    {"stem": "Real GDP adjusts for ______.", "options": {"A": "population", "B": "inflation", "C": "income", "D": "tax"}, "answer": "B"},
    {"stem": "Balance of trade deficit implies that a country is ______.", "options": {"A": "importing more than she is exporting", "B": "consuming more than she is producing", "C": "living below her means", "D": "more productive than others"}, "answer": "A"},
    {"stem": "Deflation leads to ______.", "options": {"A": "rising prices", "B": "falling prices", "C": "inflation", "D": "growth"}, "answer": "B"},
    {"stem": "Central bank controls money using ______.", "options": {"A": "interest rate", "B": "labour", "C": "land", "D": "exports"}, "answer": "A"},
    {"stem": "Which of the following is not a member of ECOWAS?", "options": {"A": "Ghana", "B": "Cameroun", "C": "Gambia", "D": "Guinea Bissau"}, "answer": "B"},
    {"stem": "Balance of trade is ______.", "options": {"A": "exports - imports", "B": "imports - exports", "C": "income - cost", "D": "GDP - GNP"}, "answer": "A"},
    {"stem": "Devaluation makes exports ______.", "options": {"A": "cheaper", "B": "expensive", "C": "constant", "D": "zero"}, "answer": "A"},
    {"stem": "Protectionism includes ______.", "options": {"A": "free trade", "B": "tariffs", "C": "exports", "D": "loans"}, "answer": "B"},
    {"stem": "Comparative advantage explains ______.", "options": {"A": "inflation", "B": "specialization", "C": "unemployment", "D": "taxation"}, "answer": "B"},
]

THEORY = [
    {
        "stem": (
            "1. " + SECTION_B_TABLE_TEXT + "\n\n"
            "a. Calculate the value of X, Y and Z.\n"
            "b. At what level of labour does the firm experience:\n"
            "   i. Increasing returns\n"
            "   ii. Decreasing returns\n"
            "   iii. Negative returns\n"
            "c. State the law of diminishing returns.\n"
            "d. On a graph sheet, draw the graph of total product and marginal product.\n"
            "e. State any two relationships between the two curves in d(i) above."
        ),
        "rich_stem": (
            _rich_block_with_image(
                "1.",
                image_name="section b question 1.png",
                caption="Section B Question 1 table",
            )
            + "<p>a. Calculate the value of X, Y and Z.</p>"
            + "<p>b. At what level of labour does the firm experience:<br>"
            + "i. Increasing returns<br>ii. Decreasing returns<br>iii. Negative returns</p>"
            + "<p>c. State the law of diminishing returns.</p>"
            + "<p>d. On a graph sheet, draw the graph of total product and marginal product.</p>"
            + "<p>e. State any two relationships between the two curves in d(i) above.</p>"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "2. What is income elasticity of demand?\n"
            + SECTION_B2_TABLE_TEXT
            + "\n\nb. Calculate the income elasticity between:\n"
            "   (i) A and B\n"
            "   (ii) C and D\n"
            "   (iii) E and F\n"
            "c. What kind of good is between:\n"
            "   (i) A and B\n"
            "   (ii) C and D"
        ),
        "rich_stem": (
            _rich_block_with_image(
                "2. What is income elasticity of demand?",
                image_name="question 2 theory.png",
                caption="Income and quantity demanded table",
            )
            + "<p>b. Calculate the income elasticity between:<br>"
            + "(i) A and B<br>(ii) C and D<br>(iii) E and F</p>"
            + "<p>c. What kind of good is between:<br>(i) A and B<br>(ii) C and D</p>"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": "3. Explain each of the following:\n(a) Indigenization policy\n(b) Localization of industry\n(c) Economies of scale\n(d) National budget",
        "rich_stem": "3. Explain each of the following:<br>(a) Indigenization policy<br>(b) Localization of industry<br>(c) Economies of scale<br>(d) National budget",
        "marks": Decimal("10.00"),
    },
    {
        "stem": "4. (a) Explain unemployment.\n(b) Explain any three types of unemployment.",
        "rich_stem": "4. (a) Explain unemployment.<br>(b) Explain any three types of unemployment.",
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "5. " + SECTION_C5_TABLE_TEXT + "\n\n"
            "(a) What is the fixed cost of the farm?\n"
            "(b) Calculate the marginal cost at each level of output.\n"
            "(c) What is the profit maximizing output?\n"
            "(d) Draw the demand curve for the farm."
        ),
        "rich_stem": (
            _rich_block_with_image(
                "5.",
                image_name="question 5 theory.png",
                caption="Quantity of eggs and total cost table",
            )
            + "<p>(a) What is the fixed cost of the farm?</p>"
            + "<p>(b) Calculate the marginal cost at each level of output.</p>"
            + "<p>(c) What is the profit maximizing output?</p>"
            + "<p>(d) Draw the demand curve for the farm.</p>"
        ),
        "marks": Decimal("10.00"),
    },
    {
        "stem": (
            "6. (a) Give three differences between light and heavy industry.\n"
            "(b) Explain with examples the following types of production:\n"
            "   (i) Primary production\n"
            "   (ii) Secondary production\n"
            "   (iii) Tertiary production\n"
            "(c) Give two reasons why primary production dominates West Africa."
        ),
        "rich_stem": (
            "6. (a) Give three differences between light and heavy industry.<br>"
            "(b) Explain with examples the following types of production:<br>"
            "(i) Primary production<br>(ii) Secondary production<br>(iii) Tertiary production<br>"
            "(c) Give two reasons why primary production dominates West Africa."
        ),
        "marks": Decimal("10.00"),
    },
]


def _objective_stem(item):
    prefix = item.get("plain_prefix")
    if prefix:
        return f"{prefix}\n\n{item['stem']}"
    return item["stem"]


def _objective_rich_stem(item):
    prefix = item.get("rich_prefix")
    if prefix:
        return f"{prefix}<p>{item['stem']}</p>"
    return item["stem"]


@transaction.atomic
def main():
    session = AcademicSession.objects.get(name="2025/2026")
    term = Term.objects.get(session=session, name="SECOND")
    academic_class = AcademicClass.objects.get(code="SS3")
    subject = Subject.objects.get(code="ECO")
    assignment = TeacherSubjectAssignment.objects.get(
        teacher__username="fadumo@ndgakuje.org",
        academic_class=academic_class,
        subject=subject,
        session=session,
        term=term,
        is_active=True,
    )
    teacher = assignment.teacher
    dean_user = User.objects.get(username="principal@ndgakuje.org")
    it_user = User.objects.get(username="admin@ndgakuje.org")

    lagos = ZoneInfo("Africa/Lagos")
    schedule_start = datetime(2026, 3, 25, 13, 45, tzinfo=lagos)
    schedule_end = datetime(2026, 3, 25, 15, 0, tzinfo=lagos)

    bank, _ = QuestionBank.objects.get_or_create(
        owner=teacher,
        name=BANK_NAME,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={"description": DESCRIPTION, "assignment": assignment, "is_active": True},
    )
    bank.description = DESCRIPTION
    bank.assignment = assignment
    bank.is_active = True
    bank.save()

    exam, created = Exam.objects.get_or_create(
        title=TITLE,
        subject=subject,
        academic_class=academic_class,
        session=session,
        term=term,
        defaults={
            "description": DESCRIPTION,
            "exam_type": CBTExamType.EXAM,
            "status": CBTExamStatus.ACTIVE,
            "created_by": teacher,
            "assignment": assignment,
            "question_bank": bank,
            "dean_reviewed_by": dean_user,
            "dean_reviewed_at": timezone.now(),
            "dean_review_comment": "Approved for Wednesday afternoon paper.",
            "activated_by": it_user,
            "activated_at": timezone.now(),
            "activation_comment": "Scheduled for Wednesday, March 25, 2026 1:45 PM WAT.",
            "schedule_start": schedule_start,
            "schedule_end": schedule_end,
            "is_time_based": True,
            "open_now": False,
            "is_free_test": False,
            "timer_is_paused": False,
        },
    )

    if exam.attempts.exists():
        raise RuntimeError(f"Exam {exam.id} already has attempts. Refusing to overwrite live content.")

    exam.description = DESCRIPTION
    exam.exam_type = CBTExamType.EXAM
    exam.status = CBTExamStatus.ACTIVE
    exam.created_by = teacher
    exam.assignment = assignment
    exam.question_bank = bank
    exam.dean_reviewed_by = dean_user
    exam.dean_reviewed_at = timezone.now()
    exam.dean_review_comment = "Approved for Wednesday afternoon paper."
    exam.activated_by = it_user
    exam.activated_at = timezone.now()
    exam.activation_comment = "Scheduled for Wednesday, March 25, 2026 1:45 PM WAT."
    exam.schedule_start = schedule_start
    exam.schedule_end = schedule_end
    exam.is_time_based = True
    exam.open_now = False
    exam.is_free_test = False
    exam.timer_is_paused = False
    exam.save()

    ExamQuestion.objects.filter(exam=exam).delete()
    bank.questions.all().delete()

    sort_order = 1
    for index, item in enumerate(OBJECTIVES, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.OBJECTIVE,
            stem=_objective_stem(item),
            rich_stem=_objective_rich_stem(item),
            marks=Decimal("1.00"),
            source_reference=f"SS3-ECO-20260325-OBJ-{index:02d}",
            is_active=True,
        )
        option_map = {}
        for option_index, label in enumerate(("A", "B", "C", "D"), start=1):
            option_map[label] = Option.objects.create(
                question=question,
                label=label,
                option_text=item["options"][label],
                sort_order=option_index,
            )
        answer = CorrectAnswer.objects.create(question=question, is_finalized=True)
        answer.correct_options.add(option_map[item["answer"]])
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=Decimal("1.00"))
        sort_order += 1

    for index, item in enumerate(THEORY, start=1):
        question = Question.objects.create(
            question_bank=bank,
            created_by=teacher,
            subject=subject,
            question_type=CBTQuestionType.SHORT_ANSWER,
            stem=item["stem"],
            rich_stem=item["rich_stem"],
            marks=item["marks"],
            source_reference=f"SS3-ECO-20260325-TH-{index:02d}",
            is_active=True,
        )
        CorrectAnswer.objects.create(question=question, note="", is_finalized=True)
        ExamQuestion.objects.create(exam=exam, question=question, sort_order=sort_order, marks=item["marks"])
        sort_order += 1

    blueprint, _ = ExamBlueprint.objects.get_or_create(exam=exam)
    blueprint.duration_minutes = 75
    blueprint.max_attempts = 1
    blueprint.shuffle_questions = True
    blueprint.shuffle_options = True
    blueprint.instructions = INSTRUCTIONS
    blueprint.section_config = {
        "paper_code": "SS3-ECO-EXAM",
        "flow_type": "OBJECTIVE_THEORY",
        "objective_count": len(OBJECTIVES),
        "theory_count": len(THEORY),
        "objective_target_max": "40.00",
        "theory_target_max": "60.00",
        "shared_prompt_objective_rows": [1, 2],
    }
    blueprint.passing_score = Decimal("0.00")
    blueprint.objective_writeback_target = CBTWritebackTarget.OBJECTIVE
    blueprint.theory_enabled = True
    blueprint.theory_writeback_target = CBTWritebackTarget.THEORY
    blueprint.auto_show_result_on_submit = False
    blueprint.finalize_on_logout = False
    blueprint.allow_retake = False
    blueprint.save()

    print(
        {
            "created": created,
            "exam_id": exam.id,
            "title": exam.title,
            "objective_count": len(OBJECTIVES),
            "theory_count": len(THEORY),
            "duration_minutes": blueprint.duration_minutes,
        }
    )


main()
