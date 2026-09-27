from copy import deepcopy

from app.integrations.jev import apply_confidence_gate, map_jev_answers
from app.models import RecommendedRoute
from tests.conftest import SAMPLE_ANSWERS
from tests.test_jev import settings


def test_low_confidence_requires_hitl():
    answers = deepcopy(SAMPLE_ANSWERS)
    answers["category"]["confidence"] = 0.4
    decision = map_jev_answers(
        answers=answers,
        settings=settings(),
        raw_body={},
        jev_latency_ms=1,
        openrouter_latency_ms=1,
    )
    gated = apply_confidence_gate(decision, settings())
    assert gated.requires_human_review is True
    assert gated.recommended_route == RecommendedRoute.HUMAN_REVIEW


def test_malicious_incident_is_blocked():
    answers = deepcopy(SAMPLE_ANSWERS)
    answers["is_malicious"]["noul"] = 0.95
    answers["category"]["choice"] = "security"
    decision = map_jev_answers(
        answers=answers,
        settings=settings(),
        raw_body={},
        jev_latency_ms=1,
        openrouter_latency_ms=1,
    )
    assert decision.is_malicious is True
    assert decision.recommended_route == RecommendedRoute.BLOCKED


def test_missing_information_routes_to_human():
    answers = deepcopy(SAMPLE_ANSWERS)
    answers["missing_information"]["noul"] = 0.9
    decision = map_jev_answers(
        answers=answers,
        settings=settings(),
        raw_body={},
        jev_latency_ms=1,
        openrouter_latency_ms=1,
    )
    assert decision.missing_information is True
    assert decision.recommended_route == RecommendedRoute.HUMAN_REVIEW
