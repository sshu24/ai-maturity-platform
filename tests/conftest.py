import os

# Must be set before any app module is imported: settings are read and cached
# at import time. Assigned (not setdefault) so a developer's .env or shell
# can never point tests at a real database or a real Anthropic key.
os.environ.update({
    "POSTGRES_USER": "test",
    "POSTGRES_PASSWORD": "test",
    "POSTGRES_DB": "test",
    "POSTGRES_HOST": "localhost",
    "SECRET_KEY": "test-secret-key",
    "ANTHROPIC_API_KEY": "test-key",
    "ENV": "test",
})

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.routes import assessment as assessment_routes
from app.auth.login import create_access_token
from app.components import ai_agents
from app.db.connection import get_db
from app.db.models import Base, Organisation, User, Assessment, Result
from app.main import app


@pytest.fixture(autouse=True)
def no_real_claude_calls(monkeypatch):
    def _blocked():
        raise AssertionError("Tests must not call the real Claude API; stub ai_agents instead")
    monkeypatch.setattr(ai_agents, "_client", _blocked)


@pytest.fixture
def db_session_factory(monkeypatch):
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    # Background AI jobs open their own session
    monkeypatch.setattr(assessment_routes, "SessionLocal", factory)
    yield factory
    engine.dispose()


@pytest.fixture
def db(db_session_factory):
    session = db_session_factory()
    yield session
    session.close()


@pytest.fixture
def client(db_session_factory):
    def override_get_db():
        session = db_session_factory()
        try:
            yield session
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


def _make_user(db, email, role, org_id):
    user = User(email=email, hashed_password="x", full_name=email, role=role, organisation_id=org_id)
    db.add(user)
    db.commit()
    return user


def auth_headers(user: User) -> dict:
    token = create_access_token(str(user.id), user.role, str(user.organisation_id) if user.organisation_id else None)
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture
def tenants(db):
    """Two organisations, each with a client admin and an assessor, plus a super admin."""
    org_a = Organisation(name="Org A", slug="org-a")
    org_b = Organisation(name="Org B", slug="org-b")
    db.add_all([org_a, org_b])
    db.commit()
    return {
        "org_a": org_a,
        "org_b": org_b,
        "super_admin": _make_user(db, "root@example.com", "super_admin", None),
        "admin_a": _make_user(db, "admin@a.com", "client_admin", org_a.id),
        "assessor_a": _make_user(db, "assessor@a.com", "assessor", org_a.id),
        "admin_b": _make_user(db, "admin@b.com", "client_admin", org_b.id),
        "assessor_b": _make_user(db, "assessor@b.com", "assessor", org_b.id),
    }


@pytest.fixture
def completed_assessment(db, tenants):
    """A completed assessment in Org A with a scored result."""
    assessment = Assessment(
        organisation_id=tenants["org_a"].id,
        created_by_id=tenants["assessor_a"].id,
        status="completed",
    )
    db.add(assessment)
    db.commit()
    db.add(Result(
        assessment_id=assessment.id,
        overall_score=2.5,
        maturity_tier=2,
        maturity_label="Developing",
        dimension_scores=[
            {"id": "data_infrastructure", "label": "Data & Data Infrastructure",
             "score": 2.5, "tier": 2, "tier_label": "Developing"},
        ],
        recommendations={},
    ))
    db.commit()
    return assessment
