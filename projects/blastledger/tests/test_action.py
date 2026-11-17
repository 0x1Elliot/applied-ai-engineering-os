import json
from pathlib import Path
import pytest

from blastledger.action import compile_assessment, render_comment, _safe
from blastledger.contract import validate_manifest, ContractError

ROOT = Path(__file__).resolve().parents[1]
SHA = "a" * 40


def sample():
    return json.loads((ROOT / "examples" / "blastledger.json").read_text())


def test_manifest_is_valid():
    validate_manifest(sample())


def test_mapped_code_change_never_claims_pass_with_missing_capacity():
    report = compile_assessment(sample(), ["app/page.tsx"], 12, SHA, as_of="2026-11-17")
    assert report["verdict"] == "UNKNOWN"
    assert "web" in report["changed_services"]
    assert report["input_hash"]


def test_unmapped_files_are_unknown_not_pass():
    report = compile_assessment(sample(), ["docs/README.md"], 12, SHA, as_of="2026-11-17")
    assert report["verdict"] == "UNKNOWN"
    assert report["findings"][0]["rule_id"] == "NO_MAPPED_SERVICES"


def test_mixed_paths_remain_unknown():
    report = compile_assessment(sample(), ["app/page.tsx", "docs/spec.txt"], 12, SHA, as_of="2026-11-17")
    assert report["verdict"] == "UNKNOWN"
    assert "UNMAPPED_PATHS" in [f["rule_id"] for f in report["findings"]]


def test_blocking_capacity_overrides_unmapped_unknown():
    m = sample()
    m["services"][0].update(replicas=2, max_rps=1000, current_rps=900,
                             required_failover_rps=300, capacity_observed_at="2026-11-17")
    report = compile_assessment(m, ["app/page.tsx", "docs/spec.txt"], 12, SHA, as_of="2026-11-17")
    assert report["verdict"] == "BLOCK-RECOMMENDED"


def test_bot_comment_includes_a_rule_and_disclaimer():
    r = compile_assessment(sample(), ["app/page.tsx"], 12, SHA, as_of="2026-11-17")
    comment = render_comment(r)
    assert "BlastLedger" in comment
    assert "safety guarantee" in comment
    assert "REPLICA_UNKNOWN" in comment


def test_escapes_untrusted_markdown():
    assert "[click](" not in _safe("[click](https://evil.example)")


def test_manifest_rejects_unknown_mapped_id():
    m = sample()
    m["path_rules"]["ghost"] = ["foo/**"]
    with pytest.raises(ContractError): validate_manifest(m)


def test_manifest_rejects_unknown_fields():
    m = sample()
    m["execute"] = "rm -rf"
    with pytest.raises(ContractError): validate_manifest(m)


def test_rollbacks_require_evidence():
    m = sample()
    m["services"][0].update(replicas=2, max_rps=1000, current_rps=100,
                             required_failover_rps=300, capacity_observed_at="2026-11-17")
    # The service is upstream of no critical callers; check missing rollback remains a warning.
    report = compile_assessment(m, ["app/page.tsx"], 12, SHA, as_of="2026-11-17")
    assert report["verdict"] in ("UNKNOWN", "REVIEW")
    assert "ROLLBACK_MISSING" in [f["rule_id"] for f in report["findings"]]


def test_action_opt_in_block_fails_only_for_block(monkeypatch, tmp_path):
    import blastledger.action as a
    event = {"pull_request": {"number": 51,
              "head": {"repo": {"full_name": "0x1Elliot/applied-ai-engineering-os"}, "sha": SHA}}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "0x1Elliot/applied-ai-engineering-os")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-test-token")
    monkeypatch.setenv("BLASTLEDGER_BLOCK_ON_HIGH_RISK", "true")
    monkeypatch.setattr(a, "_list_files", lambda *args: ["app/page.tsx"])
    m = sample()
    m["services"][0].update(replicas=2, max_rps=1000, current_rps=950,
                             required_failover_rps=150, capacity_observed_at="2026-11-17")
    monkeypatch.setattr(a, "_read_manifest", lambda *args: m)
    monkeypatch.setattr(a, "_upsert_comment", lambda *args: None)
    monkeypatch.setattr(a, "datetime", type("FixedTime", (), {"now": staticmethod(lambda _: __import__("datetime").datetime(2026, 11, 17, tzinfo=__import__("datetime").timezone.utc))}))
    assert a.main() == 1


def test_action_advisory_unknown_exits_zero(monkeypatch, tmp_path):
    import blastledger.action as a
    event = {"pull_request": {"number": 51,
              "head": {"repo": {"full_name": "0x1Elliot/applied-ai-engineering-os"}, "sha": SHA}}}
    event_path = tmp_path / "event.json"
    event_path.write_text(json.dumps(event))
    monkeypatch.setenv("GITHUB_EVENT_PATH", str(event_path))
    monkeypatch.setenv("GITHUB_REPOSITORY", "0x1Elliot/applied-ai-engineering-os")
    monkeypatch.setenv("GITHUB_TOKEN", "fake-test-token")
    monkeypatch.setenv("BLASTLEDGER_BLOCK_ON_HIGH_RISK", "true")
    monkeypatch.setattr(a, "_list_files", lambda *args: ["docs/file.md"])
    monkeypatch.setattr(a, "_read_manifest", lambda *args: sample())
    monkeypatch.setattr(a, "_upsert_comment", lambda *args: None)
    assert a.main() == 0
