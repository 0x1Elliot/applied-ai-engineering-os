"""Read-only, deterministic dependency blast-radius analysis.

No network, filesystem writes, customer credentials, or LLM calls.
The output is an engineering decision aid, not outage prediction.
"""
from __future__ import annotations

from collections import defaultdict, deque
from datetime import date
from hashlib import sha256
import json
from typing import Any


class InputError(ValueError):
    """Invalid assessment input. Safe to show to calling engineer."""


def _number(value: Any, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise InputError(f"{name} must be a nonnegative number")
    import math
    if not math.isfinite(value) or value < 0:
        raise InputError(f"{name} must be a finite nonnegative number")
    return float(value)


def _validate(data: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], dict[str, Any], date]:
    if not isinstance(data, dict) or set(data) - {"services", "change", "as_of"}:
        raise InputError("Input must contain only services, change, as_of")
    services = data.get("services")
    change = data.get("change")
    if not isinstance(services, list) or not (1 <= len(services) <= 500):
        raise InputError("services must be a list of 1..500 service records")
    if not isinstance(change, dict):
        raise InputError("change must be an object")
    try:
        as_of = date.fromisoformat(data["as_of"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InputError("as_of must be an ISO date YYYY-MM-DD") from exc
    mapped: dict[str, dict[str, Any]] = {}
    for item in services:
        if not isinstance(item, dict):
            raise InputError("Each service must be an object")
        sid = item.get("id")
        if not isinstance(sid, str) or not sid or len(sid) > 128:
            raise InputError("Service ID must be a nonempty string <=128 characters")
        if sid in mapped:
            raise InputError(f"Duplicate service ID: {sid}")
        deps = item.get("dependencies", [])
        if not isinstance(deps, list) or any(not isinstance(x, str) for x in deps):
            raise InputError(f"Invalid dependency list: {sid}")
        if item.get("criticality") not in ("low", "high", "critical"):
            raise InputError(f"Invalid criticality: {sid}")
        if len(set(deps)) != len(deps):
            raise InputError(f"Duplicate dependencies: {sid}")
        for field in ("max_rps", "current_rps", "required_failover_rps"):
            if field in item and item[field] is not None:
                _number(item[field], f"{sid}.{field}")
        replicas = item.get("replicas")
        if replicas is not None and (type(replicas) is not int or replicas < 0):
            raise InputError(f"{sid}.replicas must be a nonnegative integer")
        mapped[sid] = item
    for sid, item in mapped.items():
        for dep in item.get("dependencies", []):
            if dep not in mapped:
                raise InputError(f"Dangling dependency from {sid}: {dep}")
    ids = change.get("affected_services")
    if not isinstance(ids, list) or not ids or any(x not in mapped for x in ids):
        raise InputError("affected_services must be a nonempty list of existing service IDs")
    if not isinstance(change.get("id"), str) or not change["id"]:
        raise InputError("change.id must be a nonempty string")
    return mapped, change, as_of


def _impacted(services: dict[str, dict[str, Any]], changed: list[str]) -> list[str]:
    """Return changed services + all direct/indirect callers in stable order; cycles safe."""
    callers: dict[str, set[str]] = defaultdict(set)
    for sid, s in services.items():
        for dep in s.get("dependencies", []):
            callers[dep].add(sid)
    q = deque(sorted(set(changed)))
    visited: set[str] = set()
    while q:
        sid = q.popleft()
        if sid in visited:
            continue
        visited.add(sid)
        q.extend(sorted(callers[sid] - visited))
    return sorted(visited)


def assess(data: dict[str, Any]) -> dict[str, Any]:
    """Deterministic advisory result: PASS, REVIEW, UNKNOWN, BLOCK-RECOMMENDED.

    Values are declared from a fixture or a customer service manifest, not telemetry.
    PASS never means the planned change is guaranteed safe.
    """
    services, change, as_of = _validate(data)
    changed = sorted(set(change["affected_services"]))
    impacted = _impacted(services, changed)
    findings: list[dict[str, Any]] = []

    def emit(rule: str, severity: str, sid: str, detail: str, evidence: dict[str, Any]):
        findings.append({"rule_id": rule, "severity": severity, "service_id": sid,
                         "detail": detail, "evidence": evidence})

    for sid in changed:
        s = services[sid]
        dependents = [x for x in impacted if x != sid]
        critical = [x for x in dependents if services[x]["criticality"] == "critical"]
        if critical:
            emit("CRITICAL_DEPENDENTS", "REVIEW", sid,
                 "Changed component is upstream of critical service(s). Inspect blast radius.",
                 {"critical_dependents": critical})
        replica_count = s.get("replicas")
        if replica_count is None:
            emit("REPLICA_UNKNOWN", "UNKNOWN", sid, "Redundancy information is missing.", {})
        elif replica_count < 2 and s["criticality"] in ("high", "critical"):
            sev = "BLOCK" if s["criticality"] == "critical" else "REVIEW"
            emit("INSUFFICIENT_REPLICAS", sev, sid,
                 "Service has fewer than two declared replicas.",
                 {"replicas": replica_count, "criticality": s["criticality"]})
        required = ("max_rps", "current_rps", "required_failover_rps")
        missing = [f for f in required if s.get(f) is None]
        observed = s.get("capacity_observed_at")
        if missing or not observed:
            emit("CAPACITY_UNKNOWN", "UNKNOWN", sid,
                 "Capacity or evidence timestamp missing; cannot infer a safe release.",
                 {"missing_fields": missing + (["capacity_observed_at"] if not observed else [])})
        else:
            try:
                age = (as_of - date.fromisoformat(observed)).days
            except (ValueError, TypeError) as exc:
                raise InputError(f"{sid}.capacity_observed_at is not an ISO date") from exc
            if age < 0 or age > 7:
                emit("CAPACITY_STALE", "UNKNOWN", sid,
                     "Capacity observation is in the future or more than 7 days old.",
                     {"age_days": age, "freshness_limit_days": 7})
            else:
                maximum = _number(s["max_rps"], f"{sid}.max_rps")
                current = _number(s["current_rps"], f"{sid}.current_rps")
                required_failover = _number(s["required_failover_rps"], f"{sid}.required_failover_rps")
                spare = round(maximum - current, 4)
                if spare < required_failover:
                    emit("LOW_FAILOVER_HEADROOM", "BLOCK", sid,
                         "Declared spare capacity is below required failover capacity.",
                         {"max_rps": maximum, "current_rps": current,
                          "spare_rps": spare, "required_failover_rps": required_failover,
                          "capacity_observed_at": observed})
    rollback = change.get("rollback_ref")
    if not isinstance(rollback, str) or not rollback.strip():
        emit("ROLLBACK_MISSING", "REVIEW", ",".join(changed),
             "Rollback/runbook evidence is missing.", {"rollback_ref": None})

    severities = {x["severity"] for x in findings}
    if "BLOCK" in severities:
        verdict = "BLOCK-RECOMMENDED"
    elif "UNKNOWN" in severities:
        verdict = "UNKNOWN"
    elif "REVIEW" in severities:
        verdict = "REVIEW"
    else:
        verdict = "PASS"
    normalized = json.dumps(data, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    findings.sort(key=lambda x: (x["severity"], x["rule_id"], x["service_id"]))
    return {"change_id": change["id"], "assessment_id": sha256(normalized.encode()).hexdigest()[:20],
            "as_of": as_of.isoformat(), "changed_services": changed,
            "impacted_services": impacted, "verdict": verdict, "findings": findings,
            "disclaimer": "Advisory only. Manifest data is unverified. PASS is not a safety guarantee."}
