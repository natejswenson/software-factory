"""The factory console entry point. No agent subprocesses or model calls."""

import argparse
import json
import sys
import textwrap
from pathlib import Path
from typing import Any

from . import diagnostics, engine, history, integration, pr_description, preflight, progress, review_context
from .delivery import deliver
from .errors import FactoryError
from .git import repository
from .resources import skill_path
from .store import list_runs, read_run
from .summary import format_summary, summarize


class HelpFormatter(argparse.HelpFormatter):
    def _split_lines(self, text: str, width: int) -> list[str]:
        return textwrap.wrap(" ".join(text.split()), width, break_on_hyphens=False, break_long_words=False)


class Parser(argparse.ArgumentParser):
    def error(self, message: str) -> None:
        raise FactoryError(message)


def parser() -> Parser:
    result = Parser(
        formatter_class=HelpFormatter,
        description="Software Factory — take one task to verified delivery in your current agent session.",
        epilog="Repeat --criterion and --check. Use --task-file for longer requests. No model calls or daemon.",
    )
    result.add_argument(
        "command",
        nargs="?",
        default="help",
        help="init, prd-init, preflight, integration, start, list, runs, history, status, next, summary, explain, review-context, pr-description, progress, logs, rules, resume, plan, plan-review, verify, review, deliver, recover, extend, rename, skill-path",
    )
    for option in (
        "repo",
        "run",
        "task",
        "task-file",
        "issue",
        "base",
        "worktree-root",
        "endpoint",
        "branch",
        "file",
        "reason",
        "stage",
        "check-name",
        "phase",
        "target",
    ):
        result.add_argument(f"--{option}")
    result.add_argument("--attempts", type=int)
    result.add_argument("--limit", type=int)
    result.add_argument("--offset", type=int, default=0)
    result.add_argument("--attempt", type=int)
    result.add_argument("--tail-bytes", type=int, default=8192)
    for option in ("criterion", "check", "instructions-file", "supplement"):
        result.add_argument(f"--{option}", action="append", default=[])
    result.add_argument("--json", action="store_true")
    return result


def dispatch(args: argparse.Namespace) -> Any:
    def required(key: str) -> Any:
        value = getattr(args, key.replace("-", "_"))
        if value is None or value == "":
            raise FactoryError(f"Missing --{key}.")
        return value

    def run_path() -> str:
        return str(Path(required("run")).resolve())

    action = args.command
    if action == "skill-path":
        return str(skill_path())
    if action == "init":
        checks = [
            {"name": f"check{i + 1}", "argv": json.loads(raw), "timeoutMs": 120000} for i, raw in enumerate(args.check)
        ]
        return engine.init(required("repo"), checks)
    if action == "prd-init":
        return engine.prd_init(required("repo"))
    if action == "preflight":
        return preflight.inspect(
            required("repo"), required("worktree-root"), base=args.base, branch=args.branch, endpoint=args.endpoint
        )
    if action == "integration":
        return integration.inspect(str(Path(required("run")).absolute()), required("target"))
    if action == "start":
        if sum(value is not None for value in (args.task, args.task_file, args.issue)) != 1:
            raise FactoryError("Choose exactly one of --task, --task-file or --issue.")
        task = Path(args.task_file).read_text(encoding="utf-8") if args.task_file is not None else args.task
        return engine.start(
            engine.StartOptions(
                repo=required("repo"),
                task=task,
                issue=args.issue,
                criteria=args.criterion,
                base=args.base,
                endpoint=args.endpoint,
                worktree_root=required("worktree-root"),
                branch=args.branch,
            )
        )
    if action == "runs":
        return history.discover(required("repo"), phase=args.phase, limit=20 if args.limit is None else args.limit)
    if action == "pr-description":
        return pr_description.submit(run_path(), required("file"))
    if action == "history":
        return history.inspect(
            str(Path(required("run")).absolute()), offset=args.offset, limit=100 if args.limit is None else args.limit
        )
    if action == "list":
        return [
            {
                "id": run["id"],
                "task": run["task"].splitlines()[0],
                "phase": run["phase"],
                "endpoint": run["endpoint"],
                "run": run["dir"],
            }
            for run in list_runs(repository(required("repo")).common)
        ]
    if action in ("status", "next"):
        return engine.describe(read_run(run_path()))
    if action == "review-context":
        return review_context.collect(
            read_run(run_path()),
            stage=required("stage"),
            instructions_files=args.instructions_file,
            supplements=args.supplement,
        )
    if action == "progress":
        run = read_run(run_path())
        args.observation_blocked = run["phase"] == "blocked"
        return progress.observe(run)
    if action == "logs":
        return progress.logs(
            read_run(run_path()), check_name=required("check-name"), attempt=args.attempt, tail_bytes=args.tail_bytes
        )
    if action == "explain":
        return diagnostics.explain(read_run(run_path()))
    if action == "summary":
        return summarize(read_run(run_path()))
    if action == "rules":
        return engine.task_rules(read_run(run_path()))
    if action == "recover":
        return engine.recover(run_path()) if args.run else engine.recover_allocation(required("repo"))
    if action == "extend":
        return engine.extend(run_path(), required("attempts"), required("reason"))
    if action == "rename":
        return engine.rename_branch(run_path(), required("branch"))
    functions = {"resume": engine.resume, "verify": engine.verify, "deliver": deliver}
    if action in functions:
        return functions[action](run_path())
    submissions = {"plan": engine.submit_plan, "plan-review": engine.submit_plan_review, "review": engine.submit_review}
    if action in submissions:
        return submissions[action](run_path(), required("file"))
    raise FactoryError(f"Unknown command: {action}. Use --help.")


