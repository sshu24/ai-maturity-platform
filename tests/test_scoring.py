import pytest

from app.components.question_engine import (
    Dimension, Question, QuestionBank, QuestionOption, _validate_bank, load_question_bank,
)
from app.components.scoring import _score_to_tier, compute_scorecard


def _question(qid, weight=1.0):
    options = [QuestionOption(label=str(v), value=v) for v in range(1, 6)]
    return Question(id=qid, text=qid, type="multiple_choice", weight=weight, options=options)


def _bank(dimensions):
    return QuestionBank(
        version="test",
        total_questions=sum(len(d.questions) for d in dimensions),
        dimensions=dimensions,
    )


# ------------------------------------------------------------------
# Question bank
# ------------------------------------------------------------------

def test_question_bank_matches_metadata():
    bank = load_question_bank()
    assert len(bank.dimensions) == 6
    assert bank.total_questions == 42
    assert all(len(d.questions) == 7 for d in bank.dimensions)


def test_validate_rejects_duplicate_question_ids():
    dim = Dimension(id="d", label="D", description="", weight=1.0,
                    questions=[_question("q1"), _question("q1")])
    with pytest.raises(ValueError, match="Duplicate"):
        _validate_bank(_bank([dim]))


def test_validate_rejects_non_sequential_option_values():
    q = _question("q1")
    q.options = [QuestionOption(label="a", value=1), QuestionOption(label="b", value=3)]
    dim = Dimension(id="d", label="D", description="", weight=1.0, questions=[q])
    with pytest.raises(ValueError, match="sequential"):
        _validate_bank(_bank([dim]))


# ------------------------------------------------------------------
# Tiers
# ------------------------------------------------------------------

@pytest.mark.parametrize("score, tier, label", [
    (1.00, 1, "Ad Hoc"),
    (1.79, 1, "Ad Hoc"),
    (1.80, 2, "Developing"),
    (2.59, 2, "Developing"),
    (2.60, 3, "Defined"),
    (3.39, 3, "Defined"),
    (3.40, 4, "Managed"),
    (4.19, 4, "Managed"),
    (4.20, 5, "Optimizing"),
    (5.00, 5, "Optimizing"),
    (0.00, 1, "Ad Hoc"),
])
def test_score_to_tier_boundaries(score, tier, label):
    assert _score_to_tier(score) == (tier, label)


# ------------------------------------------------------------------
# Scorecard
# ------------------------------------------------------------------

def test_question_weights_affect_dimension_score():
    dim = Dimension(id="d", label="D", description="", weight=1.0,
                    questions=[_question("q1", weight=3.0), _question("q2", weight=1.0)])
    result = compute_scorecard(_bank([dim]), [
        {"question_id": "q1", "answer_value": 5},
        {"question_id": "q2", "answer_value": 1},
    ])
    # (5*3 + 1*1) / 4 = 4.0
    assert result.dimension_scores["d"] == 4.0
    assert result.maturity_tier == 4


def test_dimension_weights_affect_overall_score():
    heavy = Dimension(id="heavy", label="H", description="", weight=3.0, questions=[_question("h1")])
    light = Dimension(id="light", label="L", description="", weight=1.0, questions=[_question("l1")])
    result = compute_scorecard(_bank([heavy, light]), [
        {"question_id": "h1", "answer_value": 1},
        {"question_id": "l1", "answer_value": 5},
    ])
    # (1*3 + 5*1) / 4 = 2.0
    assert result.overall_score == 2.0
    assert result.maturity_label == "Developing"


def test_full_bank_all_threes_is_defined():
    bank = load_question_bank()
    responses = [
        {"question_id": q.id, "answer_value": 3}
        for d in bank.dimensions for q in d.questions
    ]
    result = compute_scorecard(bank, responses)
    assert result.overall_score == 3.0
    assert result.maturity_label == "Defined"
    assert set(result.dimension_scores) == set(bank.dimension_ids)
