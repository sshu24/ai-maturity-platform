from types import SimpleNamespace

import anthropic
import httpx2
import pytest

from app.components import ai_agents
from app.components.ai_agents import AIGenerationError, Roadmap


def _roadmap():
    initiative = {
        "title": "Data catalogue", "description": "d", "dimension": "Data & Data Infrastructure",
        "owner": "Head of Data", "effort": "Low", "impact": "High", "dependencies": "None",
        "score_improvement": 0.5, "business_value": "bv", "cost_of_inaction": "c", "roi_signal": "r",
    }
    return Roadmap.model_validate({
        "roadmap_summary": "s", "target_overall_score": 3.2, "target_maturity_label": "Defined",
        "estimated_business_value": "v",
        "phases": [{
            "phase": 1, "name": "Foundation", "months": "Months 1-2", "theme": "t",
            "business_objective": "o", "initiatives": [initiative],
            "target_dimension_scores": [{"dimension": "Data & Data Infrastructure", "score": 2.8}],
            "phase_business_outcome": "p",
        }],
    })


class FakeClient:
    def __init__(self, response=None, error=None):
        self._response, self._error = response, error
        self.calls = []
        self.messages = self

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        if self._error:
            raise self._error
        return self._response


def _response(parsed, stop_reason="end_turn"):
    return SimpleNamespace(
        parsed_output=parsed, stop_reason=stop_reason,
        usage=SimpleNamespace(input_tokens=10, output_tokens=20),
    )


def _use(monkeypatch, fake):
    monkeypatch.setattr(ai_agents, "_client", lambda: fake)
    return fake


_RESULT = SimpleNamespace(
    overall_score=2.5, maturity_label="Developing", maturity_tier=2,
    dimension_scores=[{"id": "data_infrastructure", "label": "Data & Data Infrastructure",
                       "score": 2.5, "tier_label": "Developing"}],
)


def test_roadmap_target_scores_are_stored_as_mapping(monkeypatch):
    fake = _use(monkeypatch, FakeClient(_response(_roadmap())))

    roadmap = ai_agents.generate_roadmap(_RESULT)

    assert roadmap["phases"][0]["target_dimension_scores"] == {"Data & Data Infrastructure": 2.8}
    assert fake.calls[0]["output_format"] is Roadmap
    assert "Data & Data Infrastructure: 2.5/5.0" in fake.calls[0]["messages"][0]["content"]


@pytest.mark.parametrize("stop_reason, parsed, message", [
    ("refusal", None, "declined"),
    ("max_tokens", None, "cut off"),
    ("end_turn", None, "unexpected format"),
])
def test_unusable_responses_raise(monkeypatch, stop_reason, parsed, message):
    _use(monkeypatch, FakeClient(_response(parsed, stop_reason)))
    with pytest.raises(AIGenerationError, match=message):
        ai_agents.generate_roadmap(_RESULT)


_REQUEST = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")


def _status_error(cls, code):
    return cls("err", response=httpx2.Response(code, request=_REQUEST), body=None)


@pytest.mark.parametrize("error, message", [
    (_status_error(anthropic.AuthenticationError, 401), "API key is invalid"),
    (_status_error(anthropic.RateLimitError, 429), "rate limited"),
    (_status_error(anthropic.InternalServerError, 500), "temporarily unavailable"),
    (_status_error(anthropic.BadRequestError, 400), r"rejected the request \(400\)"),
    (anthropic.APITimeoutError(request=_REQUEST), "too long"),
    (anthropic.APIConnectionError(request=_REQUEST), "Could not reach"),
])
def test_api_errors_become_readable_messages(monkeypatch, error, message):
    _use(monkeypatch, FakeClient(error=error))
    with pytest.raises(AIGenerationError, match=message):
        ai_agents.generate_roadmap(_RESULT)


def test_missing_api_key_is_reported(monkeypatch):
    monkeypatch.undo()  # restore the real _client
    ai_agents._client.cache_clear()
    monkeypatch.setattr(ai_agents, "get_settings", lambda: SimpleNamespace(ANTHROPIC_API_KEY=""))
    with pytest.raises(AIGenerationError, match="not configured"):
        ai_agents._client()


def test_analysis_prompt_only_includes_weak_answers():
    bank = SimpleNamespace(dimensions=[SimpleNamespace(
        id="data_infrastructure", label="Data & Data Infrastructure",
        questions=[SimpleNamespace(id="q1", text="Strong question"),
                   SimpleNamespace(id="q2", text="Weak question")],
    )])
    responses = [
        SimpleNamespace(question_id="q1", dimension="data_infrastructure", answer_value=5, answer_label="great"),
        SimpleNamespace(question_id="q2", dimension="data_infrastructure", answer_value=2, answer_label="poor"),
    ]
    prompt = ai_agents.build_analysis_prompt(_RESULT, responses, bank)
    assert "Weak question" in prompt
    assert "Strong question" not in prompt
