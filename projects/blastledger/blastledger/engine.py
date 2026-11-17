"""Pure, deterministic read-only graph and declared-capacity risk engine.

No network calls, I/O, credential use, LLM calls or mutating operations.
Results are advisory, not outage predictions or deployment approvals.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date
from hashlib import sha256
import json
from typing import Any

from .contract import ContractError, validate_assessment


class InputError(ValueError):
    """Input contract or semantic error safe for a review tool to display."""


def _impacted(services: dict[str, dict[str, Any]], changed: list[str]) -> list[str]:
    """Graph edges service -> dependency; reverse them to find dependent callers."""
    callers: dict[str, set[str]] = defaultdict(set)
    for sid, service in services.items():
        for dependency in service["dependencies"]:
            callers[dependency].add(sid)
    pending = deque(sorted(set(changed)))
    visited: set[str] = set()
    while pending:
        sid = pending.popleft()
        if sid in visited:
            continue
        visited.add(sid)
        pending.extend(sorted(callers[sid] - visited))
    return sorted(visited)


def assess(data: dict[str, Any]) -> dict[str, Any]:
    """Return evidence-backed advice. Identical JSON input yields identical output."""
    try:
        validate_assessment(data)
    except ContractError as exc:
        raise InputError(str(exc)) from exc
    services = {s["id"]: s for s in data["services"]}
    change = data["change"]
    changed = sorted(set(change["affected_services"]))
    impacted = _impacted(services, changed)
    as_of = date.fromisoformat(data["as_of"])
    findings: list[dict[str, Any]] = []

    def emit(rule: str, severity: str, sid: str, detail: str, evidence: dict[str, Any]) -> None:
        findings.append({"rule_id": rule, "severity": severity, "service_id": sid,
                         "detail": detail, "evidence": evidence})

    for sid in changed:
        service = services[sid]
        critical = [x for x in impacted if x != sid and services[x]["criticality"] == "critical"]
        if critical:
            emit("CRITICAL_DEPENDENTS", "REVIEW", sid,
                 "Changed component is upstream of critical service(s); assess blast radius.",
                 {"critical_dependents": critical})

        replicas = service.get("replicas")
        if replicas is None:
            emit("REPLICA_UNKNOWN", "UNKNOWN", sid,
                 "Redundancy information is missing.", {"replicas": None})
        elif replicas < 2 and service["criticality"] in ("critical", "high"):
            emit("INSUFFICIENT_REPLICAS", "BLOCK" if service["criticality"] == "critical" else "REVIEW", sid,
                 "Fewer than two declared replicas for a high-impact component.",
                 {"replicas": replicas, "criticality": service["criticality"]})

        capacity_fields = ("max_rps", "current_rps", "required_failover_rps")
        missing = [name for name in capacity_fields if service.get(name) is None]
        if service.get("capacity_observed_at") is None:
            missing.append("capacity_observed_at")
        if missing:
            emit("CAPACITY_UNKNOWN", "UNKNOWN", sid,
                 "Capacity data is incomplete; no safe-release inference is possible.",
                 {"missing_fields": missing})
        else:
            observed = date.fromisoformat(service["capacity_observed_at"])
            age_days = (as_of - observed).days
            if age_days < 0 or age_days > 7:
                emit("CAPACITY_STALE", "UNKNOWN", sid,
                     "Capacity evidence is future-dated or more than 7 days old.",
                     {"age_days": age_days, "freshness_limit_days": 7})
            else:
                max_rps = float(service["max_rps"])
                current_rps = float(service["current_rps"])
                required = float(service["required_failover_rps"])
                spare = round(max_rps - current_rps, 4)
                if spare < required:
                    emit("LOW_FAILOVER_HEADROOM", "BLOCK", sid,
                         "Declared spare throughput is below required failover load.",
                         {"max_rps": max_rps, "current_rps": current_rps, "spare_rps": spare,
                          "required_failover_rps": required,
                          "capacity_observed_at": service["capacity_observed_at"]})
    rollback = change.get("rollback_ref")
    if not isinstance(rollback, str) or not rollback.strip():
        emit("ROLLBACK_MISSING", "REVIEW", ",".join(changed),
             "Rollback or runbook evidence is missing.", {"rollback_ref": None})

    severity_set = {f["severity"] for f in findings}
    verdict = ("BLOCK-RECOMMENDED" if "BLOCK" in severity_set else
               "UNKNOWN" if "UNKNOWN" in severity_set else
               "REVIEW" if "REVIEW" in severity_set else "PASS")
    canonical = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False)
    digest = sha256(canonical.encode("utf-8")).hexdigest()
    findings.sort(key=lambda f: (f["severity"], f["rule_id"], f["service_id"]))
    return {"assessment_id": digest[:20], "input_hash": digest,
            "ruleset_version": "1.0.0", "change_id": change["id"], "as_of": as_of.isoformat(),
            "changed_services": changed, "impacted_services": impacted,
            "verdict": verdict, "findings": findings,
            "disclaimer": "Advisory only; user-declared topology and metrics are unverified. PASS is not a safety guarantee."}
