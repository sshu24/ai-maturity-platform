from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import Optional
from pydantic import BaseModel

from app.db.connection import get_db
from app.db.models import Organisation, User
from app.auth.rbac import require_role, get_current_user

router = APIRouter(prefix="/organisations", tags=["organisations"])


# ------------------------------------------------------------------
# Schemas
# ------------------------------------------------------------------

class OrgCreate(BaseModel):
    name: str
    slug: str
    industry: Optional[str] = None


class OrgResponse(BaseModel):
    id: str
    name: str
    slug: str
    industry: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


class UserCreate(BaseModel):
    email: str
    password: str
    full_name: Optional[str] = None
    role: str = "assessor"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    organisation_id: Optional[str]
    is_active: bool

    class Config:
        from_attributes = True


# ------------------------------------------------------------------
# Routes
# ------------------------------------------------------------------

@router.post("", response_model=OrgResponse)
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
    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        industry=org.industry,
        is_active=org.is_active,
    )


@router.get("", response_model=list[OrgResponse])
def list_organisations(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin"))
):
    orgs = db.query(Organisation).filter(Organisation.is_active == True).all()
    return [
        OrgResponse(
            id=str(o.id),
            name=o.name,
            slug=o.slug,
            industry=o.industry,
            is_active=o.is_active,
        )
        for o in orgs
    ]

@router.get("/{org_id}", response_model=OrgResponse)
def get_organisation(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Super admin can see all, others only their own org
    if current_user.role != "super_admin":
        if str(current_user.organisation_id) != org_id:
            raise HTTPException(status_code=403, detail="Access denied")

    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    return OrgResponse(
        id=str(org.id),
        name=org.name,
        slug=org.slug,
        industry=org.industry,
        is_active=org.is_active,
    )

@router.post("/{org_id}/users", response_model=UserResponse)
def create_user_in_org(
    org_id: str,
    payload: UserCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    # client_admin can only add users to their own org
    if current_user.role == "client_admin":
        if str(current_user.organisation_id) != org_id:
            raise HTTPException(status_code=403, detail="Access denied")

    org = db.query(Organisation).filter(Organisation.id == org_id).first()
    if not org:
        raise HTTPException(status_code=404, detail="Organisation not found")

    existing = db.query(User).filter(User.email == payload.email).first()
    if existing:
        raise HTTPException(status_code=409, detail=f"Email '{payload.email}' already exists")

    # Prevent creating super_admin via this route
    if payload.role == "super_admin":
        raise HTTPException(status_code=400, detail="Cannot create super_admin via this endpoint")

    from app.auth.login import hash_password
    user = User(
        email=payload.email,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name,
        role=payload.role,
        organisation_id=org_id,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return UserResponse(
        id=str(user.id),
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        organisation_id=str(user.organisation_id),
        is_active=user.is_active,
    )


@router.get("/{org_id}/users", response_model=list[UserResponse])
def list_users_in_org(
    org_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_role("super_admin", "client_admin"))
):
    if current_user.role == "client_admin":
        if str(current_user.organisation_id) != org_id:
            raise HTTPException(status_code=403, detail="Access denied")

    users = db.query(User).filter(
        User.organisation_id == org_id,
        User.is_active == True
    ).all()
    return [
        UserResponse(
            id=str(u.id),
            email=u.email,
            full_name=u.full_name,
            role=u.role,
            organisation_id=str(u.organisation_id),
            is_active=u.is_active,
        )
        for u in users
    ]