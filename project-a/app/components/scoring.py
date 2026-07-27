from dataclasses import dataclass, field
from app.components.question_engine import QuestionBank


# ------------------------------------------------------------------
# Tier definitions
# ------------------------------------------------------------------

MATURITY_TIERS = [
    (1.00, 1.79, 1, "Ad Hoc"),
    (1.80, 2.59, 2, "Developing"),
    (2.60, 3.39, 3, "Defined"),
    (3.40, 4.19, 4, "Managed"),
    (4.20, 5.00, 5, "Optimizing"),
]


@dataclass
class DimensionScore:
    id: str
    label: str
    score: float                      # 1.0 – 5.0
    tier: int
    tier_label: str
    question_scores: dict[str, float] = field(default_factory=dict)


@dataclass
class ScorecardResult:
    overall_score: float
    maturity_tier: int
    maturity_label: str
    dimension_scores: dict[str, float]   # {dimension_id: score}
    dimension_details: list[DimensionScore]


def _score_to_tier(score: float) -> tuple[int, str]:
    """Map a 1–5 score to a maturity tier and label."""
    for low, high, tier, label in MATURITY_TIERS:
        if low <= score <= high:
            return tier, label
    # Clamp edge cases
    if score < 1.0:
        return 1, "Ad Hoc"
    return 5, "Optimizing"


def compute_scorecard(
    bank: QuestionBank,
    responses: list[dict],
) -> ScorecardResult:
    """
    Compute the full scorecard from a list of response dicts.

    Each response dict must have:
        question_id: str
        answer_value: int   (1–5)

    Returns a ScorecardResult with dimension and overall scores.
    """
    # Index responses by question_id
    response_map: dict[str, int] = {
        r["question_id"]: r["answer_value"] for r in responses
    }

    dimension_details: list[DimensionScore] = []
    dimension_score_map: dict[str, float] = {}

    for dim in bank.dimensions:
        question_scores: dict[str, float] = {}
        weighted_sum = 0.0
        total_weight = 0.0

        for q in dim.questions:
            raw_value = response_map.get(q.id)
            if raw_value is None:
                # Should not happen after submit validation, but handle gracefully
                continue

            weighted_score = raw_value * q.weight
            question_scores[q.id] = round(raw_value * 1.0, 2)
            weighted_sum += weighted_score
            total_weight += q.weight

        dim_score = round(weighted_sum / total_weight, 2) if total_weight > 0 else 0.0
        tier, tier_label = _score_to_tier(dim_score)

        dimension_details.append(DimensionScore(
            id=dim.id,
            label=dim.label,
            score=dim_score,
            tier=tier,
            tier_label=tier_label,
            question_scores=question_scores,
        ))
        dimension_score_map[dim.id] = dim_score

    # Overall score — weighted average across dimensions
    if dimension_details:
        dim_weighted_sum = sum(
            d.score * bank.get_dimension(d.id).weight
            for d in dimension_details
        )
        dim_total_weight = sum(
            bank.get_dimension(d.id).weight
            for d in dimension_details
        )
        overall_score = round(dim_weighted_sum / dim_total_weight, 2)
    else:
        overall_score = 0.0

    overall_tier, overall_label = _score_to_tier(overall_score)

    return ScorecardResult(
        overall_score=overall_score,
        maturity_tier=overall_tier,
        maturity_label=overall_label,
        dimension_scores=dimension_score_map,
        dimension_details=dimension_details,
    )


def score_summary(result: ScorecardResult) -> dict:
    """
    Return a JSON-serialisable summary suitable for storing in the DB.
    """
    return {
        "overall_score": result.overall_score,
        "maturity_tier": result.maturity_tier,
        "maturity_label": result.maturity_label,
        "dimension_scores": result.dimension_scores,
        "dimension_details": [
            {
                "id": d.id,
                "label": d.label,
                "score": d.score,
                "tier": d.tier,
                "tier_label": d.tier_label,
            }
            for d in result.dimension_details
        ],
    }