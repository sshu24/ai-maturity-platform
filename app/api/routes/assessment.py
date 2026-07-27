import os
import httpx
import json
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.db.connection import get_db
from app.db.models import User, Assessment, Response, Result
from app.auth.rbac import get_current_user, require_role
from app.components.question_engine import load_question_bank, get_completion_status
from app.components.scoring import compute_scorecard, score_summary
from app.components.recommendations import get_all_recommendations

router = APIRouter(prefix="/assessments", tags=["assessments"])


# ------------------------------------------------------------------
# Pydantic schemas
# ------------------------------------------------------------------

class AssessmentCreate(BaseModel):
    title: Optional[str] = "AI Maturity Assessment"


class AssessmentResponse(BaseModel):
    id: str
    title: str
    status: str
    organisation_id: str
    created_by_id: str
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    created_at: datetime

    class Config:
        from_attributes = True


class ResponseCreate(BaseModel):
    question_id: str
    answer_value: int
    answer_label: str


class ResponseOut(BaseModel):
    id: str
    question_id: str
    dimension: str
    answer_value: int
    answer_label: str

    class Config:
        from_attributes = True


class AssessmentDetail(BaseModel):
    assessment: AssessmentResponse
    responses: list[ResponseOut]
    completion: dict


class ResultOut(BaseModel):
    id: str
    assessment_id: str
    overall_score: float
    maturity_tier: int
    maturity_label: str
    dimension_scores: list
    recommendations: dict
    created_at: datetime

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def _get_assessment_or_404(
    assessment_id: str,
    db: Session,
    current_user: User
) -> Assessment:
    assessment = db.query(Assessment).filter(
        Assessment.id == assessment_id
    ).first()

    if not assessment:
        raise HTTPException(status_code=404, detail="Assessment not found")

    if current_user.role != "super_admin":
        if str(assessment.organisation_id) != str(current_user.organisation_id):
            raise HTTPException(status_code=403, detail="Access denied")

    return assessment


