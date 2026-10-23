"""Behavior tests for risky and ambiguous procurement cases."""

import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from my_tool.core.review import review_batch, review_request  # noqa: E402


TODAY = date(2026, 10, 23)
ITEM = {"cas": "64-17-5", "sku": "A", "concentration": "70%", "package": "500 mL", "updated_at": "2026-10-20"}
REQUEST = {"business_id": "R-1", "version": "v1", "cas": "64-17-5", "concentration": "70%", "package": "500 mL", "budget_approval_present": True, "handoff_receiver": "reviewer", "handoff_confirmed": True}


class ReviewTests(unittest.TestCase):
    def test_clean_match_still_requires_human_review(self):
        result = review_request(REQUEST, [ITEM], as_of=TODAY)
        self.assertEqual(result["status"], "ready_for_human_review")
        self.assertFalse(result["approved"])

    def test_ambiguous_match_never_suggests_one_supplier(self):
        result = review_request(REQUEST, [ITEM, {**ITEM, "sku": "B"}], as_of=TODAY)
        self.assertIn("ambiguous_catalog_match", result["reasons"])
        self.assertEqual(result["matched_skus"], [])

    def test_cold_chain_and_handoff_fail_closed(self):
        request = {**REQUEST, "cold_chain": True, "temperature_log_present": False, "handoff_confirmed": False}
        result = review_request(request, [ITEM], as_of=TODAY)
        self.assertIn("temperature_log_missing", result["reasons"])
        self.assertIn("handoff_unconfirmed", result["reasons"])
        self.assertEqual(result["status"], "human_review_required")

    def test_stale_catalog_is_flagged(self):
        result = review_request(REQUEST, [{**ITEM, "updated_at": "2026-08-01"}], as_of=TODAY)
        self.assertIn("catalog_data_stale", result["reasons"])

    def test_batch_counts(self):
        result = review_batch({"catalog": [ITEM], "requests": [REQUEST, {**REQUEST, "business_id": "R-2", "budget_approval_present": False}]}, as_of=TODAY)
        self.assertEqual((result["ready_for_human_review"], result["human_review_required"]), (1, 1))


if __name__ == "__main__":
    unittest.main()
