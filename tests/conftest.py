from typing import Any

SAMPLE_ANSWERS: dict[str, Any] = {
    "category": {
        "type": "choice",
        "choice": "pipeline",
        "confidence": 0.91,
        "probabilities": {"pipeline": 0.91, "database": 0.09},
    },
    "severity": {
        "type": "score",
        "score": 6.2,
        "confidence": 0.88,
        "probabilities": {"6": 0.7, "7": 0.3},
    },
    "is_malicious": {"type": "noul", "noul": 0.02},
    "target_component": {
        "type": "choice",
        "choice": "sales_daily",
        "confidence": 0.9,
        "probabilities": {"sales_daily": 0.9},
    },
    "missing_information": {"type": "noul", "noul": 0.05},
    "requires_human_review": {"type": "noul", "noul": 0.1},
    "recommended_route": {
        "type": "choice",
        "choice": "investigate",
        "confidence": 0.9,
        "probabilities": {"investigate": 0.9},
    },
    "reason_code": {
        "type": "choice",
        "choice": "pipeline_timeout",
        "confidence": 0.86,
        "probabilities": {"pipeline_timeout": 0.86},
    },
    "remediation_risk": {
        "type": "choice",
        "choice": "low",
        "confidence": 0.87,
        "probabilities": {"low": 0.87},
    },
}
