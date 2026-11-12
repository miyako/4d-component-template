"""Execute source release operations only in initialized disposable Git repos."""
from contextlib import redirect_stderr, redirect_stdout
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import unittest
from unittest.mock import patch
import uuid


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import bump_release
import initialize
import release_source


class ReleaseSourceTests(unittest.TestCase):
    repository = "owner/CaseTools"
    origin_url = "https://github.com/owner/CaseTools.git"

    def setUp(self):
        self.workspace = ROOT / (".release-source-test-" + uuid.uuid4().hex)
        self.root = self.workspace / "source"
        self.origin = self.workspace / "origin.git"
        self.root.mkdir(parents=True)
        self.addCleanup(shutil.rmtree, self.workspace)
        for name in ("component", "cli-starters", "tests/host", ".github/workflows",
                     "scripts", "tooling"):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ("template.json", "package.json", "README.md", "release-policy.json",
                     "workflow-contract.json", "tests/test_cli.py", "tests/cli-contract.json"):
            shutil.copy2(ROOT / name, self.root / name)
        self.environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": self.repository})
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.availability_patch = patch.object(release_source, "available")
        self.available = self.availability_patch.start()
        self.addCleanup(self.availability_patch.stop)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Source release fixture")
        self.git("config", "user.email", "source-fixture@example.invalid")
        self.git("remote", "add", "origin", self.origin_url)
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")
        initialize.initialize(self.root, "CaseTools", "IndependentNS", "case-cli",
                              "go", "A source release fixture")
        self.commit("initialized fixture")
        subprocess.run(["git", "init", "-q", "--bare", str(self.origin)],
                       check=True, capture_output=True, text=True)
        self.git("config", "url." + str(self.origin) + ".insteadOf", self.origin_url)
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")
        # Git expands insteadOf in get-url, but the configured origin is GitHub.
        self.identity_patch = patch.object(bump_release, "github_repository",
                                           return_value=self.repository)
        self.identity_patch.start()
        self.addCleanup(self.identity_patch.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def commit(self, message):
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", message)
        return self.git("rev-parse", "HEAD")

    def env(self, branch="main", **changes):
        result = {"GITHUB_EVENT_NAME": "workflow_dispatch",
                  "GITHUB_REF": "refs/heads/" + branch,
                  "GITHUB_SHA": self.git("rev-parse", "HEAD")}
        result.update(changes)
        return result

    def remote_refs(self):
        return self.git("ls-remote", "--refs", "origin")

    def snapshot(self):
        return {str(path.relative_to(self.root)): path.read_bytes()
                for path in self.root.rglob("*")
                if path.is_file() and ".git" not in path.relative_to(self.root).parts}

    def state(self):
        return (self.snapshot(), self.git("rev-parse", "HEAD"),
                self.git("status", "--porcelain", "--untracked-files=all"),
                self.git("diff", "--cached"), self.git("tag", "--list"), self.remote_refs())

    def advance_remote(self, *, parent=True, branch="main"):
        tree = self.git("rev-parse", "HEAD^{tree}")
        args = ["commit-tree", tree, "-m", "remote-only revision"]
        if parent:
            args += ["-p", self.git("rev-parse", "HEAD")]
        revision = self.git(*args)
        self.git("push", "-q", "--force", "origin", revision + ":refs/heads/" + branch)
        return revision

    def test_dispatch_returns_exact_branch_and_immutable_sha_without_writes(self):
        for branch in ("main", "selected", "feature/version"):
            with self.subTest(branch=branch):
                env = self.env(branch)
                before = self.state()
                self.assertEqual(release_source.dispatch_source(self.root, env),
                                 (env["GITHUB_REF"], env["GITHUB_SHA"]))
                self.assertEqual(before, self.state())
        self.available.assert_not_called()

    def test_dispatch_rejects_wrong_head_invalid_sha_events_and_nonbranches(self):
        invalid = [
            {"GITHUB_SHA": "0" * 40}, {"GITHUB_SHA": "abc1234"},
            {"GITHUB_SHA": "A" * 40}, {"GITHUB_SHA": "f" * 64},
            {"GITHUB_SHA": ""}, {"GITHUB_EVENT_NAME": "push"},
            {"GITHUB_EVENT_NAME": "pull_request"}, {"GITHUB_EVENT_NAME": ""},
            {"GITHUB_REF": "refs/tags/0.1.0"}, {"GITHUB_REF": "refs/pull/1/head"},
            {"GITHUB_REF": "main"}, {"GITHUB_REF": "refs/heads/"},
            {"GITHUB_REF": "refs/heads/invalid..branch"},
        ]
        before = self.state()
        for changes in invalid:
            with self.subTest(changes=changes):
                with self.assertRaises((ValueError, subprocess.CalledProcessError)):
                    release_source.dispatch_source(self.root, self.env(**changes))
                self.assertEqual(before, self.state())
        self.available.assert_not_called()

    def test_bump_commits_only_bounded_metadata_and_pushes_only_selected_branch(self):
        initial = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "-b", "selected")
        self.git("push", "-q", "origin", "HEAD:refs/heads/selected")
        before = self.snapshot()
        _, planned = bump_release.plan(self.root, "0.1.1", self.repository)
        with patch.object(release_source, "git", wraps=release_source.git) as commands:
            result = release_source.bump(self.root, self.repository, "patch", self.env("selected"))
        self.assertEqual(result["version"], "0.1.1")
        self.assertEqual(result["tag"], "0.1.1")
        self.assertEqual(result["branch"], "refs/heads/selected")
        self.assertEqual(result["source_sha"], self.git("rev-parse", "HEAD"))
        self.assertNotEqual(result["source_sha"], initial)
        self.assertEqual(self.git("rev-parse", "HEAD^"), initial)
        self.assertEqual(set(self.git("diff-tree", "--no-commit-id", "--name-only",
                                     "-r", "HEAD").splitlines()), set(planned))
        after = self.snapshot()
        self.assertEqual({name for name in before if before[name] != after[name]}, set(planned))
        self.assertEqual(bump_release.plan(self.root, "0.1.1", self.repository)[1], {})
        self.assertEqual(self.git("status", "--porcelain"), "")
        refs = dict(line.split("\t")[::-1] for line in self.remote_refs().splitlines())
        self.assertEqual(refs, {"refs/heads/main": initial,
                                "refs/heads/selected": result["source_sha"]})
        self.assertEqual(self.git("tag", "--list"), "")
        self.assertEqual([call.args[1:] for call in commands.call_args_list
                          if call.args[1] == "push"],
                         [("push", "origin", "HEAD:refs/heads/selected")])
        self.assertFalse(any(call.args[1] in ("tag", "dispatch", "release")
                             for call in commands.call_args_list))
        self.available.assert_not_called()

    def test_repeated_bump_increments_current_source_without_stable_tags(self):
        previous = self.git("rev-parse", "HEAD")
        for mode, version in (("patch", "0.1.1"), ("patch", "0.1.2"),
                              ("minor", "0.2.0"), ("major", "1.0.0")):
            with self.subTest(mode=mode, version=version):
                result = release_source.bump(self.root, self.repository, mode, self.env())
                self.assertEqual(result["version"], version)
                self.assertEqual(self.git("rev-parse", "HEAD^"), previous)
                previous = result["source_sha"]
                self.assertEqual(self.remote_refs(), previous + "\trefs/heads/main")
                self.assertEqual(bump_release.plan(self.root, version, self.repository)[1], {})
        self.assertEqual(self.git("tag", "--list"), "")
        self.available.assert_not_called()

    def test_bump_stops_before_writes_when_selected_branch_moved(self):
        env = self.env()
        self.advance_remote()
        before = self.state()
        with patch.object(release_source, "next_version") as next_version:
            with self.assertRaisesRegex(ValueError, "moved since dispatch"):
                release_source.bump(self.root, self.repository, "patch", env)
        next_version.assert_not_called()
        self.available.assert_not_called()
        self.assertEqual(before, self.state())

    def test_dirty_worktree_index_and_untracked_source_reject_all_operations(self):
        path = self.root / "README.md"
        original = path.read_bytes()
        for kind in ("worktree", "index", "untracked"):
            with self.subTest(kind=kind):
                if kind == "untracked":
                    dirty = self.root / "untracked-source.txt"
                    dirty.write_text("untracked\n")
                else:
                    path.write_bytes(original + b"\nunsynchronized source\n")
                    if kind == "index":
                        self.git("add", "--", "README.md")
                        path.write_bytes(original)
                before = self.state()
                with patch.object(release_source, "fetch_branch") as fetch:
                    for operation in (
                            lambda: release_source.dispatch_source(self.root, self.env()),
                            lambda: release_source.bump(self.root, self.repository, "patch", self.env()),
                            lambda: release_source.preflight(self.root, self.repository, self.env())):
                        with self.assertRaisesRegex(ValueError, "clean"):
                            operation()
                    fetch.assert_not_called()
                self.assertEqual(before, self.state())
                self.available.assert_not_called()
                self.git("restore", "--staged", "--", "README.md")
                path.write_bytes(original)
                if kind == "untracked":
                    dirty.unlink()

    def test_preflight_returns_synchronized_stable_version_and_dispatch_sha(self):
        bump_release.apply(self.root, "2.3.4", self.repository)
        sha = self.commit("synchronized version")
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")
        before = self.state()
        result = release_source.preflight(self.root, self.repository, self.env())
        self.assertEqual(result, {"source_sha": sha, "release_tag": "2.3.4"})
        self.available.assert_called_once_with(self.root, self.repository, "2.3.4")
        self.assertEqual(before, self.state())

    def test_preflight_keeps_dispatch_sha_when_main_advances(self):
        env = self.env()
        later = self.advance_remote()
        before = self.state()
        result = release_source.preflight(self.root, self.repository, env)
        self.assertEqual(result, {"source_sha": env["GITHUB_SHA"], "release_tag": "0.1.0"})
        self.assertNotEqual(result["source_sha"], later)
        self.assertEqual(before, self.state())
        self.available.assert_called_once_with(self.root, self.repository, "0.1.0")

    def test_preflight_requires_main_dispatch_before_source_or_network_operations(self):
        for changes in ({"GITHUB_REF": "refs/heads/selected"},
                        {"GITHUB_REF": "refs/tags/0.1.0"}, {"GITHUB_EVENT_NAME": "push"}):
            with self.subTest(changes=changes):
                with patch.object(release_source, "dispatch_source") as dispatch:
                    with self.assertRaisesRegex(ValueError, "main"):
                        release_source.preflight(self.root, self.repository, self.env(**changes))
                    dispatch.assert_not_called()
        self.available.assert_not_called()

    def test_preflight_missing_main_fails_before_availability(self):
        self.git("push", "-q", "origin", "--delete", "main")
        before = self.state()
        with self.assertRaises(subprocess.CalledProcessError):
            release_source.preflight(self.root, self.repository, self.env())
        self.available.assert_not_called()
        self.assertEqual(before, self.state())

    def test_preflight_nonancestor_fails_before_availability(self):
        self.advance_remote(parent=False)
        before = self.state()
        with self.assertRaises(subprocess.CalledProcessError):
            release_source.preflight(self.root, self.repository, self.env())
        self.available.assert_not_called()
        self.assertEqual(before, self.state())

    def test_malformed_and_mismatched_metadata_fail_before_fetch_or_writes(self):
        relative = "package.json"
        path = self.root / relative
        original = path.read_text()
        for content in ("{", original.replace('"version": "0.1.0"', '"version": "9.9.9"'),
                        original.replace('"version": "0.1.0"', '"version": "v0.1.0"')):
            with self.subTest(content=content[:80]):
                path.write_text(content)
                self.commit("invalid source metadata")
                before = self.state()
                with patch.object(release_source, "fetch_branch") as fetch:
                    with self.assertRaises(ValueError):
                        release_source.preflight(self.root, self.repository, self.env())
                    fetch.assert_not_called()
                self.available.assert_not_called()
                self.assertEqual(before, self.state())
                path.write_text(original)
                self.commit("restore source metadata")

    def test_mismatched_protocol_surface_fails_before_fetch_or_availability(self):
        path = self.root / "tests/test_cli.py"
        original = path.read_text()
        changed = original.replace('"version":"0.1.0"', '"version":"9.9.9"')
        self.assertNotEqual(changed, original)
        path.write_text(changed)
        self.commit("stale protocol assertion")
        before = self.state()
        with patch.object(release_source, "fetch_branch") as fetch:
            with self.assertRaisesRegex(ValueError, "inconsistent"):
                release_source.preflight(self.root, self.repository, self.env())
            fetch.assert_not_called()
        self.available.assert_not_called()
        self.assertEqual(before, self.state())

    def test_preflight_rejects_equal_or_newer_stable_history_including_legacy(self):
        for tag in ("0.1.0", "0.2.0", "v0.1.0", "v2.0.0"):
            with self.subTest(tag=tag):
                self.git("tag", tag)
                before = self.state()
                with self.assertRaisesRegex(ValueError, "exceed stable release history"):
                    release_source.preflight(self.root, self.repository, self.env())
                self.available.assert_not_called()
                self.assertEqual(before, self.state())
                self.git("tag", "-d", tag)

    def test_preflight_ignores_nonstable_history_without_rewriting_tags(self):
        for tag in ("0.0.9", "v0.0.8", "99.0.0-rc.1", "99.0.0+build",
                    "v99.0.0-rc.1", "01.0.0", "20R3.2"):
            self.git("tag", tag)
        before = self.state()
        result = release_source.preflight(self.root, self.repository, self.env())
        self.assertEqual(result["release_tag"], "0.1.0")
        self.assertEqual(before, self.state())
        self.available.assert_called_once()

    def test_original_template_origin_rejected_before_fetch_or_publication(self):
        self.git("remote", "set-url", "origin", "https://github.com/miyako/4d-component-template.git")
        before = self.snapshot(), self.git("rev-parse", "HEAD")
        with patch.object(release_source, "fetch_branch") as fetch, patch.object(
                bump_release, "github_repository", return_value="miyako/4d-component-template"):
            with self.assertRaisesRegex(ValueError, "original template"):
                release_source.preflight(self.root, "miyako/4d-component-template", self.env())
            fetch.assert_not_called()
        self.available.assert_not_called()
        self.assertEqual(before, (self.snapshot(), self.git("rev-parse", "HEAD")))

    def test_preflight_propagates_tag_release_and_api_availability_failures(self):
        before = self.state()
        for message in ("release tag already exists", "GitHub release already exists",
                        "cannot establish release availability"):
            with self.subTest(message=message):
                error = ValueError(message)
                self.available.reset_mock()
                self.available.side_effect = error
                with self.assertRaises(ValueError) as raised:
                    release_source.preflight(self.root, self.repository, self.env())
                self.assertIs(raised.exception, error)
                self.available.assert_called_once_with(self.root, self.repository, "0.1.0")
                self.assertEqual(before, self.state())

    def test_preflight_cli_emits_only_validated_source_sha_and_prefix_free_version(self):
        output = self.workspace / "github-output"
        output.write_text("previous=step\n")
        env = self.env()
        stdout = io.StringIO()
        with patch.dict(os.environ, {**env, "GITHUB_OUTPUT": str(output)}), patch.object(
                sys, "argv", ["release_source.py", "--root", str(self.root),
                              "--repository", self.repository, "preflight"]), redirect_stdout(stdout):
            release_source.main()
        self.assertEqual(json.loads(stdout.getvalue()),
                         {"source_sha": env["GITHUB_SHA"], "release_tag": "0.1.0"})
        self.assertEqual(output.read_text(), "previous=step\nsource_sha=" + env["GITHUB_SHA"]
                         + "\nrelease_tag=0.1.0\n")

    def test_failed_cli_preflight_leaves_outputs_and_source_unchanged(self):
        output = self.workspace / "github-output"
        output.write_text("previous=step\n")
        before = self.state()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.dict(os.environ, {**self.env(GITHUB_SHA="0" * 40), "GITHUB_OUTPUT": str(output)}), patch.object(
                sys, "argv", ["release_source.py", "--root", str(self.root),
                              "--repository", self.repository, "preflight"]), redirect_stdout(
                stdout), redirect_stderr(stderr), self.assertRaises(SystemExit) as raised:
            release_source.main()
        self.assertEqual(raised.exception.code, 2)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn("immutable dispatch SHA", stderr.getvalue())
        self.assertEqual(output.read_text(), "previous=step\n")
        self.assertEqual(before, self.state())
        self.available.assert_not_called()

    def test_bump_cli_commits_source_then_emits_the_new_sha_without_publication(self):
        output = self.workspace / "github-output"
        stdout = io.StringIO()
        with patch.dict(os.environ, {**self.env(), "GITHUB_OUTPUT": str(output)}), patch.object(
                sys, "argv", ["release_source.py", "--root", str(self.root),
                              "--repository", self.repository, "bump", "--mode", "minor"]), redirect_stdout(stdout):
            release_source.main()
        revision = self.git("rev-parse", "HEAD")
        self.assertEqual(json.loads(stdout.getvalue()), {
            "version": "0.2.0", "tag": "0.2.0", "source_sha": revision, "branch": "refs/heads/main"})
        self.assertEqual(output.read_text(), "version=0.2.0\ntag=0.2.0\nsource_sha=" + revision
                         + "\nbranch=refs/heads/main\n")
        self.assertEqual(self.remote_refs(), revision + "\trefs/heads/main")
        self.assertEqual(self.git("tag", "--list"), "")
        self.available.assert_not_called()


if __name__ == "__main__":
    unittest.main()