def _build_assessment_detail(assessment: Assessment, db: Session) -> AssessmentDetail:
    responses = db.query(Response).filter(
        Response.assessment_id == str(assessment.id)
    ).all()

    bank = load_question_bank()
    answered_ids = [r.question_id for r in responses]
    completion = get_completion_status(bank, answered_ids)

    return AssessmentDetail(
        assessment=AssessmentResponse(
            id=str(assessment.id),
            title=assessment.title,
            status=assessment.status,
            organisation_id=str(assessment.organisation_id),
            created_by_id=str(assessment.created_by_id),
            started_at=assessment.started_at,
            completed_at=assessment.completed_at,
            created_at=assessment.created_at,
        ),
        responses=[
            ResponseOut(
                id=str(r.id),
                question_id=r.question_id,
                dimension=r.dimension,
                answer_value=r.answer_value,
                answer_label=r.answer_label,
            )
            for r in responses
        ],
        completion=completion,
    )


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.post("", response_model=AssessmentResponse)
def create_assessment(
    payload: AssessmentCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin", "assessor"))
):
    if not current_user.organisation_id:
        raise HTTPException(
            status_code=400,
            detail="User must belong to an organisation to create an assessment"
        )

    existing = db.query(Assessment).filter(
        Assessment.organisation_id == current_user.organisation_id,
        Assessment.status.in_(["draft", "in_progress"])
    ).first()

    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"An active assessment already exists: {existing.id}. Complete or delete it first."
        )

    assessment = Assessment(
        organisation_id=current_user.organisation_id,
        created_by_id=current_user.id,
        title=payload.title,
        status="draft",
    )
    db.add(assessment)
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/active", response_model=Optional[AssessmentDetail])
def get_active_assessment(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if not current_user.organisation_id:
        return None

    assessment = db.query(Assessment).filter(
        Assessment.organisation_id == current_user.organisation_id,
        Assessment.status.in_(["draft", "in_progress"])
    ).first()

    if not assessment:
        return None

    return _build_assessment_detail(assessment, db)


@router.get("/history/all")
def get_history(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == "super_admin":
        assessments = db.query(Assessment).filter(
            Assessment.status == "completed"
        ).order_by(Assessment.completed_at.asc()).all()
    else:
        assessments = db.query(Assessment).filter(
            Assessment.organisation_id == current_user.organisation_id,
            Assessment.status == "completed"
        ).order_by(Assessment.completed_at.asc()).all()

    history = []
    for a in assessments:
        result = db.query(Result).filter(
            Result.assessment_id == str(a.id)
        ).first()
        if result:
            history.append({
                "assessment_id": str(a.id),
                "title": a.title,
                "completed_at": a.completed_at.strftime("%Y-%m-%d") if a.completed_at else "",
                "overall_score": result.overall_score,
                "maturity_tier": result.maturity_tier,
                "maturity_label": result.maturity_label,
                "dimension_scores": result.dimension_scores,
            })
    return history


@router.get("/{assessment_id}", response_model=AssessmentDetail)
def get_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)
    return _build_assessment_detail(assessment, db)


@router.post("/{assessment_id}/responses", response_model=ResponseOut)
def save_response(
    assessment_id: str,
    payload: ResponseCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin", "assessor"))
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="Cannot modify a completed assessment"
        )

    bank = load_question_bank()
    question = bank.get_question(payload.question_id)
    if not question:
        raise HTTPException(
            status_code=404,
            detail=f"Question '{payload.question_id}' not found"
        )

    valid_values = [o.value for o in question.options]
    if payload.answer_value not in valid_values:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid answer value {payload.answer_value}. Valid: {valid_values}"
        )

    dimension_id = bank.get_dimension_for_question(payload.question_id)

    existing = db.query(Response).filter(
        Response.assessment_id == assessment_id,
        Response.question_id == payload.question_id
    ).first()

    if existing:
        existing.answer_value = payload.answer_value
        existing.answer_label = payload.answer_label
        response = existing
    else:
        response = Response(
            assessment_id=assessment_id,
            question_id=payload.question_id,
            dimension=dimension_id,
            answer_value=payload.answer_value,
            answer_label=payload.answer_label,
        )
        db.add(response)

    if assessment.status == "draft":
        assessment.status = "in_progress"
        assessment.started_at = datetime.utcnow()

    db.commit()
    db.refresh(response)
    return response


@router.post("/{assessment_id}/submit", response_model=AssessmentResponse)
def submit_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin", "assessor"))
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status == "completed":
        raise HTTPException(status_code=400, detail="Assessment already completed")

    bank = load_question_bank()
    responses = db.query(Response).filter(
        Response.assessment_id == assessment_id
    ).all()
    answered_ids = [r.question_id for r in responses]
    completion = get_completion_status(bank, answered_ids)

    if not completion["_overall"]["complete"]:
        incomplete = [
            f"{v['label']} ({v['answered']}/{v['total']})"
            for k, v in completion.items()
            if k != "_overall" and not v["complete"]
        ]
        raise HTTPException(
            status_code=400,
            detail=f"Incomplete dimensions: {', '.join(incomplete)}"
        )

    response_dicts = [
        {"question_id": r.question_id, "answer_value": r.answer_value}
        for r in responses
    ]
    scorecard = compute_scorecard(bank, response_dicts)
    summary = score_summary(scorecard)

    dimension_tiers = {d.id: d.tier for d in scorecard.dimension_details}
    recommendations = get_all_recommendations(dimension_tiers)

    result = Result(
        assessment_id=assessment_id,
        overall_score=scorecard.overall_score,
        maturity_tier=scorecard.maturity_tier,
        maturity_label=scorecard.maturity_label,
        dimension_scores=summary["dimension_details"],
        recommendations=recommendations,
    )
    db.add(result)

    assessment.status = "completed"
    assessment.completed_at = datetime.utcnow()
    db.commit()
    db.refresh(assessment)
    return assessment


