"""Real evidence, literal presentation, immutable recovery and old delivery parity."""

import json
import os
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

from software_factory import delivery, engine
from software_factory import pr_description as presentation
from software_factory.errors import FactoryError
from software_factory.git import git
from software_factory.store import atomic_json, read_run
from tests.support import FactoryCase


class PresentationTests(FactoryCase):
    def input(self, run, **overrides):
        data = {
            "version": 1,
            "evidence": run["next"]["evidence"],
            "title": "  Add concise PR descriptions  ",
            "summary": ["Accept verified agent prose and preserve delivery gates."],
            **overrides,
        }
        return self.json_file(run["run"], "description-input.json", data)

    def submit(self, run, **overrides):
        return presentation.submit(run["run"], self.input(run, **overrides))

    def private_bytes(self, run):
        root = Path(run["run"])
        return {p.name: p.read_bytes() for p in root.iterdir() if p.is_file()}

    def test_preview_exact_criteria_actual_checks_and_no_full_request(self):
        f = self.fixture()
        f = replace(
            f,
            options=replace(
                f.options,
                task="# Full synthetic PRD\n\nPrivate requirement detail must not be copied.",
                criteria=[
                    "First **criterion**\nwith continuation and `literal` $().",
                    "Second criterion: Unicode café 雪.",
                ],
            ),
        )
        run = self.checked(f)
        before = read_run(run["run"])
        proof = self.private_bytes(run)
        data = self.submit(
            run,
            title="  Markdown `title` 雪 $()  ",
            summary=["Literal **Markdown**, `code`, café 雪 and $(echo untouched).", "Second paragraph."],
            compatibility="Existing saved runs retain defaults.",
            risks="Reviewed prose is not a proof of truth.",
        )
        self.assertTrue(data["changed"])
        self.assertEqual(data["title"], "Markdown `title` 雪 $()")
        self.assertIn("agent-authored", data["preview"])
        self.assertNotIn("Private requirement", data["preview"])
        for criterion in before["criteria"]:
            self.assertIn(criterion["text"], data["preview"])
        self.assertIn(run["next"]["evidence"]["tree"], data["preview"])
        self.assertIn("behavior", data["preview"])
        self.assertIn("Command retained in private verification", data["preview"])
        self.assertNotIn(str(f.root), data["preview"])
        after = read_run(run["run"])
        for key in ["verification", "codeReview", "failures", "planReview", "id", "configHash"]:
            self.assertEqual(after[key], before[key])
        for name, raw in proof.items():
            if name != "state.json":
                self.assertEqual((Path(run["run"]) / name).read_bytes(), raw)
        for name in [presentation.PRESENTATION, presentation.PREVIEW]:
            self.assertEqual((Path(run["run"]) / name).stat().st_mode & 0o777, 0o600)

    def test_cli_json_human_and_exact_idempotence_missing_preview(self):
        run = self.checked(self.fixture())
        path = self.input(run)
        output = self.cli("pr-description", "--run", run["run"], "--file", path, "--json")
        self.assertEqual(output.returncode, 0, output.stderr)
        result = json.loads(output.stdout)
        before = (Path(run["run"]) / "state.json").read_bytes()
        again = presentation.submit(run["run"], path)
        self.assertFalse(again["changed"])
        self.assertEqual((Path(run["run"]) / "state.json").read_bytes(), before)
        Path(result["previewFile"]).unlink()
        restored = presentation.submit(run["run"], path)
        self.assertFalse(restored["changed"])
        self.assertEqual(Path(restored["previewFile"]).read_text(), result["preview"])
        self.assertEqual((Path(run["run"]) / "state.json").read_bytes(), before)
        output = self.cli("pr-description", "--run", run["run"], "--file", path)
        self.assertEqual(output.returncode, 0, output.stderr)
        self.assertIn("Title: Add concise PR descriptions", output.stdout)
        self.assertIn(result["preview"], output.stdout)

    def test_invalid_schema_and_stale_paths_never_change_proof_or_budget(self):
        run = self.checked(self.fixture())
        for override in [
            {"version": True},
            {"unknown": 1},
            {"title": ""},
            {"title": "x" * 151},
            {"title": "a\nb"},
            {"title": "a\x7fb"},
            {"title": "a\u2028b"},
            {"summary": []},
            {"summary": [" "]},
            {"summary": ["x"] * 6},
            {"compatibility": None},
            {"risks": []},
            {"title": "\ud800"},
            {"evidence": {**run["next"]["evidence"], "paths": ["wrong"]}},
            {"evidence": {**run["next"]["evidence"], "head": "wrong"}},
        ]:
            with self.subTest(override=override):
                path = self.input(run, **override)
                before = self.private_bytes(run)
                with self.assertRaises(FactoryError):
                    presentation.submit(run["run"], path)
                self.assertEqual(self.private_bytes(run), before)
        self.assertEqual(read_run(run["run"])["failures"], 0)

    def test_unicode_storage_expansion_and_owned_symlinks_are_safe(self):
        run = self.checked(self.fixture())
        path = self.input(run)
        data = json.loads(path.read_text())
        data["summary"] = ["雪" * 3000]
        path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        self.assertLess(path.stat().st_size, presentation.INPUT_LIMIT)
        first = presentation.submit(run["run"], path)
        self.assertGreater(Path(first["presentation"]).stat().st_size, presentation.INPUT_LIMIT)
        self.assertFalse(presentation.submit(run["run"], path)["changed"])
        preview = Path(first["previewFile"])
        preview.unlink()
        protected = Path(run["run"]) / "protected.txt"
        protected.write_text("Synthetic unrelated content.")
        preview.symlink_to(protected)
        before = (Path(run["run"]) / "state.json").read_bytes()
        with self.assertRaisesRegex(FactoryError, "regular"):
            presentation.submit(run["run"], path)
        self.assertEqual(protected.read_text(), "Synthetic unrelated content.")
        self.assertEqual((Path(run["run"]) / "state.json").read_bytes(), before)

    def test_missing_input_and_never_verified_run_refuse_without_mutation(self):
        run = self.planned(self.fixture())
        state = read_run(run["run"])
        path = self.json_file(
            run["run"],
            "not-verified-input.json",
            {
                "version": 1,
                "evidence": engine.evidence(state),
                "title": "Unverified prose",
                "summary": ["Not yet verified."],
            },
        )
        before = self.private_bytes(run)
        with self.assertRaisesRegex(FactoryError, "verification"):
            presentation.submit(run["run"], path)
        self.assertEqual(self.private_bytes(run), before)
        missing = self.cli("pr-description", "--run", run["run"], "--json")
        self.assertEqual(missing.returncode, 2)
        self.assertIn("Missing --file", missing.stderr)
        with self.assertRaisesRegex(FactoryError, "Missing"):
            presentation.submit(run["run"], Path(run["run"]) / "absent.json")
        self.assertEqual(self.private_bytes(run), before)

    def test_unsafe_encoding_duplicate_keys_limits_and_infrastructure(self):
        run = self.checked(self.fixture())
        path = self.input(run)
        valid = path.read_bytes()
        for raw in [
            b"\xff",
            b"[]",
            b'{"version":1,"version":1}',
            valid.replace(b'"head":', b'"head":"duplicate","head":'),
            b"[" * 1100 + b"0" + b"]" * 1100,
            b'{"version":NaN}',
            b"x" * (presentation.INPUT_LIMIT + 1),
        ]:
            path.write_bytes(raw)
            before = self.private_bytes(run)
            output = self.cli("pr-description", "--run", run["run"], "--file", path, "--json")
            self.assertEqual(output.returncode, 2, output.stderr)
            self.assertNotIn("Traceback", output.stderr)
            self.assertEqual(self.private_bytes(run), before)
        path.write_bytes(valid)
        alias = Path(run["run"]) / "symlink-input.json"
        alias.symlink_to(path)
        with self.assertRaisesRegex(FactoryError, "regular"):
            presentation.submit(run["run"], alias)
        with self.assertRaisesRegex(FactoryError, "regular"):
            presentation.submit(run["run"], Path(run["run"]))
        with patch.object(presentation.os, "open", side_effect=PermissionError("synthetic denial")):
            with self.assertRaises(FactoryError) as caught:
                presentation.submit(run["run"], path)
        self.assertEqual(caught.exception.code, "infrastructure")

    def test_unverified_changed_and_active_intents_refuse_submission(self):
        f = self.fixture()
        run = self.checked(f)
        path = self.input(run)
        for field, value in [("operation", {"kind": "push"}), ("commitIntent", {}), ("delivery", {})]:
            state = read_run(run["run"])
            state[field] = value
            atomic_json(Path(run["run"]) / "state.json", state)
            before = self.private_bytes(run)
            with self.assertRaisesRegex(FactoryError, "intent"):
                presentation.submit(run["run"], path)
            self.assertEqual(self.private_bytes(run), before)
            state[field] = None
            atomic_json(Path(run["run"]) / "state.json", state)
        (Path(run["worktree"]) / "value.txt").write_text("changed since verification\n")
        before = self.private_bytes(run)
        with self.assertRaisesRegex(FactoryError, "verification"):
            presentation.submit(run["run"], path)
        self.assertEqual(self.private_bytes(run), before)

    def test_oversized_criteria_body_rejects_before_artifacts(self):
        f = self.fixture()
        run = self.checked(replace(f, options=replace(f.options, criteria=["雪" * 18000])))
        path = self.input(run)
        before = self.private_bytes(run)
        with self.assertRaisesRegex(FactoryError, "never truncated"):
            presentation.submit(run["run"], path)
        self.assertEqual(self.private_bytes(run), before)
        self.assertFalse((Path(run["run"]) / presentation.PRESENTATION).exists())

    def test_portable_literal_commands_table_escape_and_recorded_outcomes(self):
        run = self.checked(self.fixture())
        state = read_run(run["run"])
        data = json.loads(self.input(run).read_text())
        state["verification"]["results"][0].update(
            argv=["python3", "check.py", "literal | `ticks` $(text) 雪", "https://example.invalid/input"],
            durationMs=12.0,
        )
        body = presentation.render(state, data).decode()
        self.assertIn("&#124;", body)
        self.assertIn("`ticks` $(text) 雪", body)
        self.assertIn("https://example.invalid/input", body)
        self.assertNotIn("retained in private verification", body)
        self.assertIn("| passed | 12 |", body)
        for arg in [
            "/private/host/secret",
            "--config=/Users/person/config",
            "print('/tmp/host')",
            "C:\\private\\host",
            "\\\\host\\share",
            "~/private",
            "-I/Users/Synthetic/private/include",
            "//Users/Synthetic/private/include",
            "//private/tmp/synthetic/data",
            "-I//private/tmp/synthetic/include",
            "--output=//private/tmp/synthetic/output",
            "-L/private/tmp/synthetic/lib",
            "--output:/Users/Synthetic/private/output",
            "file:///Users/Synthetic/private/input",
            "--includeC:\\Synthetic\\private\\include",
            "--config=file:/private/tmp/synthetic/file",
        ]:
            state["verification"]["results"][0]["argv"] = ["python3", arg]
            body = presentation.render(state, data).decode()
            self.assertNotIn(arg, body)
            self.assertIn("retained in private verification", body)
        state["verification"]["results"][0]["passed"] = False
        self.assertIn("| failed |", presentation.render(state, data).decode())
        state["verification"]["results"] = []
        self.assertIn("| not-run |", presentation.render(state, data).decode())

    def test_initial_interrupted_submission_reuses_only_owned_files(self):
        run = self.checked(self.fixture())
        path = self.input(run)
        before = read_run(run["run"])
        with patch.object(presentation, "_atomic_text", side_effect=OSError("synthetic write interruption")):
            with self.assertRaises(OSError):
                presentation.submit(run["run"], path)
        self.assertEqual(read_run(run["run"]), before)
        self.assertTrue((Path(run["run"]) / presentation.PRESENTATION).exists())
        result = presentation.submit(run["run"], path)
        self.assertTrue(result["changed"])
        events = read_run(run["run"])["history"]
        self.assertEqual(sum(item["action"] == "pr-description-submitted" for item in events), 1)

    def test_description_before_or_after_review_still_needs_review_and_can_refresh(self):
        run = self.checked(self.fixture())
        self.submit(run)
        with self.assertRaisesRegex(FactoryError, "code review"):
            delivery.deliver(run["run"])
        self.review(run)
        self.submit(run, summary=["Reviewed prose updated before delivery intent."])
        self.assertEqual(engine.describe(read_run(run["run"]))["next"]["action"], "deliver")
        done = delivery.deliver(run["run"])
        self.assertEqual(done["phase"], "done")
        self.assertIn("presentationHash", read_run(run["run"])["commitIntent"])

    def test_interrupted_replacement_and_state_publication_can_be_explicitly_retried(self):
        run = self.checked(self.fixture())
        self.submit(run)
        path = self.input(run, summary=["Explicitly selected new summary."])
        before = read_run(run["run"])
        with patch.object(presentation, "save", side_effect=OSError("synthetic state publication interruption")):
            with self.assertRaises(OSError):
                presentation.submit(run["run"], path)
        self.assertEqual(read_run(run["run"]), before)
        with self.assertRaisesRegex(FactoryError, "changed"):
            presentation.load(read_run(run["run"]))
        result = presentation.submit(run["run"], path)
        self.assertTrue(result["changed"])
        self.assertIn("Explicitly selected new summary.", result["preview"])
        self.assertEqual(read_run(run["run"])["verification"], before["verification"])
        self.assertEqual(
            sum(item["action"] == "pr-description-submitted" for item in read_run(run["run"])["history"]), 2
        )

    def test_commit_intent_and_observation_interruption_preserve_selection(self):
        for event in ["commit-intent", "commit-observed", "pr-body-selected"]:
            with self.subTest(event=event):
                f = self.fixture("draft-pr")
                remote = self.github(f)
                run = self.reviewed(f)
                self.submit(run)
                original = delivery.save

                def interrupt(state, action, **details):
                    original(state, action, **details)
                    if action == event:
                        raise OSError("synthetic delivery observation interruption")

                with (
                    patch.object(delivery, "save", side_effect=interrupt),
                    patch.object(presentation, "save", side_effect=interrupt),
                ):
                    with self.assertRaises(OSError):
                        delivery.deliver(run["run"])
                selected = read_run(run["run"])["commitIntent"]["presentationHash"]
                final = delivery.deliver(run["run"])
                self.assertEqual(read_run(run["run"])["commitIntent"]["presentationHash"], selected)
                self.assertEqual(json.loads(remote.read_text())["headRefOid"], final["delivery"]["commit"])
                self.assertEqual(git(run["worktree"], ["rev-list", "--count", "main..HEAD"]).strip(), "1")

    def test_existing_wrong_head_base_state_and_ambiguity_remain_pending(self):
        for mutation in [
            {"headRefOid": "0" * 40},
            {"baseRefName": "wrong"},
            {"state": "CLOSED"},
            {"isDraft": False},
            "ambiguous",
        ]:
            with self.subTest(mutation=mutation):
                f = self.fixture("draft-pr")
                remote = self.github(f)
                run = self.reviewed(f)
                self.submit(run)
                with patch.dict(os.environ, {"MOCK_FAIL": "1"}):
                    with self.assertRaises(FactoryError):
                        delivery.deliver(run["run"])
                if mutation == "ambiguous":
                    with patch.object(delivery, "_find_pr", side_effect=FactoryError("Ambiguous PR response")):
                        with self.assertRaisesRegex(FactoryError, "Ambiguous"):
                            delivery.deliver(run["run"])
                else:
                    original = json.loads(remote.read_text())
                    remote.write_text(json.dumps({**original, **mutation}))
                    before = remote.read_bytes()
                    with self.assertRaisesRegex(FactoryError, "not an open draft"):
                        delivery.deliver(run["run"])
                    self.assertEqual(remote.read_bytes(), before)
                self.assertNotEqual(read_run(run["run"])["phase"], "done")

    def test_custom_create_final_commit_literal_title_and_private_body(self):
        f = self.fixture("draft-pr")
        remote = self.github(f)
        run = self.reviewed(f)
        self.submit(
            run,
            title="Literal `Markdown` 雪 $(no-shell)",
            summary=["Concise **behavior** $(literal), without copying the task."],
        )
        result = delivery.deliver(run["run"])
        observed = json.loads(remote.read_text())
        self.assertEqual(observed["title"], "Literal `Markdown` 雪 $(no-shell)")
        self.assertIn("Concise **behavior** $(literal)", observed["body"])
        self.assertIn(result["delivery"]["commit"], observed["body"])
        self.assertNotIn("## Task", observed["body"])
        self.assertEqual(result["delivery"]["presentation"]["outcome"], "applied-by-create")
        state = read_run(run["run"])
        self.assertEqual((Path(run["run"]) / presentation.BODY).stat().st_mode & 0o777, 0o600)
        self.assertIn("bodyHash", state["commitIntent"])
        self.assertEqual(observed["headRefOid"], result["delivery"]["commit"])

    def test_uncertain_create_reconciles_existing_metadata_without_duplicates(self):
        f = self.fixture("draft-pr")
        remote = self.github(f)
        run = self.reviewed(f)
        self.submit(run)
        with patch.dict(os.environ, {"MOCK_FAIL": "1"}):
            with self.assertRaises(FactoryError):
                delivery.deliver(run["run"])
        original = json.loads(remote.read_text())
        changed = {**original, "title": "Human-edited title", "body": "Human-edited body"}
        remote.write_text(json.dumps(changed))
        final = delivery.deliver(run["run"])
        self.assertEqual(json.loads(remote.read_text()), changed)
        self.assertEqual(final["delivery"]["commit"], original["headRefOid"])
        self.assertEqual(final["delivery"]["presentation"]["outcome"], "reconciled-existing")
        self.assertEqual(git(run["worktree"], ["rev-list", "--count", "main..HEAD"]).strip(), "1")

    def test_failed_push_and_immutable_artifact_body_recovery(self):
        for damage in ["presentation", "missing-presentation", "body", "missing-body", "intent", None]:
            with self.subTest(damage=damage):
                f = self.fixture("draft-pr")
                remote = self.github(f)
                run = self.reviewed(f)
                self.submit(run)
                original = delivery.git

                def fail_push(root, args, *extra, **kwargs):
                    if args[0] == "push":
                        raise FactoryError("Synthetic push interruption", "infrastructure")
                    return original(root, args, *extra, **kwargs)

                with patch.object(delivery, "git", side_effect=fail_push):
                    with self.assertRaisesRegex(FactoryError, "push interruption"):
                        delivery.deliver(run["run"])
                state = read_run(run["run"])
                selected = state["commitIntent"].copy()
                head = git(run["worktree"], ["rev-parse", "HEAD"]).strip()
                self.assertIn("bodyHash", selected)
                with self.assertRaisesRegex(FactoryError, "intent"):
                    self.submit(run)
                if damage in ["presentation", "body"]:
                    file = Path(run["run"]) / (
                        presentation.PRESENTATION if damage == "presentation" else presentation.BODY
                    )
                    file.write_bytes(file.read_bytes() + b" ")
                elif damage in ["missing-presentation", "missing-body"]:
                    (
                        Path(run["run"])
                        / (presentation.PRESENTATION if damage == "missing-presentation" else presentation.BODY)
                    ).unlink()
                elif damage == "intent":
                    state["commitIntent"]["presentationHash"] = "changed"
                    atomic_json(Path(run["run"]) / "state.json", state)
                if damage is not None:
                    with self.assertRaises(FactoryError):
                        delivery.deliver(run["run"])
                    self.assertFalse(remote.exists())
                    self.assertEqual(git(run["worktree"], ["rev-parse", "HEAD"]).strip(), head)
                    self.assertNotEqual(read_run(run["run"])["phase"], "done")
                else:
                    final = delivery.deliver(run["run"])
                    self.assertEqual(final["delivery"]["commit"], head)
                    self.assertEqual(read_run(run["run"])["commitIntent"], selected)

    def test_tampered_presentation_before_commit_never_falls_back(self):
        run = self.reviewed(self.fixture())
        self.submit(run)
        path = Path(run["run"]) / presentation.PRESENTATION
        path.write_bytes(path.read_bytes() + b" ")
        before = git(run["worktree"], ["rev-parse", "HEAD"]).strip()
        with self.assertRaisesRegex(FactoryError, "changed"):
            delivery.deliver(run["run"])
        self.assertEqual(git(run["worktree"], ["rev-parse", "HEAD"]).strip(), before)
        self.assertIsNone(read_run(run["run"])["commitIntent"])

    def test_no_input_exact_default_title_body_intent_and_no_new_length_cap(self):
        f = self.fixture("draft-pr")
        remote = self.github(f)
        f = replace(f, options=replace(f.options, task="Default title\n\n" + "Long request preserved. " * 2500))
        run = self.reviewed(f)
        result = delivery.deliver(run["run"])
        state = read_run(run["run"])
        observed = json.loads(remote.read_text())
        criteria = "\n".join(f"- {item['text']}" for item in state["criteria"])
        checks = "\n".join(f"- {item['name']}: passed" for item in state["verification"]["results"])
        expected = f"## Task\n\n{state['task']}\n\n## Acceptance criteria\n\n{criteria}\n\n## Verification\n\n{checks}\n\nReviewed commit: {result['delivery']['commit']}\n"
        self.assertEqual(observed["body"], expected)
        self.assertGreater(len(expected.encode()), presentation.BODY_LIMIT)
        self.assertEqual(observed["title"], "Default title")
        self.assertEqual(set(state["commitIntent"]), {"parent", "tree", "paths"})
        self.assertNotIn("prPresentation", state)
        self.assertNotIn("presentation", state["delivery"])
