"""GitHub PR check adapter: trusted base code, untrusted PR manifest as JSON data.

Runs with pull_request event, no PR code execution. GitHub API is used only
for listing changed paths, reading the manifest, and updating a PR comment.
"""
from __future__ import annotations

from datetime import datetime, timezone
import base64
import fnmatch
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from .contract import ContractError, validate_manifest
from .engine import InputError, assess

MARKER = "<!-- blastledger:v1 -->"
REPO_PATTERN = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
SHA_PATTERN = re.compile(r"^[0-9a-f]{40}$")
MAX_MANIFEST_BYTES = 100_000


class IntegrationError(ValueError):
    """Safe-to-display integration failure."""


def _safe(text: Any, limit: int = 250) -> str:
    """Escape untrusted text in Markdown and keep PR comments bounded."""
    value = str(text).replace("\r", " ").replace("\n", " ")[:limit]
    return re.sub(r"([\\`*_{}\[\]()#+!|<>])", r"\\\1", value)


def _request(method: str, endpoint: str, token: str, payload: Any = None) -> Any:
    if not endpoint.startswith("/repos/"):
        raise IntegrationError("Unsupported GitHub API endpoint")
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request("https://api.github.com" + endpoint, data=body, method=method,
                  headers={"Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28",
                           "Authorization": "Bearer " + token, "User-Agent": "blastledger-pr-review/0.1",
                           "Content-Type": "application/json"})
    try:
        with urlopen(req, timeout=15) as resp:
            return json.load(resp)
    except HTTPError as exc:
        if exc.code == 404:
            raise IntegrationError("Requested GitHub resource not found; check repository permissions and manifest path") from exc
        if exc.code in (401, 403):
            raise IntegrationError(f"GitHub access denied ({exc.code}); check token permissions or fork PR restrictions") from exc
        raise IntegrationError(f"GitHub request failed ({exc.code})") from exc
    except (URLError, TimeoutError) as exc:
        raise IntegrationError("GitHub API connection unavailable") from exc


def _list_files(repo: str, pr_number: int, token: str) -> list[str]:
    paths: list[str] = []
    for page in range(1, 32):
        params = urlencode({"per_page": 100, "page": page})
        data = _request("GET", f"/repos/{repo}/pulls/{pr_number}/files?{params}", token)
        if not isinstance(data, list):
            raise IntegrationError("Unexpected PR files response")
        paths.extend(str(row["filename"]) for row in data)
        if len(data) < 100:
            return paths
    raise IntegrationError("PR file list too large to assess safely (>3,000 files)")


def _read_manifest(repo: str, sha: str, path: str, token: str) -> dict[str, Any]:
    if not REPO_PATTERN.fullmatch(repo) or not SHA_PATTERN.fullmatch(sha):
        raise IntegrationError("Invalid PR repository or revision")
    if not re.fullmatch(r"[A-Za-z0-9_.\-/]+", path) or ".." in path.split("/"):
        raise IntegrationError("Unsafe manifest path")
    data = _request("GET", f"/repos/{repo}/contents/{quote(path, safe='/')}?ref={sha}", token)
    if not isinstance(data, dict) or data.get("encoding") != "base64":
        raise IntegrationError("Manifest content is not a supported GitHub file")
    if data.get("size", MAX_MANIFEST_BYTES + 1) > MAX_MANIFEST_BYTES:
        raise IntegrationError("Manifest exceeds 100KB")
    try:
        content = base64.b64decode(data["content"], validate=False)
        if len(content) > MAX_MANIFEST_BYTES:
            raise IntegrationError("Manifest exceeds 100KB")
        parsed = json.loads(content)
        validate_manifest(parsed)
        return parsed
    except (KeyError, ValueError, UnicodeDecodeError) as exc:
        raise IntegrationError(f"Invalid manifest: {str(exc)[:300]}") from exc


def compile_assessment(manifest: dict[str, Any], changed_paths: list[str], pr_number: int,
                       head_sha: str, *, as_of: str) -> dict[str, Any]:
    """Pure function: map PR changed paths to declared services then assess."""
    validate_manifest(manifest)
    matches: set[str] = set()
    unmapped: list[str] = []
    for path in sorted(set(changed_paths)):
        ids = {sid for sid, patterns in manifest["path_rules"].items()
               if any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns)}
        if ids:
            matches.update(ids)
        else:
            unmapped.append(path)
    if not matches:
        return {"verdict": "UNKNOWN", "findings": [{"rule_id": "NO_MAPPED_SERVICES",
                 "severity": "UNKNOWN", "service_id": "", "detail": "Changed paths have no declared service mapping.",
                 "evidence": {"unmapped_count": len(unmapped)}}],
                "impacted_services": [], "assessment_id": "unmapped", "input_hash": None,
                "disclaimer": "No risk assessment was performed because service mapping is missing."}
    change_id = f"PR-{pr_number}-{head_sha[:8]}"
    payload = {"as_of": as_of, "services": manifest["services"],
               "change": {"id": change_id, "type": "pull_request", "affected_services": sorted(matches),
                          "rollback_ref": manifest.get("change_defaults", {}).get("rollback_ref")}}
    report = assess(payload)
    if unmapped:
        report["findings"].append({"rule_id": "UNMAPPED_PATHS", "severity": "UNKNOWN", "service_id": "",
                                   "detail": "Some changed files have no declared service mapping; impact may be missing.",
                                   "evidence": {"unmapped_count": len(unmapped),
                                                "examples": unmapped[:5]}})
        if report["verdict"] != "BLOCK-RECOMMENDED":
            report["verdict"] = "UNKNOWN"
    return report