@router.get("/{assessment_id}/result", response_model=ResultOut)
def get_result(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status != "completed":
        raise HTTPException(status_code=400, detail="Assessment is not completed yet")

    result = db.query(Result).filter(
        Result.assessment_id == assessment_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    return ResultOut(
        id=str(result.id),
        assessment_id=str(result.assessment_id),
        overall_score=result.overall_score,
        maturity_tier=result.maturity_tier,
        maturity_label=result.maturity_label,
        dimension_scores=result.dimension_scores if isinstance(result.dimension_scores, list) else [],
        recommendations=result.recommendations if isinstance(result.recommendations, dict) else {},
        created_at=result.created_at,
    )


@router.get("/{assessment_id}/result/summary")
def get_result_summary(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)
    result = db.query(Result).filter(
        Result.assessment_id == assessment_id
    ).first()
    if not result:
        return None
    return {
        "assessment_id": str(assessment.id),
        "completed_at": assessment.completed_at,
        "overall_score": result.overall_score,
        "maturity_tier": result.maturity_tier,
        "maturity_label": result.maturity_label,
        "dimension_scores": result.dimension_scores,
    }


@router.post("/{assessment_id}/analyse")
def analyse_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status != "completed":
        raise HTTPException(status_code=400, detail="Assessment must be completed first")

    result = db.query(Result).filter(
        Result.assessment_id == assessment_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    responses = db.query(Response).filter(
        Response.assessment_id == assessment_id
    ).all()

    bank = load_question_bank()

    dimension_context = []
    for dim in bank.dimensions:
        dim_responses = [r for r in responses if r.dimension == dim.id]
        dim_score_data = next(
            (d for d in result.dimension_scores if d["id"] == dim.id), {}
        )
        questions_answered = []
        for q in dim.questions:
            resp = next((r for r in dim_responses if r.question_id == q.id), None)
            if resp:
                if resp.answer_value <= 3:
                    questions_answered.append({
                        "question": q.text,
                        "answer": resp.answer_label,
                        "score": resp.answer_value,
                    })
        dimension_context.append({
            "dimension": dim.label,
            "score": dim_score_data.get("score", 0),
            "tier": dim_score_data.get("tier_label", ""),
            "responses": questions_answered,
        })

    prompt = f"""You are an expert AI platform maturity consultant.
You have just completed an assessment of an organisation's AI maturity across 6 dimensions.

Here are the assessment results:

Overall Score: {result.overall_score}/5.0
Maturity Level: {result.maturity_label} (Level {result.maturity_tier})

Dimension Scores and Responses:
{json.dumps(dimension_context, indent=2)}

Based on this assessment data, provide a structured analysis in the following JSON format:
{{
    "executive_narrative": "3 paragraphs of executive-level narrative summarising the organisation's AI maturity, key strengths, and critical gaps. Be specific and reference actual scores and answers.",
    "cross_dimensional_risks": [
        {{
            "risk": "Risk title",
            "description": "2-3 sentence description of the risk and its business impact",
            "dimensions_affected": ["dimension1", "dimension2"]
        }}
    ],
    "quick_wins": [
        {{
            "action": "Specific action title",
            "description": "Why this is high impact and low effort given current maturity",
            "expected_outcome": "What improvement this will drive"
        }}
    ],
    "ninety_day_focus": [
        {{
            "priority": 1,
            "focus_area": "Focus area title",
            "rationale": "Why this should be the priority in the next 90 days",
            "success_metric": "How to measure success"
        }}
    ]
}}

Provide exactly 3 cross_dimensional_risks, 3 quick_wins, and 3 ninety_day_focus items.
Return ONLY valid JSON, no markdown, no preamble."""

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Claude API error: {response.text}"
            )

        content = response.json()["content"][0]["text"]
        analysis = json.loads(content)
        return analysis

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse Claude response: {str(e)}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Claude API timed out. Please try again."
        )

@router.post("/{assessment_id}/roadmap")
def generate_roadmap(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Calls Claude API to generate a 6-month AI maturity improvement roadmap
    based on the assessment results.
    """
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status != "completed":
        raise HTTPException(status_code=400, detail="Assessment must be completed first")

    result = db.query(Result).filter(
        Result.assessment_id == assessment_id
    ).first()

    if not result:
        raise HTTPException(status_code=404, detail="Result not found")

    # Build dimension summary for prompt
    dimension_summary = []
    for dim in result.dimension_scores:
        dimension_summary.append({
            "dimension": dim["label"],
            "current_score": dim["score"],
            "current_tier": dim["tier_label"],
            "current_level": dim["tier"],
        })

    prompt = f"""You are an expert AI platform maturity consultant.
An organisation has completed an AI maturity assessment with the following results:

Overall Score: {result.overall_score}/5.0
Maturity Level: {result.maturity_label} (Level {result.maturity_tier})

Dimension Scores:
{json.dumps(dimension_summary, indent=2)}

Generate a practical 6-month AI maturity improvement roadmap organised into 3 phases.
Focus on moving the organisation to the next maturity tier.

Return ONLY valid JSON in exactly this format, no markdown, no preamble:
{{
    "roadmap_summary": "2-3 sentence summary of the roadmap strategy and target state",
    "target_overall_score": 3.8,
    "target_maturity_label": "Managed",
    "phases": [
        {{
            "phase": 1,
            "name": "Foundation",
            "months": "Months 1-2",
            "theme": "One sentence describing the phase theme",
            "initiatives": [
                {{
                    "title": "Initiative title",
                    "description": "2-3 sentence description of what to do and why",
                    "dimension": "Dimension name this primarily addresses",
                    "owner": "Job title of who should lead this",
                    "effort": "Low|Medium|High",
                    "impact": "Low|Medium|High",
                    "dependencies": "None or name of prerequisite initiative",
                    "score_improvement": 0.5
                }}
            ],
            "target_dimension_scores": {{
                "Data & Data Infrastructure": 2.8,
                "Model Development & MLOps": 2.5
            }}
        }}
    ]
}}

Rules:
- Phase 1 (Months 1-2): Foundation — quick wins and critical fixes
- Phase 2 (Months 3-4): Acceleration — build on foundation, address key gaps
- Phase 3 (Months 5-6): Optimisation — institutionalise and scale
- Each phase must have 3-4 initiatives
- Be specific and actionable, reference actual dimension scores
- target_dimension_scores in each phase should show realistic incremental improvement
- Return ONLY valid JSON"""

    try:
        response = httpx.post(
            "https://api.anthropic.com/v1/messages",
            headers={
                "Content-Type": "application/json",
                "x-api-key": os.environ.get("ANTHROPIC_API_KEY", ""),
                "anthropic-version": "2023-06-01",
            },
            json={
                "model": "claude-sonnet-4-6",
                "max_tokens": 4096,
                "messages": [{"role": "user", "content": prompt}],
            },
            timeout=60.0,
        )

        if response.status_code != 200:
            raise HTTPException(
                status_code=502,
                detail=f"Claude API error: {response.text}"
            )

        content = response.json()["content"][0]["text"]
        roadmap = json.loads(content)
        return roadmap

    except json.JSONDecodeError as e:
        raise HTTPException(
            status_code=502,
            detail=f"Failed to parse Claude response: {str(e)}"
        )
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=504,
            detail="Claude API timed out. Please try again."
        )
    
@router.delete("/{assessment_id}", status_code=204)
def delete_assessment(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    assessment = _get_assessment_or_404(assessment_id, db, current_user)

    if assessment.status == "completed":
        raise HTTPException(
            status_code=400,
            detail="Cannot delete a completed assessment"
        )

    db.query(Response).filter(Response.assessment_id == assessment_id).delete()
    db.delete(assessment)
    db.commit()


@router.get("", response_model=list[AssessmentResponse])
def list_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.role == "super_admin":
        assessments = db.query(Assessment).order_by(
            Assessment.created_at.desc()
        ).all()
    else:
        assessments = db.query(Assessment).filter(
            Assessment.organisation_id == current_user.organisation_id
        ).order_by(Assessment.created_at.desc()).all()

    return [
        AssessmentResponse(
            id=str(a.id),
            title=a.title,
            status=a.status,
            organisation_id=str(a.organisation_id),
            created_by_id=str(a.created_by_id),
            started_at=a.started_at,
            completed_at=a.completed_at,
            created_at=a.created_at,
        )
        for a in assessments
    ]