import uuid
from datetime import datetime
from sqlalchemy import (
    Column, String, Integer, Float, Boolean,
    DateTime, ForeignKey, Text, JSON, Enum
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import relationship, declarative_base

Base = declarative_base()


def gen_uuid():
    return str(uuid.uuid4())


# ------------------------------------------------------------------
# Organisation — top-level tenant (your client or internal team)
# ------------------------------------------------------------------
class Organisation(Base):
    __tablename__ = "organisations"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    name = Column(String(255), nullable=False)
    slug = Column(String(100), unique=True, nullable=False)
    industry = Column(String(100))
    created_at = Column(DateTime, default=datetime.utcnow)
    is_active = Column(Boolean, default=True)

    users = relationship("User", back_populates="organisation")
    assessments = relationship("Assessment", back_populates="organisation")


# ------------------------------------------------------------------
# User — belongs to one org, has one role
# ------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    email = Column(String(255), unique=True, nullable=False)
    hashed_password = Column(String(255), nullable=False)
    full_name = Column(String(255))
    role = Column(
        Enum(
            "super_admin",
            "client_admin",
            "assessor",
            "viewer",
            name="user_role"
        ),
        nullable=False,
        default="assessor"
    )
    organisation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("organisations.id"),
        nullable=True
    )
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    last_login = Column(DateTime, nullable=True)

    organisation = relationship("Organisation", back_populates="users")
    assessments = relationship("Assessment", back_populates="created_by")


# ------------------------------------------------------------------
# Assessment — one run of the full questionnaire
# ------------------------------------------------------------------
class Assessment(Base):
    __tablename__ = "assessments"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    organisation_id = Column(
        UUID(as_uuid=False),
        ForeignKey("organisations.id"),
        nullable=False
    )
    created_by_id = Column(
        UUID(as_uuid=False),
        ForeignKey("users.id"),
        nullable=False
    )
    title = Column(String(255), default="AI Maturity Assessment")
    status = Column(
        Enum("draft", "in_progress", "completed", name="assessment_status"),
        default="draft"
    )
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    organisation = relationship("Organisation", back_populates="assessments")
    created_by = relationship("User", back_populates="assessments")
    responses = relationship("Response", back_populates="assessment")
    result = relationship("Result", back_populates="assessment", uselist=False)


# ------------------------------------------------------------------
# Response — one answer to one question
# ------------------------------------------------------------------
class Response(Base):
    __tablename__ = "responses"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    assessment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("assessments.id"),
        nullable=False
    )
    question_id = Column(String(100), nullable=False)
    dimension = Column(String(100), nullable=False)
    answer_value = Column(Integer, nullable=False)
    answer_label = Column(String(255))
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="responses")


# ------------------------------------------------------------------
# Result — computed scorecard for a completed assessment
# ------------------------------------------------------------------
class Result(Base):
    __tablename__ = "results"

    id = Column(UUID(as_uuid=False), primary_key=True, default=gen_uuid)
    assessment_id = Column(
        UUID(as_uuid=False),
        ForeignKey("assessments.id"),
        unique=True,
        nullable=False
    )
    overall_score = Column(Float, nullable=False)
    maturity_tier = Column(Integer, nullable=False)
    maturity_label = Column(String(50), nullable=False)
    dimension_scores = Column(JSON, nullable=False)
    recommendations = Column(JSON, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    assessment = relationship("Assessment", back_populates="result")