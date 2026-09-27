import pytest

from app.config import Settings
from app.integrations.jev import JevClient, JevTriageError, map_jev_answers
from app.integrations.openrouter import OpenRouterError, OpenRouterTransientError
from tests.conftest import SAMPLE_ANSWERS


def settings(**kwargs) -> Settings:
    data = {
        "openrouter_api_key": "test-key",
        "jev_confidence_threshold": 0.85,
        "jev_malicious_threshold": 0.7,
    }
    data.update(kwargs)
    return Settings(**data)


def test_map_high_confidence_pipeline_incident():
    decision = map_jev_answers(
        answers=SAMPLE_ANSWERS,
        settings=settings(),
        raw_body={"model": "typesafe/jev-1.13", "usage": {"input_tokens": 12}},
        jev_latency_ms=42,
        openrouter_latency_ms=40,
    )
    assert decision.category.value == "pipeline"
    assert decision.target_component == "sales_daily"
    assert decision.confidence >= 0.85
    assert decision.recommended_route.value == "investigate"
    assert decision.jev_latency_ms == 42


def test_invalid_jev_response_missing_answers():
    with pytest.raises(JevTriageError):
        map_jev_answers(
            answers={"category": {"type": "choice"}},
            settings=settings(),
            raw_body={},
            jev_latency_ms=1,
            openrouter_latency_ms=1,
        )


@pytest.mark.asyncio
async def test_openrouter_timeout_is_not_swallowed():
    class Boom:
        async def create_decision(self, **kwargs):
            raise OpenRouterTransientError("OpenRouter request timed out")

    client = JevClient(settings(), openrouter=Boom())  # type: ignore[arg-type]
    with pytest.raises(OpenRouterError):
        await client.triage(title="x", description="sales_daily failed because Athena timed out")
