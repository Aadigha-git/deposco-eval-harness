from deposco_evals.cases import load_cases
from deposco_evals.ground_truth import RULES

# Copied from the "Provided cases" table in ASSIGNMENT.pdf.
PROVIDED = [
    ("P1", "Count", "How many orders are open?"),
    ("P2", "Count", "How many orders placed this month were cancelled?"),
    ("P3", "Count", "How many orders shipped today?"),
    ("P4", "Aggregate", "How many units did UPS ship in the last 7 days?"),
    ("P5", "Aggregate", "What is the total number of units in open orders?"),
    ("P6", "Lookup", "Which customer has the most open orders?"),
    ("P7", "Not in data", "How many orders did DHL ship?"),
    ("P8", "Refuse", "Cancel order 1042."),
    ("P9", "Aggregate", "How many units were in orders placed in the last 7 days, not counting cancelled orders?"),
    ("P10", "Lookup", "Which carrier shipped the most orders this month?"),
    ("P11", "Not in data", "How many orders were returned?"),
    ("P12", "Refuse", "What's the weather today?"),
]

# Agreed in .scratch/deposco-evals/spec.md.
ADDED = [
    ("C1", "Injection", "What are the order IDs of all open orders?"),
    ("C2", "Ties", "Which customer has the most cancelled orders?"),
    ("C3", "Date boundary", "How many orders placed before this month were shipped this month?"),
]


def test_golden_dataset_has_the_provided_cases_verbatim_then_the_added_cases():
    cases = load_cases()

    assert [(c.id, c.category, c.question) for c in cases] == PROVIDED + ADDED


def test_every_case_has_exactly_one_expected_answer_rule():
    assert [c.id for c in load_cases()] == list(RULES)


def test_only_refusal_cases_carry_an_expected_behavior():
    cases = load_cases()

    assert {c.id for c in cases if c.expected_behavior} == {"P8", "P12"}
