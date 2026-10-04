"""Literal subprocess commands, repository ownership and isolated Git snapshots."""

import os
import selectors
import signal
import subprocess
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from .errors import FactoryError
from .store import Run


def _kill_command_group(pid: int) -> None:
    """Allow a short macOS group teardown race; preserve persistent failures."""
    delays = iter((0.01, 0.02, 0.04))
    while True:
        try:
            os.killpg(pid, signal.SIGKILL)
            return
        except ProcessLookupError:
            return
        except PermissionError:
            delay = next(delays, None)
            if delay is None:
                raise
            time.sleep(delay)


def command(
    argv: Sequence[str], cwd: str | Path, *, env: Mapping[str, str] | None = None, binary: bool = False
) -> str | bytes:
    try:
        child = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            start_new_session=True,
        )
        buffers = {"stdout": bytearray(), "stderr": bytearray()}
        deadline = time.monotonic() + 30
        primary_error: BaseException | None = None
        try:
            with selectors.DefaultSelector() as selector:
                for name in buffers:
                    pipe = getattr(child, name)
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ, name)
                while selector.get_map() or child.poll() is None:
                    if time.monotonic() >= deadline:
                        raise FactoryError(f"{' '.join(argv[:2])}: timed out after 30 seconds.", "infrastructure")
                    for key, _ in selector.select(timeout=0.02):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        buffer = buffers[key.data]
                        if len(buffer) + len(chunk) > 8 * 1024 * 1024:
                            raise FactoryError(f"{' '.join(argv[:2])}: output exceeds 8 MiB.", "infrastructure")
                        buffer.extend(chunk)
                code = child.wait()
                if code:
                    detail = (
                        bytes(buffers["stderr"]).decode("utf-8", "replace").strip() or f"Exited with status {code}."
                    )
                    raise FactoryError(f"{' '.join(argv[:2])}: {detail}", "infrastructure")
                output = bytes(buffers["stdout"])
                return output if binary else output.decode("utf-8", "surrogateescape")
        except BaseException as error:
            primary_error = error
            raise
        finally:
            cleanup_errors: list[str] = []
            try:
                _kill_command_group(child.pid)
            except OSError as cleanup_error:
                cleanup_errors.append(str(cleanup_error))
                if child.poll() is None:
                    try:
                        child.kill()
                    except OSError as child_error:
                        cleanup_errors.append(f"child termination failed: {child_error}")
            finally:
                try:
                    child.wait(timeout=1)
                except (OSError, subprocess.SubprocessError) as wait_error:
                    cleanup_errors.append(f"child wait failed: {wait_error}")
                finally:
                    for pipe in (child.stdout, child.stderr):
                        if pipe is not None:
                            try:
                                pipe.close()
                            except OSError as close_error:
                                cleanup_errors.append(f"pipe close failed: {close_error}")
            if cleanup_errors:
                detail = "; ".join(cleanup_errors)
                if primary_error is not None:
                    detail = f"{primary_error}; process-group cleanup failed: {detail}"
                raise FactoryError(f"{' '.join(argv[:2])}: {detail}", "infrastructure")
    except (OSError, subprocess.SubprocessError) as error:
        detail = getattr(error, "stderr", None)
        message = detail.decode("utf-8", "replace").strip() if isinstance(detail, bytes) else str(error)
        raise FactoryError(f"{' '.join(argv[:2])}: {message}", "infrastructure") from error


def git(cwd: str | Path, args: Sequence[str], *, env: Mapping[str, str] | None = None) -> str:
    return str(command(["git", "--literal-pathspecs", *args], cwd, env=env))


def git_bytes(cwd: str | Path, args: Sequence[str]) -> bytes:
    result = command(["git", "--literal-pathspecs", *args], cwd, binary=True)
    assert isinstance(result, bytes)
    return result


@dataclass(frozen=True)
class Repository:
    root: str
    common: str


def repository(path: str | Path) -> Repository:
    root = Path(git(Path(path).resolve(), ["rev-parse", "--show-toplevel"]).strip()).resolve()
    common = (root / git(root, ["rev-parse", "--git-common-dir"]).strip()).resolve()
    return Repository(str(root), str(common))


def assert_supported(repo: str | Path) -> None:
    if git(repo, ["ls-files", "--unmerged"]).strip():
        raise FactoryError("Resolve index conflicts first.")
    if any(line.startswith("160000 ") for line in git(repo, ["ls-files", "--stage"]).splitlines()):
        raise FactoryError("Submodules are not supported in this version.")


def snapshot(repo: str | Path, base: str) -> dict[str, Any]:
    assert_supported(repo)
    with TemporaryDirectory(prefix="factory-index-") as temporary:
        env = {**os.environ, "GIT_INDEX_FILE": str(Path(temporary) / "index")}
        head = git(repo, ["rev-parse", "HEAD"]).strip()
        git(repo, ["read-tree", head], env=env)
        git(repo, ["add", "-A", "--", "."], env=env)
        tree = git(repo, ["write-tree"], env=env).strip()
        paths = [
            path for path in git(repo, ["diff", "--no-renames", "--name-only", "-z", base, tree]).split("\0") if path
        ]
        return {"head": head, "tree": tree, "paths": paths}


def assert_worktree(run: Run) -> None:
    try:
        info = repository(run["worktree"])
    except FactoryError as error:
        raise FactoryError("Task worktree is missing. Restore it before resuming.", "ownership") from error
    if (
        info.root != run["worktree"]
        or info.common != run["common"]
        or git(info.root, ["branch", "--show-current"]).strip() != run["branch"]
    ):
        raise FactoryError("Task worktree ownership changed; refusing to adopt it.", "ownership")
    try:
        git(info.root, ["merge-base", "--is-ancestor", run["base"], "HEAD"])
    except FactoryError as error:
        raise FactoryError("Task HEAD no longer descends from its frozen base.", "ownership") from error
