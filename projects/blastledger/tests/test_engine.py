import copy
import json
from pathlib import Path
import unittest

from blastledger import InputError, assess

ROOT = Path(__file__).resolve().parents[1]


def fixture(name):
    return json.loads((ROOT / "fixtures" / name).read_text(encoding="utf-8"))


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
        self.assertEqual(assess(fixture("unknown.json"))["verdict"], "UNKNOWN")

    def test_does_not_mutate_input(self):
        d = fixture("danger.json")
        self.assertEqual(assess(d), assess(copy.deepcopy(d)))

    def test_replay_is_deterministic(self):
        self.assertEqual(assess(fixture("danger.json")), assess(fixture("danger.json")))

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

    def test_schema_rejects_unknown_top_level_fields(self):
        d = fixture("healthy.json")
        d["untrusted"] = "nope"
        with self.assertRaises(InputError): assess(d)

    def test_schema_rejects_unknown_service_fields(self):
        d = fixture("healthy.json")
        d["services"][0]["new_unknown"] = 123
        with self.assertRaises(InputError): assess(d)

    def test_contradictory_headroom_declared_is_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["current_rps"] = 1001
        with self.assertRaisesRegex(InputError, "inconsistent"): assess(d)

    def test_invalid_calendar_date_rejected(self):
        d = fixture("healthy.json")
        d["as_of"] = "2026-02-31"
        with self.assertRaises(InputError): assess(d)

    def test_cyclic_traversal_critical_transitive(self):
        d = fixture("danger.json")
        d["services"].append({"id": "fulfillment", "criticality": "critical", "dependencies": ["orders-api"], "replicas": 2})
        d["services"][1]["dependencies"].append("fulfillment")
        result = assess(d)
        self.assertIn("fulfillment", result["impacted_services"])

    def test_input_hash_full_digest_is_stable(self):
        result = assess(fixture("healthy.json"))
        self.assertEqual(len(result["input_hash"]), 64)
        self.assertEqual(result["assessment_id"], result["input_hash"][:20])

    def test_duplicate_changed_service_rejected(self):
        d = fixture("healthy.json")
        d["change"]["affected_services"].append("search-api")
        with self.assertRaises(InputError): assess(d)

    def test_huge_graph_rejected(self):
        d = fixture("healthy.json")
        d["services"] = [{**d["services"][0], "id": f"svc{i}"} for i in range(501)]
        with self.assertRaises(InputError): assess(d)

    def test_missing_critical_replica_yields_unknown(self):
        d = fixture("healthy.json")
        del d["services"][0]["replicas"]
        self.assertEqual(assess(d)["verdict"], "UNKNOWN")

    def test_malformed_date_stale_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["capacity_observed_at"] = "not a date"
        with self.assertRaises(InputError): assess(d)

    def test_nonfinite_capacity_rejected(self):
        d = fixture("healthy.json")
        d["services"][0]["max_rps"] = float("nan")
        with self.assertRaises(InputError): assess(d)
