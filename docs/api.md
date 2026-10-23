# CLI and JSON interface

## Command

```bash
PYTHONPATH=src python -m my_tool.main review \
  --input data/sample_requests.json \
  --config config/default.yaml \
  --as-of 2026-10-23 \
  --output review.json
```

`--output` is optional; omitting it prints JSON to standard output. `--as-of` makes freshness checks reproducible. The CLI reads only local files and has no service credentials or network API.

## Input

Top-level JSON object with `catalog` and `requests` arrays. Each catalog entry requires `cas`, `concentration`, `package`, and ISO date `updated_at`. `sku` is an output reference. Each request requires `business_id`, `version`, `cas`, `concentration`, and `package`. Optional booleans are `cold_chain`, `temperature_log_present`, `hazardous`, `safety_approval_present`, `budget_approval_present`, and `handoff_confirmed`; `handoff_receiver` is a string. Missing approval/evidence booleans are treated as false.

CAS identifies candidates, then concentration and package must match exactly after case/whitespace normalization. This is a conservative demonstration rule; production unit conversion and equivalence rules require a named rule owner and validation. Multiple exact candidates are marked ambiguous. The prototype does not choose a supplier.

## Output

The JSON response includes `as_of`, `total_requests`, `ready_for_human_review`, `human_review_required`, and a `results` array. Each result contains `business_id`, `version`, `status`, `matched_skus`, `reasons`, `evidence_ids`, and `approved: false`.

Possible `reasons` are `catalog_item_missing`, `specification_mismatch`, `ambiguous_catalog_match`, `catalog_evidence_incomplete`, `catalog_date_invalid`, `catalog_data_stale`, `temperature_log_missing`, `safety_approval_missing`, `budget_approval_missing`, and `handoff_unconfirmed`.

`ready_for_human_review` means these local checks found no issue. It does not mean a purchase is authorized. A reviewer must verify the underlying records and follow the organization's approval chain.