def format_output(action: str, result: Any) -> str:
    if action == "pr-description":
        return pr_description.format_preview(result)
    if action == "skill-path":
        return result
    if action == "integration":
        return integration.format_report(result)
    if action == "preflight":
        return preflight.format_report(result)
    if action == "prd-init":
        return "\n".join(
            [
                f"PRD folder: {result['prd']}",
                *[f"Created: {path}" for path in result["created"]],
                *[f"Skipped: {path}" for path in result["skipped"]],
                result["next"],
            ]
        )
    if action == "review-context":
        return review_context.format_bundle(result)
    if action == "progress":
        return progress.format_progress(result)
    if action == "logs":
        return progress.format_logs(result)
    if action == "explain":
        return diagnostics.format_report(result)
    if action == "runs":
        return history.format_runs(result)
    if action == "history":
        return history.format_history(result)
    if action == "summary":
        return format_summary(result)
    if action == "rules":
        if not result["enabled"]:
            return "Legacy run: repository rules were not enabled at start."
        return (
            "\n\n".join(f"# {file['path']}\n\n{file['content']}" for file in result["files"]) or "No repository rules."
        )
    if isinstance(result, list):
        return "TASK\tSTATE\tENDPOINT\tRUN\n" + "\n".join(
            f"{run['task']}\t{run['phase']}\t{run['endpoint']}\t{run['run']}" for run in result
        )
    if isinstance(result, dict) and "id" in result:
        lines = [
            result["task"].splitlines()[0],
            "",
            f"State: {result['phase']}    Next: {result['next']['action']}    Endpoint: {result['endpoint']}",
            f"Worktree: {result['worktree']}",
            f"Run: {result['run']}",
        ]
        if result["next"].get("reason"):
            lines.append(result["next"]["reason"])
        for check in (result.get("verification") or {}).get("results", []):
            lines.append(
                f"Check {check['name']}: {'passed' if check['passed'] else 'failed'}{' (timeout)' if check['timedOut'] else ''}    Log: {check['log']}"
            )
        if result.get("delivery"):
            lines.append(f"Commit: {result['delivery']['commit']}")
            if result["delivery"].get("pr"):
                lines.append(f"Draft PR: {result['delivery']['pr']}")
        return "\n".join(lines)
    return json.dumps(result, indent=2, ensure_ascii=True)


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    json_output = "--json" in argv
    try:
        options = parser()
        args = options.parse_args(argv)
        if args.command == "help":
            options.print_help()
            return 0
        result = dispatch(args)
        print(
            json.dumps(
                result,
                ensure_ascii=True,
                separators=(",", ":") if args.command == "summary" else None,
                indent=None if args.command == "summary" else 2,
            )
            if args.json
            else format_output(args.command, result)
        )
        if args.command == "integration":
            return integration.exit_code(result)
        if args.command in ("runs", "history"):
            return 2 if result["errors"] else 0
        if args.command == "progress":
            return 2 if args.observation_blocked else 0
        if args.command == "explain":
            return diagnostics.exit_code(result)
        if args.command == "preflight":
            return preflight.exit_code(result)
        if isinstance(result, dict) and (
            result.get("phase") == "blocked"
            or (args.command == "verify" and (result.get("verification") or {}).get("passed") is False)
        ):
            return 2
        return 0
    except (FactoryError, OSError, ValueError) as error:
        code = error.code if isinstance(error, FactoryError) else "invalid"
        print(json.dumps({"error": str(error), "code": code}) if json_output else f"factory: {error}", file=sys.stderr)
        return 3 if code == "infrastructure" else 2


if __name__ == "__main__":
    sys.exit(main())
