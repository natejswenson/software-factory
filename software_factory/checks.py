"""Frozen check validation and bounded POSIX process execution."""

import os
import re
import selectors
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

from .errors import FactoryError
from .validation import json_integer


def validate_config(config: Any) -> dict[str, Any]:
    if not isinstance(config, dict) or type(config.get("version")) not in (int, float) or config["version"] != 1:
        raise FactoryError("Expected factory configuration version 1.")
    if config.get("endpoint") not in ("local", "draft-pr"):
        raise FactoryError("Endpoint must be local or draft-pr.")
    checks = config.get("checks")
    if not isinstance(checks, list) or not checks:
        raise FactoryError("Configure at least one executable check.")
    names = set()
    for check in checks:
        if (
            not isinstance(check, dict)
            or not isinstance(check.get("name"), str)
            or not re.fullmatch(r"[a-zA-Z0-9_-]{1,64}", check["name"])
            or check["name"] in names
        ):
            raise FactoryError("Checks need distinct simple names.")
        names.add(check["name"])
        argv = check.get("argv")
        if (
            not isinstance(argv, list)
            or not argv
            or any(not isinstance(arg, str) or "\0" in arg for arg in argv)
            or not argv[0].strip()
        ):
            raise FactoryError("Each check needs a nonempty argv array.")
        timeout = check.get("timeoutMs")
        if not json_integer(timeout) or not 100 <= timeout <= 600000:
            raise FactoryError("Check timeoutMs must be 100–600000.")
    return config


def execute_check(check: dict[str, Any], cwd: str | Path, directory: str | Path, attempt: int) -> dict[str, Any]:
    """Drain both pipes, terminate the whole group, and persist real diagnostics."""
    if sys.platform not in ("darwin", "linux"):
        raise FactoryError("Verification requires macOS/Linux process groups.")
    log = Path(directory) / f"check-{attempt}-{check['name']}.log"
    started = time.monotonic()
    result: dict[str, Any] = {
        "name": check["name"],
        "argv": check["argv"],
        "exitCode": None,
        "signal": None,
        "timedOut": False,
        "truncated": False,
        "log": str(log),
    }
    child: subprocess.Popen[bytes] | None = None
    handlers = {}
    group_killed = False
    signalling = False
    kill_requested = False

    def kill_group(sig: int) -> None:
        nonlocal group_killed, signalling, kill_requested
        if signalling:
            if sig == signal.SIGKILL:
                kill_requested = True
            return
        signalling = True
        try:
            if child is not None and not group_killed:
                try:
                    os.killpg(child.pid, sig)
                    if sig == signal.SIGKILL:
                        group_killed = True
                except ProcessLookupError:
                    group_killed = True
                except OSError as error:
                    result.setdefault("error", str(error))
                    result.setdefault("cleanupErrors", []).append(str(error))
        finally:
            signalling = False
            if kill_requested:
                kill_requested = False
                kill_group(signal.SIGKILL)

    def interrupted(signum: int, frame: Any) -> None:
        result["error"] = "Verification interrupted"
        kill_group(signal.SIGKILL)

    with open(os.open(log, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "wb") as output:
        try:
            child = subprocess.Popen(
                check["argv"],
                cwd=cwd,
                env={**os.environ, "CI": "true"},
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                start_new_session=True,
            )
            if threading.current_thread() is threading.main_thread():
                for sig in (signal.SIGINT, signal.SIGTERM):
                    handlers[sig] = signal.signal(sig, interrupted)
            deadline = started + check["timeoutMs"] / 1000
            kill_at = None
            parent_finished = False
            written = 0
            with selectors.DefaultSelector() as selector:
                for pipe in (child.stdout, child.stderr):
                    assert pipe is not None
                    os.set_blocking(pipe.fileno(), False)
                    selector.register(pipe, selectors.EVENT_READ)
                while selector.get_map() or child.poll() is None:
                    current = time.monotonic()
                    if child.poll() is not None and not parent_finished:
                        parent_finished = True
                        # A successful check must not retain inherited pipes/background writers.
                        kill_group(signal.SIGKILL)
                    if not parent_finished and current >= deadline and not result["timedOut"]:
                        result["timedOut"] = True
                        kill_group(signal.SIGTERM)
                        kill_at = current + 0.3
                    if kill_at is not None and current >= kill_at:
                        kill_group(signal.SIGKILL)
                        kill_at = None
                    for key, _ in selector.select(timeout=0.02):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            key.fileobj.close()
                            continue
                        size = min(len(chunk), max(0, 1024 * 1024 - written))
                        output.write(chunk[:size])
                        written += size
                        result["truncated"] |= size < len(chunk)
                code = child.wait()
                if code < 0:
                    result["signal"] = signal.Signals(-code).name
                else:
                    result["exitCode"] = code
        except OSError as error:
            result["error"] = str(error)
        finally:
            kill_group(signal.SIGKILL)
            if child is not None:
                child.wait()
                for pipe in (child.stdout, child.stderr):
                    if pipe is not None:
                        pipe.close()
            for sig, handler in handlers.items():
                signal.signal(sig, handler)
    result["durationMs"] = round((time.monotonic() - started) * 1000)
    result["passed"] = result["exitCode"] == 0 and not result["timedOut"] and not result.get("error")
    return result
