"""Run: python -m unittest discover -s tests -v"""
import copy
import json
from pathlib import Path
import unittest
from blastledger import assess, InputError

ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text())


class TestRiskEngine(unittest.TestCase):
    def test_danger_blocks_for_capacity(self):
        result = assess(fixture("danger.json"))
        self.assertEqual(result["verdict"], "BLOCK-RECOMMENDED")
        self.assertIn("LOW_FAILOVER_HEADROOM", {x["rule_id"] for x in result["findings"]})
        self.assertIn("checkout-api", result["impacted_services"])
        self.assertEqual(next(x for x in result["findings"] if x["rule_id"] == "LOW_FAILOVER_HEADROOM")["evidence"]["spare_rps"], 120)

    def test_healthy_passes_defined_rules(self):
        self.assertEqual(assess(fixture("healthy.json"))["verdict"], "PASS")

    def test_missing_metrics_never_passes(self):
        r = assess(fixture("unknown.json"))
        self.assertEqual(r["verdict"], "UNKNOWN")
        self.assertIn("CAPACITY_UNKNOWN", [x["rule_id"] for x in r["findings"]])

    def test_read_only_does_not_mutate_input(self):
        d = fixture("danger.json")
        original = copy.deepcopy(d)
        assess(d)
        self.assertEqual(original, d)

    def test_replay_is_deterministic(self):
        d = fixture("danger.json")
        self.assertEqual(assess(d), assess(copy.deepcopy(d)))

    def test_cycle_is_bounded(self):
        d = fixture("healthy.json")
        d["services"][0]["dependencies"] = ["other"]
        d["services"].append({"id": "other", "criticality": "low", "dependencies": ["search-api"], "replicas": 2})
        self.assertEqual(assess(d)["impacted_services"], ["other", "search-api"])

    def test_duplicate_services_rejected(self):
        d = fixture("healthy.json")
        d["services"].append(copy.deepcopy(d["services"][0]))
        with self.assertRaises(InputError): assess(d)

    def test_dangling_dependency_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["dependencies"] = ["nonexistent"]
        with self.assertRaises(InputError): assess(d)

    def test_stale_evidence_is_unknown(self):
        d = fixture("healthy.json")
        d["services"][0]["capacity_observed_at"] = "2026-01-01"
        self.assertEqual(assess(d)["verdict"], "UNKNOWN")

    def test_single_critical_replica_blocks(self):
        d = fixture("unknown.json")
        d["services"][0]["replicas"] = 1
        self.assertEqual(assess(d)["verdict"], "BLOCK-RECOMMENDED")

    def test_missing_rollback_warns(self):
        d = fixture("healthy.json")
        d["change"]["rollback_ref"] = ""
        self.assertEqual(assess(d)["verdict"], "REVIEW")

    def test_bool_capacity_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["current_rps"] = True
        with self.assertRaises(InputError): assess(d)

    def test_unknown_changed_service_rejected(self):
        d = fixture("healthy.json")
        d["change"]["affected_services"] = ["ghost"]
        with self.assertRaises(InputError): assess(d)

    def test_negative_capacity_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["max_rps"] = -1
        with self.assertRaises(InputError): assess(d)


if __name__ == "__main__":
    unittest.main()
