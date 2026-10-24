"""Deterministic checks for a small, read-only procurement pilot.

Every result requires a named human review. This module never selects a
supplier, approves a purchase, writes to a source system, or makes a payment.
"""

from __future__ import annotations

from datetime import date
from typing import Any


REQUIRED_REQUEST_FIELDS = ("business_id", "version", "cas", "concentration", "package")
REQUIRED_CATALOG_FIELDS = ("cas", "concentration", "package", "updated_at")


def _missing_fields(record: dict[str, Any], fields: tuple[str, ...]) -> list[str]:
    return [field for field in fields if not str(record.get(field, "")).strip()]


def _normalized(value: Any) -> str:
    return " ".join(str(value or "").strip().casefold().split())


def review_request(
    request: dict[str, Any],
    catalog: list[dict[str, Any]],
    *,
    as_of: date,
    max_catalog_age_days: int = 30,
) -> dict[str, Any]:
    """Return evidence-backed flags for one request without approving it."""
    if max_catalog_age_days < 0:
        raise ValueError("max_catalog_age_days must be non-negative")
    missing = _missing_fields(request, REQUIRED_REQUEST_FIELDS)
    if missing:
        raise ValueError(f"request missing required fields: {', '.join(missing)}")

    cas = _normalized(request["cas"])
    candidates = [item for item in catalog if _normalized(item.get("cas")) == cas]
    reasons: list[str] = []
    evidence: list[str] = []
    matched_skus: list[str] = []

    if not candidates:
        reasons.append("catalog_item_missing")
        evidence.append("research-procurement-f31")
    else:
        exact = [
            item for item in candidates
            if _normalized(item.get("concentration")) == _normalized(request["concentration"])
            and _normalized(item.get("package")) == _normalized(request["package"])
        ]
        if not exact:
            reasons.append("specification_mismatch")
            evidence.append("research-procurement-f10")
        elif len(exact) != 1:
            reasons.append("ambiguous_catalog_match")
            evidence.append("research-procurement-f33")
        else:
            item = exact[0]
            matched_skus = [str(item.get("sku", ""))]
            missing_catalog = _missing_fields(item, REQUIRED_CATALOG_FIELDS)
            if missing_catalog:
                reasons.append("catalog_evidence_incomplete")
                evidence.append("research-procurement-f33")
            else:
                try:
                    age = (as_of - date.fromisoformat(str(item["updated_at"]))).days
                except ValueError:
                    reasons.append("catalog_date_invalid")
                else:
                    if age < 0 or age > max_catalog_age_days:
                        reasons.append("catalog_data_stale")
                if reasons:
                    evidence.append("research-procurement-f33")

    if request.get("cold_chain") and not request.get("temperature_log_present"):
        reasons.append("temperature_log_missing")
        evidence.extend(("research-procurement-f11", "research-procurement-f40"))
    if request.get("hazardous") and not request.get("safety_approval_present"):
        reasons.append("safety_approval_missing")
        evidence.append("research-procurement-f40")
    if not request.get("budget_approval_present"):
        reasons.append("budget_approval_missing")
        evidence.append("research-procurement-f40")
    if not str(request.get("handoff_receiver", "")).strip() or not request.get("handoff_confirmed"):
        reasons.append("handoff_unconfirmed")
        evidence.append("research-procurement-f23")

    return {
        "business_id": str(request["business_id"]),
        "version": str(request["version"]),
        "status": "human_review_required" if reasons else "ready_for_human_review",
        "matched_skus": matched_skus,
        "reasons": reasons,
        "evidence_ids": list(dict.fromkeys(evidence)),
        "approved": False,
    }


def review_batch(
    payload: dict[str, Any], *, as_of: date, max_catalog_age_days: int = 30
) -> dict[str, Any]:
    """Review all requests and calculate transparent pilot counts."""
    catalog = payload.get("catalog")
    requests = payload.get("requests")
    if not isinstance(catalog, list) or not isinstance(requests, list):
        raise ValueError("input must contain catalog and requests arrays")
    if not all(isinstance(item, dict) for item in catalog + requests):
        raise ValueError("catalog and requests must contain objects")
    results = [
        review_request(item, catalog, as_of=as_of, max_catalog_age_days=max_catalog_age_days)
        for item in requests
    ]
    return {
        "as_of": as_of.isoformat(),
        "total_requests": len(results),
        "ready_for_human_review": sum(r["status"] == "ready_for_human_review" for r in results),
        "human_review_required": sum(r["status"] == "human_review_required" for r in results),
        "results": results,
    }
