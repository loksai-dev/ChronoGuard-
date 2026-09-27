"""Submit the canonical demo incident to a running ChronoGuard API."""

from __future__ import annotations

import json
import os
import sys
import urllib.request

API = os.getenv("CHRONOGUARD_API", "http://localhost:8000")
BODY = {
    "title": "sales_daily Airflow failure",
    "description": (
        "sales_daily failed at 02:14 UTC because Athena timed out and "
        "sales_fact_detail was not refreshed. The pipeline normally completes within 8 minutes."
    ),
    "occurred_at": "2026-09-27T02:14:00Z",
    "logs": ["Athena QueryTimeout", "DAG sales_daily failed"],
}


def main() -> None:
    req = urllib.request.Request(
        f"{API}/incidents",
        data=json.dumps(BODY).encode(),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=120) as res:
        payload = json.loads(res.read().decode())
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
