"""Merge eligible current-head PRs after CI, then dispatch their exact release.

Runs only from trusted main in a workflow_run job. Never checks out PR code or
downloads PR artifacts; API responses are data and subprocesses use literal argv.
"""

import argparse
import json
import os

from scripts.github_api import api, command, repository, sha


def eligible(pr: dict, run: dict, repo: str, permission: str) -> bool:
    return bool(
        run.get("event") == "pull_request"
        and run.get("conclusion") == "success"
        and run.get("path", "").split("@")[0] == ".github/workflows/ci.yml"
        and run.get("repository", {}).get("full_name") == repo
        and pr.get("head", {}).get("repo", {}).get("full_name") == repo
        and pr.get("base", {}).get("repo", {}).get("full_name") == repo
        and pr.get("base", {}).get("ref") == "main"
        and pr.get("head", {}).get("sha") == run.get("head_sha")
        and not pr.get("draft")
        and permission in ("admin", "maintain", "write")
        and (pr.get("state") == "open" or pr.get("merged") is True)
    )


def merge_run(repo: str, run_id: int) -> list[dict]:
    repository(repo)
    if isinstance(run_id, bool) or run_id <= 0:
        raise ValueError("A positive CI run id is required.")
    run = api(f"repos/{repo}/actions/runs/{run_id}")
    if run.get("event") != "pull_request" or run.get("conclusion") != "success":
        return []
    head = sha(run["head_sha"])
    candidates = api(f"repos/{repo}/commits/{head}/pulls?per_page=100")
    results = []
    for candidate in candidates:
        number = candidate["number"]
        if isinstance(number, bool) or not isinstance(number, int) or number <= 0:
            raise ValueError("Invalid PR number.")
        pr = api(f"repos/{repo}/pulls/{number}")
        login = pr["user"]["login"]
        if not isinstance(login, str) or not login.replace("-", "").isalnum():
            continue
        permission = api(f"repos/{repo}/collaborators/{login}/permission")["permission"]
        if not eligible(pr, run, repo, permission):
            continue
        if not pr.get("merged"):
            command("gh", "pr", "merge", str(number), "--repo", repo, "--squash", "--match-head-commit", head)
            pr = api(f"repos/{repo}/pulls/{number}")
        if not pr.get("merged") or pr["head"]["sha"] != head:
            raise RuntimeError("Protected merge was not observed at the tested PR head.")
        commit = sha(pr["merge_commit_sha"])
        # Dispatch is deliberately resumable even when the preceding merge
        # succeeded but dispatch failed. Release reconciles this commit's tag.
        api(
            f"repos/{repo}/actions/workflows/release.yml/dispatches",
            method="POST",
            data={"ref": "main", "inputs": {"commit": commit}},
        )
        results.append({"pr": number, "commit": commit, "releaseDispatched": True})
    return results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-id", required=True, type=int)
    args = parser.parse_args()
    print(json.dumps(merge_run(os.environ["GITHUB_REPOSITORY"], args.run_id), indent=2))


if __name__ == "__main__":
    main()
