# BlastLedger v0.2 — Acceptance checklist (schema → API → GitHub PR)

## Reproducibility

- [ ] Check the PR diff: only `projects/blastledger/**` plus `.github/workflows/blastledger*.yml` are changed; no website, Lookout, or other code altered.
- [ ] Install dependencies and run `python -m pytest -q`. Verify the exact passing count in your own environment and capture output.
- [ ] Run the three original fixture scenarios and verify `BLOCK-RECOMMENDED`, `PASS`, `UNKNOWN`.
- [ ] Change `current_rps` above `max_rps`: expect a schema/semantic rejection, **not** a silent PASS.
- [ ] Add an unknown JSON key, invalid date, dangling dependency, or duplicate service: reject with an actionable error.
- [ ] Add A→B→A cycle: assessment must terminate with correct downstream callers.
- [ ] Remove current metrics or set stale date: expect UNKNOWN.
- [ ] Repeat the same input twice: output and hash must be identical.

## HTTP contract

- [ ] Start `uvicorn blastledger.api:app --host 127.0.0.1 --port 8000`.
- [ ] `POST /assess` using `fixtures/danger.json` returns 200 with `input_hash` and evidence-linked `LOW_FAILOVER_HEADROOM` finding.
- [ ] Send malformed JSON: 400. Invalid schema: 422. More than 1 MiB: 413.
- [ ] Open `/openapi.json` and `/docs`; verify the documented endpoint matches actual requests.
- [ ] Verify API contains **no** persistent store, auth, tenancy, hosting, or ability to deploy/rollback. Keep it private.

## GitHub Action check (after workflow is available on base branch)

- [ ] Make a disposable PR changing a mapped file (`app/page.tsx`), without touching production configuration. Confirm an `UNKNOWN` assessment when no measured capacity is supplied.
- [ ] Make a disposable PR changing an unmapped file. Confirm UNKNOWN, not a false green PASS.
- [ ] Ensure PR comment includes evidence, rule IDs, dependencies, and a human review disclaimer.
- [ ] Re-run the action and confirm it edits its bot comment rather than creating an unbounded stream of new comments.
- [ ] Confirm fork PRs do not execute PR code with a write-capable token; comment permission errors are visible in logs.
- [ ] Default result is advisory. Only after human verification, flip the repo Actions variable `BLASTLEDGER_BLOCK_ON_HIGH_RISK=true`; prove one BLOCK finding fails the check and UNKNOWN does not.

## Commercial reality check

- [ ] Interview five engineering leads at teams with ~5–40 developers.
- [ ] For each, record the last customer-visible change incident and which artifacts were missing before approval.
- [ ] Ask whether this PR comment would alter a real decision, who pays, and maintenance burden.
- [ ] Continue integration development only if evidence supports adoption. If 3+ would ignore it, reconsider how topology data enters the system.

**Sign-off:** Built [ ] Verified [ ] Visible [ ] Explained [ ]. Approver: ___________ Date: ______. This is prototype validation, not production safety certification.
