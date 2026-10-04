"""Real process groups: timeout, successful orphans, interrupts and bounded logs."""

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from unittest.mock import patch

from software_factory import checks
from software_factory.checks import execute_check
from tests.support import ROOT, FactoryCase


class ProcessTests(FactoryCase):
    def test_cleanup_permission_diagnostics_preserve_primary_interrupt(self):
        f = self.fixture()
        original_signal, original_kill = signal.signal, os.killpg
        handlers = {sig: signal.getsignal(sig) for sig in (signal.SIGINT, signal.SIGTERM)}
        denied = False

        def kill_once(pid, sig):
            nonlocal denied
            if not denied:
                denied = True
                raise PermissionError("synthetic cleanup denial")
            return original_kill(pid, sig)

        def install(sig, handler):
            previous = original_signal(sig, handler)
            if sig == signal.SIGTERM and getattr(handler, "__name__", "") == "interrupted":
                handler(sig, None)
            return previous

        with (
            patch.object(checks.os, "killpg", side_effect=kill_once),
            patch.object(checks.signal, "signal", side_effect=install),
        ):
            result = execute_check(
                {"name": "interrupt-denial", "argv": [sys.executable, "-c", "pass"], "timeoutMs": 2000},
                f.root,
                f.root,
                1,
            )
        self.assertFalse(result["passed"])
        self.assertEqual(result["error"], "Verification interrupted")
        self.assertEqual(result["cleanupErrors"], ["synthetic cleanup denial"])
        self.assertEqual({sig: signal.getsignal(sig) for sig in handlers}, handlers)

    def test_cleanup_only_permission_failure_still_fails_check(self):
        f = self.fixture()
        with patch.object(checks.os, "killpg", side_effect=PermissionError("synthetic cleanup denial")):
            result = execute_check(
                {"name": "cleanup-denial", "argv": [sys.executable, "-c", "pass"], "timeoutMs": 2000}, f.root, f.root, 1
            )
        self.assertEqual(result["exitCode"], 0)
        self.assertFalse(result["passed"])
        self.assertEqual(result["error"], "synthetic cleanup denial")
        self.assertTrue(result["cleanupErrors"])

    def parent(self, root, *, exit_early=False, inherited_pipes=False):
        target = root / "orphan.txt"
        script = root / "parent.py"
        child = f"import time; from pathlib import Path; time.sleep(1); Path({str(target)!r}).write_text('orphan')"
        script.write_text(
            "import subprocess, sys, time\n"
            + f"subprocess.Popen([sys.executable, '-c', {child!r}], stdout={'None' if inherited_pipes else 'subprocess.DEVNULL'}, stderr=subprocess.DEVNULL)\n"
            + ("" if exit_early else "time.sleep(30)\n")
        )
        return script, target

    def test_timeout_kills_descendant_and_bounds_logs(self):
        f = self.fixture()
        script, target = self.parent(f.root)
        result = execute_check(
            {"name": "timeout", "argv": [sys.executable, str(script)], "timeoutMs": 150}, f.root, f.root, 1
        )
        self.assertFalse(result["passed"])
        self.assertTrue(result["timedOut"])
        time.sleep(1.1)
        self.assertFalse(target.exists())
        noisy = execute_check(
            {
                "name": "noisy",
                "argv": [sys.executable, "-c", "import sys; sys.stdout.write('x' * (2*1024*1024))"],
                "timeoutMs": 2000,
            },
            f.root,
            f.root,
            2,
        )
        self.assertTrue(noisy["passed"])
        self.assertTrue(noisy["truncated"])
        self.assertEqual(Path(noisy["log"]).stat().st_size, 1024 * 1024)

    def test_literal_argv_and_missing_executable(self):
        f = self.fixture()
        arg = "spaces; `echo bad` $(echo bad)"
        result = execute_check(
            {
                "name": "literal",
                "argv": [sys.executable, "-c", "import sys; print(sys.argv[1])", arg],
                "timeoutMs": 2000,
            },
            f.root,
            f.root,
            1,
        )
        self.assertEqual(Path(result["log"]).read_text().strip(), arg)
        missing = execute_check(
            {"name": "missing", "argv": ["/not/a/real/program"], "timeoutMs": 1000}, f.root, f.root, 2
        )
        self.assertFalse(missing["passed"])
        self.assertIn("No such file", missing["error"])

    def test_successful_parent_kills_background_writer_and_inherited_pipes(self):
        for inherited in (False, True):
            with self.subTest(inherited=inherited):
                f = self.fixture()
                script, target = self.parent(f.root, exit_early=True, inherited_pipes=inherited)
                result = execute_check(
                    {"name": "early", "argv": [sys.executable, str(script)], "timeoutMs": 2000}, f.root, f.root, 1
                )
                self.assertTrue(result["passed"], result)
                self.assertLess(result["durationMs"], 1000)
                time.sleep(1.1)
                self.assertFalse(target.exists())

    def test_interrupt_kills_group_and_restores_handlers(self):
        f = self.fixture()
        script, target = self.parent(f.root)
        ready = f.root / "ready"
        receipt = f.root / "interrupt.json"
        check = {"name": "interrupt", "argv": [sys.executable, str(script)], "timeoutMs": 10000}
        driver = (
            "import json, signal; from pathlib import Path; from software_factory.checks import execute_check; "
            "handler=lambda *args: None; signal.signal(signal.SIGTERM, handler); "
            f"Path({str(ready)!r}).write_text('ready'); "
            f"result=execute_check({check!r}, {str(f.root)!r}, {str(f.root)!r}, 1); "
            "result['restored']=signal.getsignal(signal.SIGTERM) is handler; "
            f"Path({str(receipt)!r}).write_text(json.dumps(result))"
        )
        child = subprocess.Popen([sys.executable, "-c", driver], cwd=ROOT)
        try:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.02)
            self.assertTrue(ready.exists())
            time.sleep(0.15)
            child.send_signal(signal.SIGTERM)
            self.assertEqual(child.wait(timeout=3), 0)
            result = json.loads(receipt.read_text())
            self.assertFalse(result["passed"])
            self.assertEqual(result["error"], "Verification interrupted")
            self.assertTrue(result["restored"])
            time.sleep(1.1)
            self.assertFalse(target.exists())
        finally:
            if child.poll() is None:
                child.kill()
                child.wait()

    def test_command_output_limit_is_enforced_while_draining(self):
        from software_factory.errors import FactoryError
        from software_factory.git import command

        f = self.fixture()
        for destination in ("stdout", "stderr"):
            with self.subTest(destination=destination), self.assertRaisesRegex(FactoryError, "exceeds 8 MiB"):
                command([sys.executable, "-c", f"import sys; sys.{destination}.write('x' * (9*1024*1024))"], f.root)
