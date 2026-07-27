from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import Optional
from pydantic import BaseModel
from datetime import datetime

from app.db.connection import get_db
from app.db.models import Organisation, User, Assessment, Result
from app.auth.rbac import require_role, get_current_user
from app.auth.login import hash_password

router = APIRouter(prefix="/admin", tags=["admin"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class OrgSummary(BaseModel):
    id: str
    name: str
    slug: str
    industry: Optional[str]
    is_active: bool
    user_count: int
    assessment_count: int
    latest_score: Optional[float]
    latest_tier: Optional[str]


class UserSummary(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    organisation_id: Optional[str]
    organisation_name: Optional[str]
    is_active: bool
    last_login: Optional[datetime]


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "assessor"
    organisation_id: Optional[str] = None


class UserUpdate(BaseModel):
    full_name: Optional[str] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None


class OrgCreate(BaseModel):
    name: str
    slug: str
    industry: Optional[str] = None


class PlatformStats(BaseModel):
    total_orgs: int
    total_users: int
    total_assessments: int
    completed_assessments: int
    average_score: Optional[float]


# ------------------------------------------------------------------
# Platform stats — super admin only
# ------------------------------------------------------------------

@router.get("/stats", response_model=PlatformStats)
def get_platform_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    total_orgs = db.query(func.count(Organisation.id)).filter(
        Organisation.is_active == True
    ).scalar()

    total_users = db.query(func.count(User.id)).filter(
        User.is_active == True
    ).scalar()

    total_assessments = db.query(func.count(Assessment.id)).scalar()

    completed_assessments = db.query(func.count(Assessment.id)).filter(
        Assessment.status == "completed"
    ).scalar()

    avg_score = db.query(func.avg(Result.overall_score)).scalar()

    return PlatformStats(
        total_orgs=total_orgs,
        total_users=total_users,
        total_assessments=total_assessments,
        completed_assessments=completed_assessments,
        average_score=round(float(avg_score), 2) if avg_score else None,
    )


# ------------------------------------------------------------------
# Organisation management — super admin only
# ------------------------------------------------------------------

@router.get("/organisations", response_model=list[OrgSummary])
def list_organisations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    orgs = db.query(Organisation).order_by(Organisation.name).all()
    result = []
    for org in orgs:
        user_count = db.query(func.count(User.id)).filter(
            User.organisation_id == org.id,
            User.is_active == True
        ).scalar()

        assessment_count = db.query(func.count(Assessment.id)).filter(
            Assessment.organisation_id == org.id,
            Assessment.status == "completed"
        ).scalar()

        latest_result = db.query(Result).join(Assessment).filter(
            Assessment.organisation_id == org.id,
            Assessment.status == "completed"
        ).order_by(Assessment.completed_at.desc()).first()

        result.append(OrgSummary(
            id=str(org.id),
            name=org.name,
            slug=org.slug,
            industry=org.industry,
            is_active=org.is_active,
            user_count=user_count,
            assessment_count=assessment_count,
            latest_score=latest_result.overall_score if latest_result else None,
            latest_tier=latest_result.maturity_label if latest_result else None,
        ))
    return result


@router.post("/organisations", response_model=OrgSummary)
def create_organisation(
    payload: OrgCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    existing = db.query(Organisation).filter(
        Organisation.slug == payload.slug
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Slug '{payload.slug}' already exists")

    org = Organisation(
        name=payload.name,
        slug=payload.slug,
        industry=payload.industry,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return OrgSummary(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        industry=org.industry,
        is_active=org.is_active,
        user_count=0,
        assessment_count=0,
        latest_score=None,
        latest_tier=None,
    )


@router.patch("/organisations/{org_id}/deactivate")
def deactivate_organisation(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")
    org.is_active = False
    db.commit()
    return {"status": "deactivated", "org_id": org_id}


# ------------------------------------------------------------------
# User management
# ------------------------------------------------------------------

@router.get("/users", response_model=list[UserSummary])
def list_users(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    if current_user.role == "super_admin":
        users = db.query(User).order_by(User.email).all()
    else:
        users = db.query(User).filter(
            User.organisation_id == current_user.organisation_id
        ).order_by(User.email).all()

    result = []
    for u in users:
        org_name = None
        if u.organisation_id:
            org = db.query(Organisation).filter(
                Organisation.id == u.organisation_id
            ).first()
            org_name = org.name if org else None

        result.append(UserSummary(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            organisation_id=str(u.organisation_id) if u.organisation_id else None,
            organisation_name=org_name,
            is_active=u.is_active,
            last_login=u.last_login,
        ))
    return result


@router.post("/users", response_model=UserSummary)
def create_user(
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    # client_admin can only create users in their own org
    if current_user.role == "client_admin":
        if payload.organisation_id != str(current_user.organisation_id):
            raise HTTPException(status_code=403, detail="Access denied")
        if payload.role in ("super_admin", "client_admin"):
            raise HTTPException(status_code=403, detail="Cannot create this role")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Email '{payload.email}' already exists")

    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        organisation_id=payload.organisation_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    org_name = None
    if user.organisation_id:
        org = db.query(Organisation).filter(
            Organisation.id == user.organisation_id
        ).first()
        org_name = org.name if org else None

    return UserSummary(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organisation_id=str(user.organisation_id) if user.organisation_id else None,
        organisation_name=org_name,
        is_active=user.is_active,
        last_login=user.last_login,
    )


@router.patch("/users/{user_id}", response_model=UserSummary)
def update_user(
    user_id: str,
    payload: UserUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if current_user.role == "client_admin":
        if str(user.organisation_id) != str(current_user.organisation_id):
            raise HTTPException(status_code=403, detail="Access denied")

    if payload.full_name is not None:
        user.full_name = payload.full_name
    if payload.role is not None:
        if current_user.role == "client_admin" and payload.role in ("super_admin", "client_admin"):
            raise HTTPException(status_code=403, detail="Cannot assign this role")
        user.role = payload.role
    if payload.is_active is not None:
        user.is_active = payload.is_active

    db.commit()
    db.refresh(user)

    org_name = None
    if user.organisation_id:
        org = db.query(Organisation).filter(
            Organisation.id == user.organisation_id
        ).first()
        org_name = org.name if org else None

    return UserSummary(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organisation_id=str(user.organisation_id) if user.organisation_id else None,
        organisation_name=org_name,
        is_active=user.is_active,
        last_login=user.last_login,
    )


# ------------------------------------------------------------------
# Cross-org assessment overview — super admin only
# ------------------------------------------------------------------

@router.get("/assessments")
def list_all_assessments(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    assessments = db.query(Assessment).order_by(
        Assessment.created_at.desc()
    ).all()

    result = []
    for a in assessments:
        org = db.query(Organisation).filter(
            Organisation.id == a.organisation_id
        ).first()
        latest_result = db.query(Result).filter(
            Result.assessment_id == str(a.id)
        ).first()
        result.append({
            "id": str(a.id),
            "title": a.title,
            "status": a.status,
            "organisation": org.name if org else "Unknown",
            "organisation_id": str(a.organisation_id),
            "created_at": a.created_at.strftime("%Y-%m-%d") if a.created_at else "",
            "completed_at": a.completed_at.strftime("%Y-%m-%d") if a.completed_at else "",
            "overall_score": latest_result.overall_score if latest_result else None,
            "maturity_label": latest_result.maturity_label if latest_result else None,
        })
    return result