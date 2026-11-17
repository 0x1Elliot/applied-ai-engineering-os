# BlastLedger — Backend v0.1

BlastLedger is a proposed **pre-change infrastructure risk-review platform**. This first deliverable is a deterministic, **read-only Python engine** that evaluates a change against declared service dependencies and capacity data.

**Status:** research + prototype. No production customer, paid service, live telemetry, API server, authentication, PostgreSQL, or CI gate exists. Verdicts are advisory; a PASS is **never** a deployment safety guarantee.

## Product source of truth

[Pursuit-format Product Requirements Document](https://docs.google.com/document/d/10AkZ_TSvP4BVHumdjJ6p7VI4Dqkh761tzXmaY5DBGnE/edit?usp=drivesdk)

[Validation checklist](VALIDATION.md) — run this before approving or migrating the code.

## Run locally

From this folder, using Python 3.10+ (no paid API key or external dependency):

    python -m blastledger assess fixtures/danger.json
    python -m blastledger assess fixtures/healthy.json
    python -m blastledger assess fixtures/unknown.json
    python -m unittest discover -s tests -v

Expected results:

| Fixture | Verdict | What it checks |
| --- | --- | --- |
| danger.json | BLOCK-RECOMMENDED | 120 RPS spare vs 250 RPS required, plus critical downstream services and missing rollback reference |
| healthy.json | PASS | Fixture-specific checks satisfied, **not** an actual safety guarantee |
| unknown.json | UNKNOWN | Missing capacity metrics cannot be treated as safe |

Input is local JSON containing a change record and service graph. A service's dependencies point to the services **it calls**. The engine reverses those edges to find all callers of a changed component, directly or transitively.

The change assessment is deterministic for identical inputs, including a repeatable input-based assessment ID.

## Safety / scope limits

- Synthetic, user-declared capacity data. No real APM, telemetry, chaos testing, or control-plane instrumentation.
- No network calls, production credentials, deploy/rollback operations, or LLM in the implementation.
- No multi-tenant isolation, secret management, persistent audit store, rate limiting, or webhook authentication.
- Simplified failover arithmetic is **not** a production capacity model.
- No guaranteed detection of every risk. Unknown and missing topology may hide hazards.
- Do not require this assessment as a live deployment safety gate yet.

## Next engineering slice

Define a strict schema and OpenAPI endpoint with FastAPI, then add PostgreSQL-backed scoped organizations, snapshots, provenance and append-only review decisions. Run adversarial integration tests before connecting to any customer metadata.

**Repository placement:** staged under an isolated feature branch of applied-ai-engineering-os while a dedicated BlastLedger repository is not yet available. This is not the final product repository.
