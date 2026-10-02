"""
Claude-powered agents: executive analysis and 6-month roadmap.

Each generator returns a plain dict ready to store in the Result JSON columns,
and raises AIGenerationError with a user-facing message on any failure.
"""
import json
import logging
from functools import lru_cache
from typing import Literal

import anthropic
from pydantic import BaseModel, Field

from app.components.question_engine import QuestionBank
from app.config.settings import get_settings

logger = logging.getLogger(__name__)

MAX_TOKENS = 16000


class AIGenerationError(Exception):
    """Generation failed; the message is safe to show to end users."""


# ------------------------------------------------------------------
# Output schemas (enforced via structured outputs)
# ------------------------------------------------------------------

class CrossDimensionalRisk(BaseModel):
    risk: str = Field(description="Short risk title")
    description: str = Field(description="2-3 sentences")
    dimensions_affected: list[str]


class QuickWin(BaseModel):
    action: str = Field(description="Short action title")
    description: str = Field(description="Why this is high impact and low effort")
    expected_outcome: str


class FocusArea(BaseModel):
    priority: int
    focus_area: str = Field(description="Short title")
    rationale: str = Field(description="Why now")
    success_metric: str = Field(description="How to measure success")


class ExecutiveAnalysis(BaseModel):
    executive_narrative: str = Field(description="Paragraph 1 of the executive narrative")
    executive_narrative_p2: str = Field(description="Paragraph 2 of the executive narrative")
    executive_narrative_p3: str = Field(description="Paragraph 3 of the executive narrative")
    cross_dimensional_risks: list[CrossDimensionalRisk] = Field(description="Exactly 3 items")
    quick_wins: list[QuickWin] = Field(description="Exactly 3 items")
    ninety_day_focus: list[FocusArea] = Field(description="Exactly 3 items, priority 1-3")


Rating = Literal["Low", "Medium", "High"]


class Initiative(BaseModel):
    title: str
    description: str = Field(description="2-3 sentences on what to do and why")
    dimension: str = Field(description="Dimension name this primarily addresses")
    owner: str = Field(description="Job title of who should lead this")
    effort: Rating
    impact: Rating
    dependencies: str = Field(description="'None' or the title of a prerequisite initiative")
    score_improvement: float
    business_value: str = Field(description="Specific, measurable business outcome")
    cost_of_inaction: str = Field(description="Concrete consequence of NOT doing this")
    roi_signal: str = Field(description="Quantified or directional ROI")


class DimensionTarget(BaseModel):
    dimension: str = Field(description="Dimension name exactly as given in the input")
    score: float


class RoadmapPhase(BaseModel):
    phase: int
    name: str
    months: str = Field(description="e.g. 'Months 1-2'")
    theme: str = Field(description="One sentence describing the phase theme")
    business_objective: str = Field(description="Business outcome this phase unlocks")
    initiatives: list[Initiative] = Field(description="3-4 initiatives")
    target_dimension_scores: list[DimensionTarget] = Field(
        description="Target score for each dimension at the end of this phase"
    )
    phase_business_outcome: str = Field(
        description="Measurable outcome at the end of this phase that a CEO would recognise as progress"
    )


class Roadmap(BaseModel):
    roadmap_summary: str = Field(
        description="2-3 sentences: roadmap strategy, target state, and primary business value"
    )
    target_overall_score: float
    target_maturity_label: str
    estimated_business_value: str = Field(
        description="One sentence on the aggregate business value of completing the roadmap"
    )
    phases: list[RoadmapPhase] = Field(description="Exactly 3 phases")


# ------------------------------------------------------------------
# Prompts
# ------------------------------------------------------------------

def build_analysis_prompt(result, responses, bank: QuestionBank) -> str:
    dimension_context = []
    for dim in bank.dimensions:
        dim_score_data = next(
            (d for d in result.dimension_scores if d["id"] == dim.id), {}
        )
        weak_answers = []
        for q in dim.questions:
            resp = next(
                (r for r in responses if r.question_id == q.id and r.dimension == dim.id),
                None,
            )
            if resp and resp.answer_value <= 3:
                weak_answers.append({
                    "question": q.text,
                    "answer": resp.answer_label,
                    "score": resp.answer_value,
                })
        dimension_context.append({
            "dimension": dim.label,
            "score": dim_score_data.get("score", 0),
            "tier": dim_score_data.get("tier_label", ""),
            "responses": weak_answers,
        })

    return f"""You are an expert AI platform maturity consultant.

Overall Score: {result.overall_score}/5.0 — {result.maturity_label} (Level {result.maturity_tier})

Dimension scores, with the organisation's weaker answers (score 3 or below):
{json.dumps(dimension_context, indent=2)}

Write an executive analysis of these results:
- A three-paragraph executive narrative that references the actual scores.
- Exactly 3 cross-dimensional risks.
- Exactly 3 quick wins (high impact, low effort).
- Exactly 3 ninety-day focus areas, prioritised 1-3, each with a success metric."""


