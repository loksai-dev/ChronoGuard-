from datetime import datetime

from app.temporal.models import parse_utc


def valid_time_predicate(alias: str = "r") -> str:
    return (
        f"datetime($at) >= datetime({alias}.valid_from) AND "
        f"({alias}.valid_to IS NULL OR datetime($at) < datetime({alias}.valid_to))"
    )


def transaction_time_predicate(alias: str = "r") -> str:
    return (
        f"datetime($at) >= datetime({alias}.transaction_from) AND "
        f"({alias}.transaction_to IS NULL OR datetime($at) < datetime({alias}.transaction_to))"
    )


def as_utc_param(when: datetime | str) -> str:
    value = parse_utc(when)
    return value.replace(microsecond=0).isoformat().replace("+00:00", "Z")
