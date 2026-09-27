from datetime import datetime, timezone

from app.temporal.models import BiTemporalFact, parse_utc


def test_valid_time_vs_transaction_time():
    fact = BiTemporalFact(
        valid_from=parse_utc("2026-09-27T02:00:00Z"),
        valid_to=None,
        transaction_from=parse_utc("2026-09-27T02:35:00Z"),
        transaction_to=None,
        payload={"rel": "READS_FROM", "to": "query_service"},
    )
    at_0200 = datetime(2026, 9, 27, 2, 0, tzinfo=timezone.utc)
    at_0210 = datetime(2026, 9, 27, 2, 10, tzinfo=timezone.utc)

    assert fact.valid_at(at_0200) is True
    assert fact.known_at(at_0200) is False
    assert fact.valid_at(at_0210) is True
    assert fact.known_at(at_0210) is False


def test_temporal_reconstruction_diff_shape():
    from app.investigation.temporal_reconstruction import _summarize_diff

    world = [{"from_name": "sales_daily", "rel": "READS_FROM", "to_name": "query_service"}]
    knowledge = [{"from_name": "sales_daily", "rel": "READS_FROM", "to_name": "athena"}]
    diff = _summarize_diff(world, knowledge)
    assert ["sales_daily", "READS_FROM", "query_service"] in diff["world_only"]
    assert ["sales_daily", "READS_FROM", "athena"] in diff["knowledge_only"]
