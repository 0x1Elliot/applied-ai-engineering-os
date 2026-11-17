# BlastLedger v0.1 — Founder Validation Checklist

Owner: founder / engineering reviewer
Version: v0.1 (deterministic engine)
Status: **Unmerged, not production-ready**
Evidence collected: local Python test run on 2026-11-17 — **14/14 tests passed**. This is not a statement about GitHub Actions or production.

## Gate 1 — Provenance and branch safety

- [ ] Confirm you are reviewing the feature branch, NOT main. Verify the diff contains only projects/blastledger/ files.
- [ ] Compare the branch against main. Check no existing app source, deployment configuration, credentials, or history were modified.
- [ ] Open and read the [Pursuit PRD](https://docs.google.com/document/d/10AkZ_TSvP4BVHumdjJ6p7VI4Dqkh761tzXmaY5DBGnE/edit?usp=drivesdk). Verify the first product goal, P0 scope, explicit exclusions, and prospective buyer.
- [ ] Confirm no claims imply these three recent outages had the same root cause or that BlastLedger could have prevented them.

## Gate 2 — Reproduce the executable demo locally

1. Download or clone the branch and move into projects/blastledger.
2. Verify Python is 3.10 or newer:

       python --version

3. Run all unit tests:

       python -m unittest discover -s tests -v

   Acceptance: 14 tests run, all PASS, with exit code 0.
4. Execute the three fixtures:

       python -m blastledger assess fixtures/danger.json
       python -m blastledger assess fixtures/healthy.json
       python -m blastledger assess fixtures/unknown.json

   Acceptance: verdicts exactly BLOCK-RECOMMENDED, PASS, UNKNOWN respectively.
5. Read the danger fixture as if you were the on-call engineer. Confirm headroom calculation: 1000 - 880 = 120 RPS and required failover = 250 RPS. Inspect critical downstream service checkout-api and orders-api.
6. Confirm findings include rule IDs and exact evidence fields, not only an LLM-written explanation. Explain why changed gateway-proxy affects callers shown in impacted_services.

## Gate 3 — Negative and trust-path tests

- [ ] Change healthy.json so current_rps=900 (keeping max_rps=1000, required_failover_rps=300), then run on a COPY of the fixture; it should become BLOCK-RECOMMENDED.
- [ ] Remove capacity_observed_at from a COPY of healthy.json. Expected UNKNOWN.
- [ ] Make a critical changed service's replicas=1. Expected BLOCK-RECOMMENDED, even if capacity is unknown.
- [ ] Remove rollback_ref (or make it empty) from healthy fixture. Expected REVIEW; note missing rollback is currently an advisory warning, not an automatic blocker.
- [ ] Introduce a dangling dependency. Expected a controlled input error, not a silent PASS.
- [ ] Create A → B → A in a fixture. Expected termination and complete impacted service list, not a hang.
- [ ] Run identical fixture twice, compare results, and explain how the input hash produces an assessment_id.
- [ ] Inspect malformed input behavior. Document any raw exception or unexpected PASS as a **defect**. Do not approve based only on the current 14 tests.

## Gate 4 — Security and correctness limitations (must be acknowledged)

- [ ] Confirm the app reads files only; no real provider APIs, credential handling, or production writes are present.
- [ ] Inspect the rule ordering: BLOCK outranks UNKNOWN, UNKNOWN outranks REVIEW, REVIEW outranks PASS. Consider where this policy could mislead a reviewer.
- [ ] Identify limits of declared RPS headroom (burst traffic, latency, queueing, autoscaling, resource sharing, failure modes) and what measured data would be needed.
- [ ] Verify this engine has **no** authentication, tenant isolation, PostgreSQL audit log, actual CI enforcement, webhook signature verification, dashboard, or hosted URL. Do not claim those exist.
- [ ] List at least three false-negative risks from incomplete dependency data; write tests before trusting additional scenarios.
- [ ] Do not use a PASS to authorize any live or safety-critical deployment.

## Gate 5 — Pull-request acceptance and business validation

- [ ] Review the GitHub PR file list and source diff line by line. Approve only after local test output is recorded.
- [ ] Attach a screenshot or pasted command results as proof of Build + Verify.
- [ ] Walk through a 60-second CLI demo: change submitted → reverse dependency graph → capacity rule → evidence-linked finding → human decision.
- [ ] Teach back why UNKNOWN differs from PASS, and why missing telemetry must not be treated as safe.
- [ ] Conduct at least five early interviews with engineering leads. Ask about a real production change, consequence, process today, how much time is spent gathering evidence, and purchasing ownership.
- [ ] Log objections and alternatives (Datadog, Harness, Gremlin, existing checklists). Don't write production integrations before understanding whether a buyer would adopt this workflow.
- [ ] Keep the branch unmerged until acceptance criteria are met. Establish a dedicated repository when ready and migrate this subtree independently.

## Explicit known gaps / next release blockers

- The Python code validates a constrained JSON input, but is not yet a complete versioned schema or hardened adversarial input parser.
- No tests yet cover tenant isolation, CI, auth, DB consistency, production observability integration, or sustained load.
- The current 14 passing tests prove only their respective unit conditions; they do not establish production readiness, market demand, or a statistically valid outage-prevention rate.

## Acceptance signoff

Built [ ]  Verified [ ]  Visible (CLI and captured output) [ ]  Explained [ ]

Reviewer: ____________________
Date: ________________________
PR reviewed: __________________
Open defects: ________________
Next action: _________________
