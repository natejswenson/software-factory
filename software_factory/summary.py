"""Read-only projections; freshness decisions remain in the task engine."""

from typing import Any

from .engine import describe
from .store import Run


def summarize(run: Run) -> dict[str, Any]:
    status = describe(run)
    next_step = {
        key: value
        for key, value in status["next"].items()
        if key in ("action", "reason", "endpoint", "owner", "failures", "limit", "receipt")
    }
    verification = run.get("verification")
    results = {result["name"]: result for result in verification["results"]} if verification else {}
    return {
        "id": run["id"],
        "task": run["task"],
        "phase": run["phase"],
        "endpoint": run["endpoint"],
        "criteria": run["criteria"],
        "checks": [{**check, "result": results.get(check["name"])} for check in run["config"]["checks"]],
        "verification": {key: verification[key] for key in ("passed", "unchanged", "at")} if verification else None,
        "findings": {
            "plan": (run.get("planReview") or {}).get("findings", []),
            "code": (run.get("codeReview") or {}).get("findings", []),
        },
        "next": next_step,
        "delivery": run.get("delivery"),
    }


def format_summary(summary: dict[str, Any]) -> str:
    lines = [
        f"Task: {summary['task']}",
        f"State: {summary['phase']}    Endpoint: {summary['endpoint']}",
        "",
        "Criteria:",
    ]
    lines.extend(f"  {criterion['id']}: {criterion['text']}" for criterion in summary["criteria"])
    lines.extend(["", "Checks: last verification"])
    for check in summary["checks"]:
        result = check["result"]
        if not result:
            lines.append(f"  {check['name']}: not run")
            continue
        lines.append(
            f"  {check['name']}: {'passed' if result['passed'] else 'failed'}{' (timeout)' if result['timedOut'] else ''}"
        )
        if not result["passed"]:
            error = f"    Error: {result['error']}" if result.get("error") else ""
            lines.append(f"    Exit: {result['exitCode']}    Signal: {result.get('signal') or 'none'}{error}")
        if result["truncated"]:
            lines.append("    Log truncated")
        lines.append(f"    Log: {result['log']}")
    verification = summary["verification"]
    if verification:
        lines.append(
            f"  Overall: {'passed' if verification['passed'] else 'failed'}{'' if verification['unchanged'] else ' (files changed during checks)'}"
        )
    lines.extend(["", "Findings:"])
    findings = [
        f"  {kind} {finding['severity']} {finding['location']}: {finding['issue']}"
        for kind, values in summary["findings"].items()
        for finding in values
    ]
    lines.extend(findings or ["  none"])
    next_step = summary["next"]
    reason = f" — {next_step['reason']}" if next_step.get("reason") else ""
    lines.extend(["", f"Next: {next_step['action']}{reason}"])
    if next_step.get("owner"):
        lines.append(f"  Owner: {next_step['owner']['pid']} on {next_step['owner']['host']}")
    if "limit" in next_step:
        lines.append(f"  Repair attempts: {next_step['failures']}/{next_step['limit']}")
    delivery = summary["delivery"]
    if not delivery:
        lines.append("Delivery: pending")
    else:
        lines.extend(
            [
                f"Delivery: {delivery['endpoint']} ({'completed' if summary['phase'] == 'done' else 'pending'})",
                f"  Commit: {delivery['commit']}",
            ]
        )
        if delivery["endpoint"] == "draft-pr":
            lines.append(f"  PR: {delivery.get('pr', 'pending')}")
    return "\n".join(lines)