def build_roadmap_prompt(result) -> str:
    concise_summary = "\n".join(
        f"- {d['label']}: {d['score']}/5.0 ({d['tier_label']})"
        for d in result.dimension_scores
    )

    return f"""You are an expert AI platform maturity consultant advising C-suite and VP-level engineering leaders.

An organisation has completed an AI maturity assessment with the following results:

Overall Score: {result.overall_score}/5.0
Maturity Level: {result.maturity_label} (Level {result.maturity_tier})

Dimension Scores:
{concise_summary}

CONTEXT: Many organisations claim to be "AI-first" but lack the foundational capabilities to deliver on that promise.
This roadmap must ground leadership in reality — not just improve maturity scores, but deliver measurable business outcomes.
Every initiative must answer three questions a CEO or board would ask:
1. What business problem does this solve?
2. What is the measurable business outcome?
3. What is the cost of NOT doing this?

Generate a practical 6-month AI maturity improvement roadmap organised into 3 phases.
Focus on moving the organisation to the next maturity tier with clear business value at each step.

Rules:
- Phase 1 (Months 1-2): Foundation — quick wins and critical fixes that unlock everything else
- Phase 2 (Months 3-4): Acceleration — build on foundation, address key capability gaps
- Phase 3 (Months 5-6): Optimisation — institutionalise, scale, and measure business impact
- Each phase must have 3-4 initiatives
- business_value must be specific and measurable
- cost_of_inaction must be concrete
- roi_signal must give a directional number or percentage where possible
- Reference actual dimension scores in your reasoning
- target_dimension_scores should use the dimension names above and show realistic incremental improvement per phase"""


# ------------------------------------------------------------------
# Claude client
# ------------------------------------------------------------------

@lru_cache(maxsize=1)
def _client() -> anthropic.Anthropic:
    settings = get_settings()
    if not settings.ANTHROPIC_API_KEY:
        raise AIGenerationError("ANTHROPIC_API_KEY is not configured on the server.")
    return anthropic.Anthropic(
        api_key=settings.ANTHROPIC_API_KEY,
        timeout=settings.AI_REQUEST_TIMEOUT_SECONDS,
        max_retries=2,  # SDK retries 408/409/429/5xx and connection errors with backoff
    )


def _generate(prompt: str, output_model: type[BaseModel]) -> BaseModel:
    settings = get_settings()
    try:
        response = _client().messages.parse(
            model=settings.ANTHROPIC_MODEL,
            max_tokens=MAX_TOKENS,
            messages=[{"role": "user", "content": prompt}],
            output_format=output_model,
        )
    except anthropic.AuthenticationError as e:
        raise AIGenerationError("The Anthropic API key is invalid.") from e
    except anthropic.PermissionDeniedError as e:
        raise AIGenerationError("The Anthropic API key does not have access to this model.") from e
    except anthropic.NotFoundError as e:
        raise AIGenerationError(f"Model '{settings.ANTHROPIC_MODEL}' was not found.") from e
    except anthropic.RateLimitError as e:
        raise AIGenerationError("Claude is rate limited right now. Please try again in a minute.") from e
    except anthropic.APIStatusError as e:
        if e.status_code >= 500:
            raise AIGenerationError("Claude is temporarily unavailable. Please try again shortly.") from e
        raise AIGenerationError(f"Claude rejected the request ({e.status_code}).") from e
    except anthropic.APITimeoutError as e:
        raise AIGenerationError("Claude took too long to respond. Please try again.") from e
    except anthropic.APIConnectionError as e:
        raise AIGenerationError("Could not reach the Claude API.") from e

    if response.stop_reason == "refusal":
        raise AIGenerationError("Claude declined to generate this content.")
    if response.stop_reason == "max_tokens":
        raise AIGenerationError("Claude's response was cut off before it finished. Please try again.")
    if response.parsed_output is None:
        raise AIGenerationError("Claude returned a response in an unexpected format.")

    logger.info(
        "Claude %s generated: input_tokens=%s output_tokens=%s",
        output_model.__name__, response.usage.input_tokens, response.usage.output_tokens,
    )
    return response.parsed_output


def generate_analysis(result, responses, bank: QuestionBank) -> dict:
    analysis = _generate(build_analysis_prompt(result, responses, bank), ExecutiveAnalysis)
    return analysis.model_dump()


def generate_roadmap(result) -> dict:
    roadmap = _generate(build_roadmap_prompt(result), Roadmap).model_dump()
    # The UI and PDF read target_dimension_scores as {dimension: score}
    for phase in roadmap["phases"]:
        phase["target_dimension_scores"] = {
            t["dimension"]: t["score"] for t in phase["target_dimension_scores"]
        }
    return roadmap
