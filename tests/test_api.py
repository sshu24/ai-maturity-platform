from datetime import datetime, timedelta

import pytest

from app.components import ai_agents
from app.db.models import Assessment, Result, User
from tests.conftest import auth_headers


# ------------------------------------------------------------------
# Tenant isolation
# ------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/assessments/{id}",
    "/assessments/{id}/result",
    "/assessments/{id}/analyse/status",
    "/assessments/{id}/roadmap/status",
])
def test_other_org_cannot_read_assessment(client, tenants, completed_assessment, path):
    url = path.format(id=completed_assessment.id)
    assert client.get(url, headers=auth_headers(tenants["assessor_b"])).status_code == 403
    assert client.get(url, headers=auth_headers(tenants["assessor_a"])).status_code == 200


def test_other_org_cannot_trigger_ai_generation(client, tenants, completed_assessment):
    r = client.post(f"/assessments/{completed_assessment.id}/analyse",
                    headers=auth_headers(tenants["admin_b"]))
    assert r.status_code == 403


def test_super_admin_can_read_any_org(client, tenants, completed_assessment):
    r = client.get(f"/assessments/{completed_assessment.id}", headers=auth_headers(tenants["super_admin"]))
    assert r.status_code == 200


def test_list_assessments_is_scoped_to_org(client, tenants, completed_assessment):
    r_a = client.get("/assessments", headers=auth_headers(tenants["assessor_a"]))
    r_b = client.get("/assessments", headers=auth_headers(tenants["assessor_b"]))
    assert [a["id"] for a in r_a.json()] == [str(completed_assessment.id)]
    assert r_b.json() == []


def test_requests_without_token_are_rejected(client, completed_assessment):
    assert client.get(f"/assessments/{completed_assessment.id}").status_code == 401


# ------------------------------------------------------------------
# User management
# ------------------------------------------------------------------

def test_client_admin_cannot_move_user_to_another_org(client, db, tenants):
    user = tenants["assessor_a"]
    r = client.patch(f"/admin/users/{user.id}", json={"organisation_id": str(tenants["org_b"].id)},
                     headers=auth_headers(tenants["admin_a"]))
    assert r.status_code == 403
    db.refresh(user)
    assert str(user.organisation_id) == str(tenants["org_a"].id)


def test_super_admin_can_move_user_to_another_org(client, db, tenants):
    user = tenants["assessor_a"]
    r = client.patch(f"/admin/users/{user.id}", json={"organisation_id": str(tenants["org_b"].id)},
                     headers=auth_headers(tenants["super_admin"]))
    assert r.status_code == 200
    db.refresh(user)
    assert str(user.organisation_id) == str(tenants["org_b"].id)


def test_client_admin_cannot_edit_user_in_another_org(client, tenants):
    r = client.patch(f"/admin/users/{tenants['assessor_b'].id}", json={"full_name": "x"},
                     headers=auth_headers(tenants["admin_a"]))
    assert r.status_code == 403


def test_client_admin_cannot_grant_admin_roles(client, tenants):
    r = client.patch(f"/admin/users/{tenants['assessor_a'].id}", json={"role": "super_admin"},
                     headers=auth_headers(tenants["admin_a"]))
    assert r.status_code == 403


# ------------------------------------------------------------------
# AI generation jobs
# ------------------------------------------------------------------

ANALYSIS = {"executive_narrative": "Narrative"}


def _result(db, assessment) -> Result:
    db.expire_all()
    return db.query(Result).filter(Result.assessment_id == assessment.id).one()