def render_comment(report: dict[str, Any]) -> str:
    verdict = report["verdict"]
    lines = [MARKER, "## BlastLedger — Pre-change review", "",
             f"**Advisory verdict: `{verdict}`**", "",
             "This assessment uses declared topology and capacity data, not live measurements. "
             "A `PASS` is **not** a deployment safety guarantee.", "",
             f"**Impacted:** {', '.join(_safe(s) for s in report.get('impacted_services', [])[:15]) or 'Unknown'}", "",
             "| Rule | Severity | Explanation |", "| --- | --- | --- |"]
    for finding in report.get("findings", [])[:12]:
        lines.append(f"| {_safe(finding['rule_id'])} | {_safe(finding['severity'])} | {_safe(finding['detail'])} |")
    if len(report.get("findings", [])) > 12:
        lines.append(f"| Other | — | {len(report['findings']) - 12} more findings omitted; see check logs |")
    lines.append("")
    lines.append("<details><summary>Evidence (selected findings)</summary>\n")
    lines.append("```json")
    # Json evidence is bounded; prevent code fence injection in user data.
    evidence = [{"rule_id": x["rule_id"], "service_id": x["service_id"],
                 "evidence": x["evidence"]} for x in report.get("findings", [])[:8]]
    lines.append(json.dumps(evidence, indent=2, ensure_ascii=True).replace("```", "` ` `")[:6000])
    lines.append("```\n</details>\n")
    lines.append("**Next step:** Human reviewer decides. This tool never changes infrastructure.")
    return "\n".join(lines)


def _upsert_comment(repo: str, pr_number: int, token: str, body: str) -> None:
    # Look for a prior bot comment to avoid spamming a PR on repeated pushes.
    previous_id = None
    for page in range(1, 6):
        data = _request("GET", f"/repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}", token)
        for comment in data:
            author = comment.get("user", {})
            if MARKER in comment.get("body", "") and author.get("type") == "Bot":
                previous_id = comment["id"]
                break
        if previous_id or len(data) < 100:
            break
    endpoint = (f"/repos/{repo}/issues/comments/{previous_id}" if previous_id else
                f"/repos/{repo}/issues/{pr_number}/comments")
    _request("PATCH" if previous_id else "POST", endpoint, token, {"body": body})


def main() -> int:
    try:
        token = os.environ["GITHUB_TOKEN"]
        repo = os.environ["GITHUB_REPOSITORY"]
        if not REPO_PATTERN.fullmatch(repo):
            raise IntegrationError("Invalid GitHub repository")
        event = json.loads(Path(os.environ["GITHUB_EVENT_PATH"]).read_text(encoding="utf-8"))
        pr = event["pull_request"]
        number = int(pr["number"])
        head_repo = pr["head"]["repo"]["full_name"]
        head_sha = pr["head"]["sha"]
        if not REPO_PATTERN.fullmatch(head_repo) or not SHA_PATTERN.fullmatch(head_sha):
            raise IntegrationError("Invalid PR source")
        paths = _list_files(repo, number, token)
        manifest = _read_manifest(head_repo, head_sha,
                                  os.environ.get("BLASTLEDGER_MANIFEST_PATH", "blastledger.json"), token)
        report = compile_assessment(manifest, paths, number, head_sha,
                                    as_of=datetime.now(timezone.utc).date().isoformat())
    except (OSError, ValueError, KeyError, TypeError, IntegrationError, InputError, ContractError) as exc:
        report = {"verdict": "UNKNOWN", "impacted_services": [],
                  "findings": [{"rule_id": "INTEGRATION_UNKNOWN", "severity": "UNKNOWN", "service_id": "",
                                "detail": f"Assessment unavailable: {str(exc)[:200]}", "evidence": {}}]}
        # Fail-open as an advisory check for integration failures, never claim PASS.
        repo = os.environ.get("GITHUB_REPOSITORY", "")
        token = os.environ.get("GITHUB_TOKEN", "")
        number = event.get("pull_request", {}).get("number", 0) if "event" in locals() else 0
    print(json.dumps(report, indent=2))
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as f:
            f.write("verdict=" + report["verdict"] + "\n")
    if REPO_PATTERN.fullmatch(repo) and token and number:
        try:
            _upsert_comment(repo, int(number), token, render_comment(report))
        except IntegrationError as exc:
            print(f"Comment not posted: {exc} (fork token permissions may be restricted)", file=sys.stderr)
    blocking = os.environ.get("BLASTLEDGER_BLOCK_ON_HIGH_RISK", "false").lower() == "true"
    if blocking and report["verdict"] == "BLOCK-RECOMMENDED":
        print("Opt-in blocking: confirmed high-risk findings", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
