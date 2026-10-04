"""Real Git policy checks and synthetic boundary tests for trusted automation."""

import io
import subprocess
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from scripts import auto_merge, ci_policy, github_api, release, verify

REPO = "example/factory"
HEAD = "a" * 40
MERGE = "b" * 40


def ci_run():
    return {
        "event": "pull_request",
        "conclusion": "success",
        "head_sha": HEAD,
        "path": ".github/workflows/ci.yml",
        "repository": {"full_name": REPO},
    }


def pull_request(*, merged=False):
    return {
        "number": 7,
        "state": "closed" if merged else "open",
        "merged": merged,
        "draft": False,
        "head": {"sha": HEAD, "repo": {"full_name": REPO}},
        "base": {"ref": "main", "repo": {"full_name": REPO}},
        "user": {"login": "maintainer"},
        "merge_commit_sha": MERGE if merged else None,
    }


class CommitPolicyTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="factory-policy-")
        self.addCleanup(self.temporary.cleanup)
        self.repo = Path(self.temporary.name)
        ci_policy.git(self.repo, "init", "-b", "main")
        ci_policy.git(self.repo, "config", "user.name", "Synthetic Policy Test")
        ci_policy.git(self.repo, "config", "user.email", "factory@example.invalid")
        ci_policy.git(self.repo, "config", "commit.gpgsign", "false")
        (self.repo / "value.txt").write_text("baseline")
        self.base = self.commit()

    def commit(self):
        ci_policy.git(self.repo, "add", "-A")
        ci_policy.git(self.repo, "commit", "-m", "synthetic policy fixture")
        return ci_policy.git(self.repo, "rev-parse", "HEAD").strip()

    def write_test_file(self, value=1, comment=""):
        (self.repo / "tests").mkdir(exist_ok=True)
        (self.repo / "tests/test_value.py").write_text(
            f"import unittest\nclass ValueTests(unittest.TestCase):\n"
            f"    def test_value(self):\n        {comment}\n        self.assertEqual({value}, {value})\n"
        )

    def test_added_and_semantically_updated_test_is_associated(self):
        self.write_test_file()
        one = self.commit()
        self.write_test_file(2)
        two = self.commit()
        reports = ci_policy.inspect_range(self.repo, self.base, two, {"tests.test_value.ValueTests.test_value"})
        self.assertEqual([report["commit"] for report in reports], [one, two])
        self.assertTrue(all(report["tests"] for report in reports))

    def test_comment_or_deleted_test_does_not_satisfy_commit(self):
        self.write_test_file()
        baseline = self.commit()
        self.write_test_file(comment="# only a comment")
        with self.assertRaisesRegex(ValueError, "needs an added"):
            ci_policy.inspect_range(self.repo, baseline, self.commit())
        (self.repo / "tests/test_value.py").unlink()
        with self.assertRaises(ValueError):
            ci_policy.inspect_range(self.repo, baseline, self.commit())

    def test_test_added_later_does_not_cover_earlier_commit(self):
        (self.repo / "value.txt").write_text("untested change")
        offending = self.commit()
        self.write_test_file()
        with self.assertRaisesRegex(ValueError, offending[:12]):
            ci_policy.inspect_range(self.repo, self.base, self.commit())

    def test_skipped_or_undiscovered_test_cannot_satisfy_association(self):
        self.write_test_file()
        head = self.commit()
        with self.assertRaises(ValueError):
            ci_policy.inspect_range(self.repo, self.base, head, set())

    def test_empty_range_and_invalid_revision(self):
        self.assertEqual(ci_policy.inspect_range(self.repo, self.base, self.base), [])
        with self.assertRaises(ValueError):
            ci_policy.inspect_range(self.repo, "--help", self.base)

    def test_merge_commit_cannot_hide_untested_resolution(self):
        self.write_test_file()
        baseline = self.commit()
        ci_policy.git(self.repo, "checkout", "-b", "feature/other")
        self.write_test_file(2)
        other = self.commit()
        ci_policy.git(self.repo, "checkout", "main")
        (self.repo / "value.txt").write_text("resolution without test")
        tree = ci_policy.git(self.repo, "write-tree").strip()
        # Explicit synthetic two-parent object with only an untested resolution.
        ci_policy.git(self.repo, "add", "value.txt")
        tree = ci_policy.git(self.repo, "write-tree").strip()
        merge = ci_policy.git(
            self.repo, "commit-tree", tree, "-p", baseline, "-p", other, "-m", "synthetic merge resolution"
        ).strip()
        with self.assertRaisesRegex(ValueError, merge[:12]):
            ci_policy.inspect_range(self.repo, other, merge)

    def test_new_branch_push_uses_main_merge_base(self):
        ci_policy.git(self.repo, "update-ref", "refs/remotes/origin/main", self.base)
        self.write_test_file()
        head = self.commit()
        self.assertEqual(
            ci_policy.event_range(self.repo, {"before": "0" * 40, "after": head}, "push"), (self.base, head)
        )

    def test_success_report_excludes_skips(self):
        class Results(unittest.TestCase):
            def test_pass(self):
                self.assertTrue(True)

            @unittest.skip("synthetic skip")
            def test_skip(self):
                self.fail("must not run")

        result = unittest.TextTestRunner(stream=io.StringIO(), resultclass=verify.TestResults).run(
            unittest.defaultTestLoader.loadTestsFromTestCase(Results)
        )
        self.assertEqual(len(result.passed), 1)
        self.assertTrue(result.passed[0].endswith("test_pass"))


