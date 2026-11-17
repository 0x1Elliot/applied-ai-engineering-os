"""Versioned JSON Schema validation, shared by CLI, API, and PR workflow."""
from __future__ import annotations

from datetime import date
from importlib.resources import files
import math
from typing import Any

from jsonschema import Draft202012Validator, FormatChecker, RefResolver


class ContractError(ValueError):
    pass


def _schema(name: str) -> dict[str, Any]:
    import json
    return json.loads((files("blastledger") / "schemas" / name).read_text(encoding="utf-8"))


def _check(payload: Any, filename: str) -> None:
    schema = _schema(filename)
    # Schemas are packaged with the engine: no remote URI resolution.
    store = {
        "https://blastledger.example/schemas/assessment.schema.json": _schema("assessment.schema.json"),
        "https://blastledger.example/schemas/manifest.schema.json": _schema("manifest.schema.json"),
    }
    resolver = RefResolver.from_schema(schema, store=store)
    validator = Draft202012Validator(schema, format_checker=FormatChecker(), resolver=resolver)
    failures = sorted(validator.iter_errors(payload), key=lambda e: (tuple(str(x) for x in e.path), e.message))
    if failures:
        error = failures[0]
        path = ".".join(str(x) for x in error.path) or "$"
        raise ContractError(f"Invalid {path}: {error.message}")


def validate_assessment(payload: Any) -> None:
    _check(payload, "assessment.schema.json")
    # jsonschema format=date already checks calendar validity, but explicit date keeps
    # the engine free of assumptions about parser behavior.
    try:
        date.fromisoformat(payload["as_of"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ContractError("as_of must be an ISO calendar date") from exc
    services = {s["id"]: s for s in payload["services"]}
    if len(services) != len(payload["services"]):
        raise ContractError("Duplicate service IDs are not allowed")
    for s in services.values():
        for name in ("max_rps", "current_rps", "required_failover_rps"):
            value = s.get(name)
            if value is not None and not math.isfinite(value):
                raise ContractError(f"{s['id']}.{name}: non-finite capacity value")
        for dep in s["dependencies"]:
            if dep not in services:
                raise ContractError(f"Dangling dependency from {s['id']} to {dep}")
        if s.get("max_rps") is not None and s.get("current_rps") is not None:
            if s["current_rps"] > s["max_rps"]:
                raise ContractError(f"{s['id']}: current_rps exceeds max_rps; capacity declaration inconsistent")
    unknown = set(payload["change"]["affected_services"]) - services.keys()
    if unknown:
        raise ContractError(f"Change references unknown services: {', '.join(sorted(unknown))}")


def validate_manifest(payload: Any) -> None:
    _check(payload, "manifest.schema.json")
    service_ids = {s["id"] for s in payload["services"]}
    if len(service_ids) != len(payload["services"]):
        raise ContractError("Duplicate service IDs are not allowed")
    for sid in payload["path_rules"]:
        if sid not in service_ids:
            raise ContractError(f"Path rule refers to unknown service: {sid}")
    # Shared graph logic plus cross-field capacity checks, but with a placeholder
    # change that references an existing service.
    validate_assessment({"as_of": "2026-11-17", "services": payload["services"],
                         "change": {"id": "MANIFEST-CHECK", "type": "validation", "affected_services": [next(iter(service_ids))]}})
