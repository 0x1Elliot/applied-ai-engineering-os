# BlastLedger — read-only pre-change review v0.2

A **prototype** for small software teams: a strict input contract, deterministic dependency/capacity findings, an optional FastAPI adapter, and a GitHub pull request comment integration. No outage-prevention promises. PR verdicts are **advisory** by default.

**Product PRD:** [Pursuit net-new-build format](https://docs.google.com/document/d/10AkZ_TSvP4BVHumdjJ6p7VI4Dqkh761tzXmaY5DBGnE/edit?usp=drivesdk).  **Validation:** [v0.2 validation gates](BUILD_V0_2.md).

## Install / test

From `projects/blastledger` (Python 3.10+):

```bash
python -m pip install -e '.[dev]'
python -m pytest -q
python -m blastledger assess fixtures/danger.json
python -m blastledger assess fixtures/healthy.json
python -m blastledger assess fixtures/unknown.json
```

The three fixtures should produce `BLOCK-RECOMMENDED`, `PASS`, `UNKNOWN`, respectively. A PASS **does not certify** that any real release is safe. All capacity numbers in the sample fixtures are synthetic declarations, not observed telemetry.

## HTTP adapter (development only)

```bash
python -m uvicorn blastledger.api:app --host 127.0.0.1 --port 8000
curl -s -X POST http://127.0.0.1:8000/assess -H 'Content-Type: application/json' --data-binary @fixtures/danger.json
```

- `POST /assess`: JSON request matching [`assessment.schema.json`](blastledger/schemas/assessment.schema.json); output includes `verdict`, `findings`/evidence, `assessment_id`, `input_hash`, ruleset version.
- `GET /openapi.json`: generated OpenAPI document; `GET /docs`: development API explorer.
- Invalid schema/semantic content returns HTTP 422; malformed JSON 400; body above 1 MiB 413.
- No DB, authentication, durable audits, tenancy, or rate limiting. **Never expose this endpoint publicly or put it in production as-is.**

## GitHub PR advisory integration (v0.2)

[`.github/workflows/blastledger.yml`](../../.github/workflows/blastledger.yml) uses the `pull_request` event and checks out **trusted base-branch code**. It never executes code from the PR head. It reads the proposed JSON service manifest via the GitHub Contents API **as data only**, fetches changed-file paths, maps those paths to service IDs, then invokes the deterministic library in-process (no hosted service or paid API required).

1. Copy [the sample manifest](examples/blastledger.json) into your repository and adapt the `services` inventory and `path_rules` to your actual paths. The repository workflow currently points to `projects/blastledger/examples/blastledger.json`; adjust `BLASTLEDGER_MANIFEST_PATH` for other repositories.
2. Put only service-level metadata in the manifest. Declare `dependencies`, `criticality`, `replicas`, optional RPS data and capacity evidence timestamps. Missing data yields `UNKNOWN`. If changing the manifest in a PR, that proposed manifest is treated as untrusted self-reported input (not independently verified).
3. After merging the workflow, open a test PR and inspect its action logs and the bot comment. A PR whose paths aren't mapped is **UNKNOWN**, not PASS.
4. The check is **advisory by default** and exits successfully regardless of verdict. To opt in to fail *only for a confirmed `BLOCK-RECOMMENDED`*, set repository Actions variable `BLASTLEDGER_BLOCK_ON_HIGH_RISK` to `true`. Do this only after you have validated the mapping and rules. UNKNOWN stays advisory; separately decide whether your team wants a policy that gates missing evidence.
5. The GitHub token requests read repository + write PR scope only. **Fork PRs may not have permission to write comments**, so check the log; the assessment remains visible in Actions output. Repeated comments by the bot are updated in place where permissions permit.

This is deliberately **not** a production-grade security gate: manifest rules are editable in a PR, data is unverified, and GitHub's workflow security depends on repository policy. Review branch protection and allowlisting before enabling mandatory checks. Do not run unreviewed code with a write-capable token.

## Code contracts and boundaries

- `blastledger/engine.py`: no network, no I/O, no mutation, stable output for identical input.
- `blastledger/contract.py`: strict JSON Schema Draft 2020-12, with semantic graph/capacity checks. Extra fields, invalid types, dangling refs and contradictory `current_rps > max_rps` are rejected.
- `blastledger/action.py`: manifest-to-affected-service mapping, PR comment rendering and GitHub REST adapter.
- `blastledger/api.py`: **zero persistence**, small HTTP wrapper around the same `assess` library.
- No LLM, chaos tests, live telemetry, autonomous rollback, or cloud control-plane integrations.

## Customer validation before extending the product

Interview five engineering leads. Ask whether their *last painful change* would have benefited from this PR comment, how long their current evidence gathering takes, who approves risky releases, and whether maintaining a `services/path_rules` manifest is practical. If 3+ out of 5 would ignore the comment or reject manual data entry, investigate low-friction topology acquisition before building a SaaS dashboard or persistence layer.