class AutoMergeTests(unittest.TestCase):
    def test_only_ready_current_same_repo_main_write_pr_is_eligible(self):
        self.assertTrue(auto_merge.eligible(pull_request(), ci_run(), REPO, "write"))
        for field, value in (("draft", True), ("state", "closed")):
            pr = pull_request()
            pr[field] = value
            self.assertFalse(auto_merge.eligible(pr, ci_run(), REPO, "write"))
        for path, value in (("head", "fork/factory"), ("base", "fork/factory")):
            pr = pull_request()
            pr[path]["repo"]["full_name"] = value
            self.assertFalse(auto_merge.eligible(pr, ci_run(), REPO, "write"))
        pr = pull_request()
        pr["head"]["sha"] = MERGE
        self.assertFalse(auto_merge.eligible(pr, ci_run(), REPO, "write"))
        pr = pull_request()
        pr["base"]["ref"] = "other"
        self.assertFalse(auto_merge.eligible(pr, ci_run(), REPO, "write"))
        self.assertFalse(auto_merge.eligible(pull_request(), ci_run(), REPO, "read"))

    def test_failed_or_wrong_workflow_cannot_merge(self):
        for field, value in (("conclusion", "failure"), ("event", "push"), ("path", ".github/workflows/other.yml")):
            run = ci_run()
            run[field] = value
            self.assertFalse(auto_merge.eligible(pull_request(), run, REPO, "admin"))

    def test_merge_and_resumed_dispatch_bind_exact_merge_commit(self):
        for already_merged in (False, True):
            with self.subTest(already_merged=already_merged):
                prs = iter([pull_request(merged=already_merged), pull_request(merged=True)])
                dispatched = []

                def fake_api(path, **kwargs):
                    if path.endswith("/runs/9"):
                        return ci_run()
                    if "/commits/" in path:
                        return [{"number": 7}]
                    if path.endswith("/pulls/7"):
                        return next(prs)
                    if path.endswith("/permission"):
                        return {"permission": "admin"}
                    if path.endswith("/dispatches"):
                        dispatched.append(kwargs["data"])
                        return None
                    self.fail(path)

                with (
                    patch.object(auto_merge, "api", side_effect=fake_api),
                    patch.object(auto_merge, "command") as command,
                ):
                    result = auto_merge.merge_run(REPO, 9)
                self.assertEqual(result[0]["commit"], MERGE)
                self.assertEqual(dispatched, [{"ref": "main", "inputs": {"commit": MERGE}}])
                self.assertEqual(command.call_count, 0 if already_merged else 1)
                if not already_merged:
                    self.assertIn("--match-head-commit", command.call_args.args)
                    self.assertEqual(command.call_args.args[-1], HEAD)

    def test_uncertain_dispatch_fails_visibly_and_can_be_retried(self):
        def fake_api(path, **kwargs):
            if path.endswith("/runs/9"):
                return ci_run()
            if "/commits/" in path:
                return [{"number": 7}]
            if path.endswith("/pulls/7"):
                return pull_request(merged=True)
            if path.endswith("/permission"):
                return {"permission": "write"}
            raise RuntimeError("synthetic dispatch failure")

        with patch.object(auto_merge, "api", side_effect=fake_api), patch.object(auto_merge, "command") as command:
            with self.assertRaisesRegex(RuntimeError, "dispatch failure"):
                auto_merge.merge_run(REPO, 9)
            command.assert_not_called()


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="factory-release-")
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def assets(self, version="0.2.1"):
        metadata = f"Metadata-Version: 2.4\nName: software-factory\nVersion: {version}\n\n".encode()
        wheel = self.folder / "software_factory-0.2.1-py3-none-any.whl"
        with zipfile.ZipFile(wheel, "w") as archive:
            archive.writestr("software_factory-0.2.1.dist-info/METADATA", metadata)
        source = self.folder / "software_factory-0.2.1.tar.gz"
        with tarfile.open(source, "w:gz") as archive:
            entry = tarfile.TarInfo("software_factory-0.2.1/PKG-INFO")
            entry.size = len(metadata)
            archive.addfile(entry, io.BytesIO(metadata))
        return [wheel, source]

    def test_patch_allocation_and_exact_commit_retry(self):
        self.assertEqual(release.select_version({}, HEAD), "0.2.1")
        self.assertEqual(release.select_version({"v0.2.9": MERGE, "v0.3.0rc1": HEAD}, HEAD), "0.2.10")
        self.assertEqual(release.select_version({"v0.2.1": HEAD, "v0.2.2": MERGE}, HEAD), "0.2.1")
        with self.assertRaises(ValueError):
            release.select_version({"v0.2.1": HEAD, "v0.2.2": HEAD}, HEAD)

    def test_archive_versions_and_checksum_match(self):
        paths = self.assets()
        self.assertEqual(release.validate_assets(self.folder, "0.2.1"), paths)
        sums = release.checksums(paths)
        self.assertEqual(len(sums.splitlines()), 2)
        self.assertTrue(all(len(line.split()[0]) == 64 for line in sums.splitlines()))

    def test_wrong_archive_version_refuses_publication(self):
        self.assets("0.2.2")
        with self.assertRaises(ValueError):
            release.validate_assets(self.folder, "0.2.1")

    def test_tag_conflict_never_moves_existing_tag(self):
        self.assets()
        with patch.object(release, "tag_commit", return_value=MERGE), patch.object(release, "api") as api:
            with self.assertRaisesRegex(ValueError, "another commit"):
                release.publish(REPO, HEAD, "0.2.1", self.folder)
            api.assert_not_called()

    def test_published_retry_is_read_only(self):
        self.assets()
        record = {
            "tag_name": "v0.2.1",
            "draft": False,
            "prerelease": False,
            "html_url": "https://github.com/example/factory/releases/tag/v0.2.1",
        }
        with (
            patch.object(release, "tag_commit", return_value=HEAD),
            patch.object(release, "api", return_value=[record]),
            patch.object(release, "verify_published") as verify_published,
            patch.object(release, "command") as command,
        ):
            result = release.publish(REPO, HEAD, "0.2.1", self.folder)
        self.assertEqual(result["state"], "already-published")
        verify_published.assert_called_once()
        command.assert_not_called()

    def test_draft_retry_verifies_upload_before_publication(self):
        paths = self.assets()
        draft = {
            "tag_name": "v0.2.1",
            "draft": True,
            "prerelease": False,
            "assets": [{"name": path.name} for path in paths] + [{"name": "SHA256SUMS"}],
        }
        published = {**draft, "draft": False, "html_url": "https://github.com/example/factory/releases/tag/v0.2.1"}
        records = iter([draft, draft, published])
        operations = []

        def lookup(path, **kwargs):
            if path == f"repos/{REPO}/releases?per_page=100&page=1":
                return [next(records)]
            raise RuntimeError("Tag endpoint cannot discover the draft (HTTP 404)")

        def command(*argv):
            operation = argv[2]
            operations.append(operation)
            if operation == "download":
                destination = Path(argv[-1])
                for source in [*paths, self.folder / "SHA256SUMS"]:
                    (destination / source.name).write_bytes(source.read_bytes())
            elif operation not in ("upload", "edit"):
                self.fail(f"Existing draft must not be recreated: {argv}")

        with (
            patch.object(release, "tag_commit", return_value=HEAD),
            patch.object(release, "api", side_effect=lookup),
            patch.object(release, "command", side_effect=command),
        ):
            result = release.publish(REPO, HEAD, "0.2.1", self.folder)
        self.assertEqual(result["state"], "published")
        self.assertEqual(operations, ["upload", "download", "edit"])
        self.assertEqual((self.folder / "SHA256SUMS").read_text(), release.checksums(paths))

    def test_release_lookup_finds_draft_on_later_page(self):
        draft = {"tag_name": "v0.2.1", "draft": True}
        with patch.object(release, "api", side_effect=[[{"tag_name": "v9.0.0"}] * 100, [draft]]) as api:
            self.assertEqual(release.find_release(REPO, "v0.2.1"), draft)
        self.assertEqual(
            [call.args[0] for call in api.call_args_list],
            [f"repos/{REPO}/releases?per_page=100&page={page}" for page in (1, 2)],
        )

    def test_release_lookup_short_page_means_absent(self):
        with patch.object(release, "api", return_value=[{"tag_name": "v0.2.2"}]) as api:
            self.assertIsNone(release.find_release(REPO, "v0.2.1"))
        api.assert_called_once_with(f"repos/{REPO}/releases?per_page=100&page=1")

    def test_release_lookup_bound_fails_closed(self):
        with patch.object(release, "api", return_value=[{"tag_name": "v9.0.0"}] * 100) as api:
            with self.assertRaisesRegex(ValueError, "pagination bound"):
                release.find_release(REPO, "v0.2.1")
        self.assertEqual(api.call_count, 100)

    def test_release_lookup_propagates_repository_and_authentication_errors(self):
        for status in (403, 404):
            with self.subTest(status=status), patch.object(release, "api", side_effect=RuntimeError(f"HTTP {status}")):
                with self.assertRaisesRegex(RuntimeError, str(status)):
                    release.find_release(REPO, "v0.2.1")

    def test_mutation_requires_observed_release(self):
        with patch.object(release, "api", return_value=[]):
            with self.assertRaisesRegex(ValueError, "not observed"):
                release.require_release(REPO, "v0.2.1")

    def test_checksum_readback_accepts_real_archive_metadata_and_checksums(self):
        paths = self.assets()
        record = {"assets": [{"name": path.name} for path in paths] + [{"name": "SHA256SUMS"}]}

        def download(*argv):
            destination = Path(argv[-1])
            for source in paths:
                (destination / source.name).write_bytes(source.read_bytes())
            (destination / "SHA256SUMS").write_text(release.checksums(paths))

        with patch.object(release, "command", side_effect=download) as command:
            release.verify_published(REPO, "v0.2.1", "0.2.1", record)
        self.assertEqual(command.call_args.args[:7], ("gh", "release", "download", "v0.2.1", "--repo", REPO, "--dir"))

    def test_checksum_readback_rejects_corruption(self):
        self.assets()
        record = {"assets": [{"name": path.name} for path in self.assets()] + [{"name": "SHA256SUMS"}]}

        def download(*argv):
            folder = Path(argv[-1])
            for source in self.assets():
                (folder / source.name).write_bytes(source.read_bytes())
            (folder / "SHA256SUMS").write_text("corrupted")

        with patch.object(release, "command", side_effect=download), self.assertRaisesRegex(ValueError, "checksums"):
            release.verify_published(REPO, "v0.2.1", "0.2.1", record)

    def test_prepare_validates_main_history_before_checkout(self):
        calls = []

        def fake_git(repo, *args):
            calls.append(args)
            if args[0] == "rev-list":
                return MERGE
            return ""

        with patch.object(release, "git", side_effect=fake_git), self.assertRaisesRegex(ValueError, "first-parent"):
            release.prepare(self.folder, HEAD, checkout=True)
        self.assertFalse(any(call[0] == "checkout" for call in calls))

    def test_real_main_tag_allocation_and_retry_are_stable(self):
        ci_policy.git(self.folder, "init", "-b", "main")
        ci_policy.git(self.folder, "config", "user.name", "Synthetic Release Test")
        ci_policy.git(self.folder, "config", "user.email", "factory@example.invalid")
        ci_policy.git(self.folder, "config", "commit.gpgsign", "false")
        (self.folder / "source.py").write_text("value = 1\n")
        ci_policy.git(self.folder, "add", "source.py")
        ci_policy.git(self.folder, "commit", "-m", "synthetic release fixture")
        head = ci_policy.git(self.folder, "rev-parse", "HEAD").strip()
        ci_policy.git(self.folder, "update-ref", "refs/remotes/origin/main", head)
        first = release.prepare(self.folder, head, checkout=True)
        self.assertEqual(first, {"version": "0.2.1", "tag": "v0.2.1", "commit": head})
        self.assertEqual(release.prepare(self.folder, head), first)
        self.assertEqual(ci_policy.git(self.folder, "rev-parse", "v0.2.1^{commit}").strip(), head)
        (self.folder / "source.py").write_text("value = 2\n")
        with self.assertRaisesRegex(ValueError, "clean"):
            release.prepare(self.folder, head)

    def test_missing_api_only_treats_404_as_absent(self):
        for stderr, absent in (("HTTP 404", True), ("HTTP 403", False)):
            result = subprocess.CompletedProcess([], 1, "", stderr)
            with patch.object(github_api.subprocess, "run", return_value=result):
                if absent:
                    self.assertIsNone(github_api.api("synthetic", missing=True))
                else:
                    with self.assertRaises(RuntimeError):
                        github_api.api("synthetic", missing=True)


class WorkflowTests(unittest.TestCase):
    def test_readiness_stable_gate_and_release_serialization_contract(self):
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        ci = (root / "ci.yml").read_text()
        self.assertIn("ready_for_review", ci)
        self.assertNotIn("paths:", ci)
        self.assertIn("name: test", ci)
        self.assertIn("--results", ci)
        publication = (root / "release.yml").read_text()
        self.assertIn("queue: max", publication)
        self.assertIn("cancel-in-progress: false", publication)
        self.assertIn("--checkout", publication)
        self.assertNotIn("cache:", publication)
        merger = (root / "auto-merge.yml").read_text()
        self.assertIn("ref: main", merger)
        self.assertNotIn("pull_request_target", merger)
        self.assertNotIn("download-artifact", merger)