def test_analysis_job_runs_and_is_cached(client, db, tenants, completed_assessment, monkeypatch):
    calls = []
    monkeypatch.setattr(ai_agents, "generate_analysis",
                        lambda result, responses, bank: calls.append(1) or ANALYSIS)
    headers = auth_headers(tenants["assessor_a"])
    base = f"/assessments/{completed_assessment.id}"

    # TestClient runs background tasks before returning
    assert client.post(f"{base}/analyse", headers=headers).json()["status"] == "generating"
    status = client.get(f"{base}/analyse/status", headers=headers).json()
    assert status == {"status": "complete", "data": ANALYSIS, "error": None}

    # Second request returns the cached result without calling Claude again
    r = client.post(f"{base}/analyse", headers=headers).json()
    assert r["status"] == "complete" and r["data"] == ANALYSIS
    assert len(calls) == 1

    # force=true regenerates
    client.post(f"{base}/analyse?force=true", headers=headers)
    assert len(calls) == 2


def test_failed_job_records_readable_error(client, tenants, completed_assessment, monkeypatch):
    def fail(result):
        raise ai_agents.AIGenerationError("Claude is rate limited right now.")
    monkeypatch.setattr(ai_agents, "generate_roadmap", fail)
    headers = auth_headers(tenants["assessor_a"])
    base = f"/assessments/{completed_assessment.id}"

    client.post(f"{base}/roadmap", headers=headers)
    status = client.get(f"{base}/roadmap/status", headers=headers).json()
    assert status["status"] == "failed"
    assert status["error"] == "Claude is rate limited right now."


def test_unexpected_exception_marks_job_failed(client, tenants, completed_assessment, monkeypatch):
    def crash(result):
        raise KeyError("boom")
    monkeypatch.setattr(ai_agents, "generate_roadmap", crash)
    headers = auth_headers(tenants["assessor_a"])
    base = f"/assessments/{completed_assessment.id}"

    client.post(f"{base}/roadmap", headers=headers)
    status = client.get(f"{base}/roadmap/status", headers=headers).json()
    assert status["status"] == "failed"
    assert "server logs" in status["error"]


def test_failed_job_can_be_retried(client, db, tenants, completed_assessment, monkeypatch):
    result = _result(db, completed_assessment)
    result.roadmap_status = "failed"
    result.roadmap_error = "old error"
    db.commit()
    monkeypatch.setattr(ai_agents, "generate_roadmap", lambda result: {"phases": []})

    client.post(f"/assessments/{completed_assessment.id}/roadmap", headers=auth_headers(tenants["assessor_a"]))

    result = _result(db, completed_assessment)
    assert result.roadmap_status == "complete"
    assert result.roadmap_error is None


def test_in_flight_job_is_not_started_twice(client, db, tenants, completed_assessment, monkeypatch):
    result = _result(db, completed_assessment)
    result.analysis_status = "generating"
    result.analysis_started_at = datetime.utcnow()
    db.commit()
    calls = []
    monkeypatch.setattr(ai_agents, "generate_analysis", lambda *a: calls.append(1) or ANALYSIS)

    r = client.post(f"/assessments/{completed_assessment.id}/analyse?force=true",
                    headers=auth_headers(tenants["assessor_a"]))

    assert r.json()["status"] == "generating"
    assert calls == []


def test_stale_job_is_restarted(client, db, tenants, completed_assessment, monkeypatch):
    result = _result(db, completed_assessment)
    result.analysis_status = "generating"
    result.analysis_started_at = datetime.utcnow() - timedelta(hours=1)
    db.commit()
    monkeypatch.setattr(ai_agents, "generate_analysis", lambda *a: ANALYSIS)

    client.post(f"/assessments/{completed_assessment.id}/analyse", headers=auth_headers(tenants["assessor_a"]))

    assert _result(db, completed_assessment).analysis_status == "complete"


def test_ai_generation_requires_completed_assessment(client, db, tenants):
    draft = Assessment(organisation_id=tenants["org_a"].id, created_by_id=tenants["assessor_a"].id,
                       status="in_progress")
    db.add(draft)
    db.commit()
    r = client.post(f"/assessments/{draft.id}/analyse", headers=auth_headers(tenants["assessor_a"]))
    assert r.status_code == 400
