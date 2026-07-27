from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from datetime import datetime
from typing import Optional
from pydantic import BaseModel

from app.db.connection import get_db
from app.db.models import User
from app.auth.login import verify_password, create_access_token
from app.auth.rbac import get_current_user

router = APIRouter(prefix="/auth", tags=["auth"])


class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    role: str
    full_name: Optional[str]
    org_id: Optional[str]


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: Optional[str]
    role: str
    org_id: Optional[str]

    class Config:
        from_attributes = True


@router.post("/login", response_model=TokenResponse)
def login(
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db)
):
    user = db.query(User).filter(
        User.email == form_data.username,
        User.is_active == True
    ).first()

    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    user.last_login = datetime.utcnow()
    db.commit()

    token = create_access_token(
        user_id=str(user.id),
        role=user.role,
        org_id=str(user.organisation_id) if user.organisation_id else None
    )

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        role=user.role,
        full_name=user.full_name,
        org_id=str(user.organisation_id) if user.organisation_id else None
    )


@router.get("/me", response_model=UserResponse)
def get_me(current_user: User = Depends(get_current_user)):
    return UserResponse(
        id=str(current_user.id),
        email=current_user.email,
        full_name=current_user.full_name,
        role=current_user.role,
        org_id=str(current_user.organisation_id) if current_user.organisation_id else None
    )