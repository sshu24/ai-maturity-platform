import logging
from datetime import datetime, timedelta
from typing import Literal, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.db.connection import get_db, SessionLocal
from app.db.models import User, Assessment, Response, Result
from app.auth.rbac import get_current_user, require_role
from app.components import ai_agents
from app.components.question_engine import load_question_bank, get_completion_status
from app.components.scoring import compute_scorecard, score_summary
from app.components.recommendations import get_all_recommendations
from app.config.settings import get_settings

logger = logging.getLogger(__name__)
settings = get_settings()

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

class JobStatus(BaseModel):
    status: str        # "pending" | "generating" | "complete" | "failed"
    data: dict | None = None
    error: str | None = None

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

AIJobKind = Literal["analysis", "roadmap"]


def _mark_job_failed(db: Session, assessment_id: str, kind: AIJobKind, message: str) -> None:
    db.rollback()
    result = db.query(Result).filter(Result.assessment_id == assessment_id).first()
    if result:
        setattr(result, f"{kind}_status", "failed")
        setattr(result, f"{kind}_error", message)
        db.commit()


def _run_ai_job(assessment_id: str, kind: AIJobKind) -> None:
    """Background task: generate analysis or roadmap with Claude and store it.

    Opens its own session, because the request's session is closed by the
    time background tasks run.
    """
    db = SessionLocal()
    try:
        result = db.query(Result).filter(Result.assessment_id == assessment_id).first()
        if not result:
            logger.warning("AI %s job: no result for assessment %s", kind, assessment_id)
            return

        if kind == "analysis":
            responses = db.query(Response).filter(
                Response.assessment_id == assessment_id
            ).all()
            output = ai_agents.generate_analysis(result, responses, load_question_bank())
        else:
            output = ai_agents.generate_roadmap(result)

        setattr(result, f"ai_{kind}", output)
        setattr(result, f"{kind}_status", "complete")
        setattr(result, f"{kind}_error", None)
        db.commit()

    except ai_agents.AIGenerationError as e:
        logger.warning("AI %s job failed for assessment %s: %s", kind, assessment_id, e, exc_info=True)
        _mark_job_failed(db, assessment_id, kind, str(e))
    except Exception:
        logger.exception("AI %s job crashed for assessment %s", kind, assessment_id)
        _mark_job_failed(db, assessment_id, kind, "Unexpected error during generation. Check the server logs.")
    finally:
        db.close()


def _get_completed_result_or_404(assessment_id: str, db: Session, current_user: User) -> Result:
    assessment = _get_assessment_or_404(assessment_id, db, current_user)
    if assessment.status != "completed":
        raise HTTPException(status_code=400, detail="Assessment must be completed first")

    result = db.query(Result).filter(Result.assessment_id == assessment_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return result


def _start_ai_job(
    assessment_id: str,
    kind: AIJobKind,
    force: bool,
    background_tasks: BackgroundTasks,
    db: Session,
    current_user: User,
) -> JobStatus:
    result = _get_completed_result_or_404(assessment_id, db, current_user)

    data = getattr(result, f"ai_{kind}")
    if data and getattr(result, f"{kind}_status") == "complete" and not force:
        return JobStatus(status="complete", data=data)

    # Claim the job atomically so concurrent clicks don't start two generations.
    # A job stuck in "generating" (e.g. the container restarted) can be reclaimed.
    status_col = getattr(Result, f"{kind}_status")
    started_col = getattr(Result, f"{kind}_started_at")
    now = datetime.utcnow()
    stale_before = now - timedelta(seconds=settings.AI_JOB_STALE_SECONDS)
    claimed = db.query(Result).filter(
        Result.id == result.id,
        or_(
            status_col.is_(None),
            status_col != "generating",
            started_col.is_(None),
            started_col < stale_before,
        ),
    ).update(
        {status_col: "generating", started_col: now, getattr(Result, f"{kind}_error"): None},
        synchronize_session=False,
    )
    db.commit()

    if claimed:
        background_tasks.add_task(_run_ai_job, assessment_id, kind)
    return JobStatus(status="generating")


def _ai_job_status(assessment_id: str, kind: AIJobKind, db: Session, current_user: User) -> JobStatus:
    _get_assessment_or_404(assessment_id, db, current_user)
    result = db.query(Result).filter(Result.assessment_id == assessment_id).first()
    if not result:
        raise HTTPException(status_code=404, detail="Result not found")
    return JobStatus(
        status=getattr(result, f"{kind}_status") or "pending",
        data=getattr(result, f"ai_{kind}"),
        error=getattr(result, f"{kind}_error"),
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


@router.post("/{assessment_id}/analyse", response_model=JobStatus)
def analyse_assessment(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start AI analysis. Returns the cached analysis unless force=true."""
    return _start_ai_job(assessment_id, "analysis", force, background_tasks, db, current_user)


@router.post("/{assessment_id}/roadmap", response_model=JobStatus)
def generate_roadmap(
    assessment_id: str,
    background_tasks: BackgroundTasks,
    force: bool = False,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Start roadmap generation. Returns the cached roadmap unless force=true."""
    return _start_ai_job(assessment_id, "roadmap", force, background_tasks, db, current_user)


@router.get("/{assessment_id}/analyse/status", response_model=JobStatus)
def get_analyse_status(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _ai_job_status(assessment_id, "analysis", db, current_user)


@router.get("/{assessment_id}/roadmap/status", response_model=JobStatus)
def get_roadmap_status(
    assessment_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    return _ai_job_status(assessment_id, "roadmap", db, current_user)


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