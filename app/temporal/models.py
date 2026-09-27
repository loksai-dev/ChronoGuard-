from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


def parse_utc(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text).astimezone(timezone.utc)


def iso(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


class BiTemporalFact(BaseModel):
    """A graph fact with valid time (world) and transaction time (knowledge)."""

    valid_from: datetime
    valid_to: datetime | None = None
    transaction_from: datetime
    transaction_to: datetime | None = None
    payload: dict[str, Any] = Field(default_factory=dict)

    def valid_at(self, when: datetime) -> bool:
        when = parse_utc(when)
        if when < parse_utc(self.valid_from):
            return False
        if self.valid_to is not None and when >= parse_utc(self.valid_to):
            return False
        return True

    def known_at(self, when: datetime) -> bool:
        when = parse_utc(when)
        if when < parse_utc(self.transaction_from):
            return False
        if self.transaction_to is not None and when >= parse_utc(self.transaction_to):
            return False
        return True
