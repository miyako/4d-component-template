"""Release refs use real local Git tags; no workflows or releases are invoked."""
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
import ci_config
import release_ref


class ReleaseRefTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / (".release-ref-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        self.git("init", "-q", "--initial-branch=main")
        self.git("config", "user.name", "Release fixture")
        self.git("config", "user.email", "release-fixture@example.invalid")
        self.git("commit", "-q", "--allow-empty", "-m", "first")
        self.sha = self.git("rev-parse", "HEAD")
        self.git("tag", "v0.1.0")

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def resolve(self, **args):
        defaults = {"event": "workflow_dispatch", "version_tag": "v0.1.0"}
        defaults.update(args)
        return release_ref.resolve(self.root, **defaults)

    def test_manual_branch_resolves_existing_tag_not_selected_branch(self):
        self.git("commit", "-q", "--allow-empty", "-m", "branch advanced")
        metadata = self.resolve(ref_type="branch", ref_name="main",
                                event_sha=self.git("rev-parse", "HEAD"))
        self.assertEqual(metadata, {"tag": "v0.1.0", "sha": self.sha})

    def test_push_tag_requires_event_commit(self):
        self.assertEqual(self.resolve(event="push", ref_type="tag", ref_name="v0.1.0",
                                      event_sha=self.sha),
                         {"tag": "v0.1.0", "sha": self.sha})

    def test_push_branch_and_unsupported_events_fail(self):
        for args in ({"event": "push", "ref_type": "branch"},
                     {"event": "pull_request"}, {"event": "workflow_call"}):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.resolve(**args)

    def test_annotated_tag_peels_to_commit(self):
        self.git("tag", "-a", "v0.2.0", "-m", "annotated")
        self.assertNotEqual(self.git("rev-parse", "refs/tags/v0.2.0"), self.sha)
        self.assertEqual(self.resolve(version_tag="v0.2.0")["sha"], self.sha)

    def test_semver_prerelease_and_build_metadata(self):
        tag = "v1.2.3-rc.1+build-4"
        self.git("tag", tag)
        self.assertEqual(self.resolve(version_tag=tag)["sha"], self.sha)

    def test_malformed_and_arbitrary_refs_rejected_before_git(self):
        for tag in ("", "main", "refs/tags/v0.1.0", "v01.2.3", "v1.2",
                    "v1.2.3-01", "v1.2.3\nsha=evil", "v1.2.3^{commit}",
                    "--help", "v1.2.3;echo x", "v١.2.3", None):
            with self.subTest(tag=tag), patch.object(release_ref.subprocess, "run") as run:
                with self.assertRaises(ValueError):
                    self.resolve(version_tag=tag)
                run.assert_not_called()

    def test_missing_tag_fails(self):
        with self.assertRaisesRegex(ValueError, "already exist"):
            self.resolve(version_tag="v9.9.9")

    def test_tag_pointing_at_blob_fails(self):
        (self.root / "blob").write_text("not a commit", encoding="utf-8")
        blob = self.git("hash-object", "-w", "blob")
        self.git("tag", "v0.3.0", blob)
        with self.assertRaisesRegex(ValueError, "point to a commit"):
            self.resolve(version_tag="v0.3.0")

    def test_verify_expected_commit_and_invalid_sha(self):
        self.assertEqual(release_ref.verify(self.root, "v0.1.0", self.sha), self.sha)
        for sha in ("", self.sha[:7], "HEAD", "A" * 40, "f" * 41, None):
            with self.subTest(sha=sha), self.assertRaisesRegex(ValueError, "full normalized"):
                release_ref.verify(self.root, "v0.1.0", sha)

    def test_moved_tag_fails_push_and_publish(self):
        self.git("commit", "-q", "--allow-empty", "-m", "second")
        self.git("tag", "-f", "v0.1.0")
        with self.assertRaisesRegex(ValueError, "moved"):
            release_ref.verify(self.root, "v0.1.0", self.sha)
        with self.assertRaisesRegex(ValueError, "moved"):
            self.resolve(event="push", ref_type="tag", ref_name="v0.1.0",
                         event_sha=self.sha)

    def test_deleted_tag_fails_publish(self):
        self.git("tag", "-d", "v0.1.0")
        with self.assertRaisesRegex(ValueError, "already exist"):
            release_ref.verify(self.root, "v0.1.0", self.sha)

    def test_git_uses_literal_tag_ref_argument_and_rejects_bad_output(self):
        result = subprocess.CompletedProcess([], 0, stdout="not-a-sha\n", stderr="")
        with patch.object(release_ref.subprocess, "run", return_value=result) as run:
            with self.assertRaisesRegex(ValueError, "invalid commit SHA"):
                release_ref.tag_commit(self.root, "v0.1.0")
            self.assertEqual(run.call_args.args[0],
                             ["git", "rev-parse", "--verify", "refs/tags/v0.1.0^{commit}"])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_cli_outputs_only_validated_single_line_metadata(self):
        output = self.root / "github-output"
        output.write_text("previous=step\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/release_ref.py"), "--root", str(self.root),
             "resolve", "--event", "workflow_dispatch", "--version-tag", "v0.1.0"],
            env={**os.environ, "GITHUB_OUTPUT": str(output)}, capture_output=True,
            text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        expected = f"tag=v0.1.0\nsha={self.sha}\n"
        self.assertEqual(result.stdout, expected)
        self.assertEqual(result.stderr, "")
        self.assertEqual(output.read_text(encoding="utf-8"), "previous=step\n" + expected)

    def test_cli_failure_leaves_metadata_unchanged(self):
        output = self.root / "github-output"
        output.write_text("previous=step\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts/release_ref.py"), "--root", str(self.root),
             "resolve", "--event", "workflow_dispatch", "--version-tag", "v9.9.9"],
            env={**os.environ, "GITHUB_OUTPUT": str(output)}, capture_output=True,
            text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("already exist", result.stderr)
        self.assertEqual(output.read_text(encoding="utf-8"), "previous=step\n")

    def test_existing_configuration_validator_checks_version(self):
        config = ci_config.load_config(ROOT)
        self.assertEqual(ci_config.load_config(ROOT, tag="v" + config["version"]), config)
        with self.assertRaisesRegex(ValueError, "template.json version"):
            ci_config.load_config(ROOT, tag="v999999.0.0")

    def test_only_ci_and_publish_with_main_only_version_and_exact_sha_builds(self):
        ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        release = (ROOT / ".github/workflows/publish.yml").read_text(encoding="utf-8")
        self.assertEqual(sorted(path.name for path in (ROOT / ".github/workflows").iterdir()),
                         ["ci.yml", "publish.yml"])
        self.assertTrue(ci.startswith("name: CI\n"))
        self.assertTrue(release.startswith("name: Publish\n"))
        self.assertIn("branches: ['**']", ci)
        self.assertNotIn("  push:", release)
        self.assertNotIn("version_tag:", release)
        self.assertIn("options: [patch, minor, major]", release)
        self.assertIn("default: patch", release)
        self.assertIn("group: publish\n  cancel-in-progress: false", release)
        self.assertIn("if: github.ref != 'refs/heads/main'", release)
        self.assertIn("ref: main", release)
        self.assertIn("bump_release.py apply", release)
        self.assertIn("--stage", release)
        self.assertIn("git push origin HEAD:refs/heads/main", release)
        self.assertLess(release.index("release_ref.py available"), release.index("git commit"))
        self.assertEqual(release.count("contents: write"), 2)
        self.assertEqual(ci.count("uses: actions/checkout@v4"), 3)
        self.assertEqual(ci.count("ref: ${{ inputs.source_sha || github.sha }}"), 3)
        self.assertEqual(ci.count("&& !inputs.release_call"), 4)
        self.assertIn("workflow_dispatch:", ci)
        self.assertIn("workflow_dispatch:", release)
        self.assertIn("fetch-depth: 0", release)
        self.assertIn("source_sha: ${{ needs.version.outputs.source_sha }}", release)
        self.assertIn("release_call: true", release)
        self.assertEqual(release.count("ref: ${{ needs.version.outputs.source_sha }}"), 2)
        self.assertEqual(release.count('validate --release --tag "$RELEASE_TAG"'), 2)
        self.assertIn('--tool4d .tools/tool4d.app/Contents/MacOS/tool4d --tag "$RELEASE_TAG"', release)
        self.assertIn("--create-tag --publish", release)
        self.assertNotIn("git tag ", release)
        self.assertIn("--verify-tag", (ROOT / "scripts/release_assets.py").read_text())

    def test_main_guard_rejects_nonmanual_and_nonmain_runs(self):
        release_ref.require_main({"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"})
        for event, ref in (("push", "refs/heads/main"), ("workflow_dispatch", "refs/heads/feature"),
                           ("workflow_dispatch", "refs/tags/v0.1.0"), ("", "")):
            with self.subTest(event=event, ref=ref), self.assertRaisesRegex(ValueError, "on main"):
                release_ref.require_main({"GITHUB_EVENT_NAME": event, "GITHUB_REF": ref})

    def test_availability_requires_explicit_404_for_both_remote_resources(self):
        missing = subprocess.CompletedProcess([], 1, "HTTP/2.0 404 Not Found\n\n{}", "")
        with patch.object(release_ref, "load_config") as config, patch.object(
                release_ref.subprocess, "run", return_value=missing) as run:
            release_ref.available(self.root, "owner/Destination", "v0.1.0")
            config.assert_called_once_with(self.root, initialized=True,
                                           repository="owner/Destination", tag="v0.1.0")
            self.assertEqual(run.call_count, 2)
            self.assertEqual(run.call_args.args[0][-1],
                             "repos/owner/Destination/releases/tags/v0.1.0")

    def test_tag_release_collision_and_unknown_api_failures_stop(self):
        for result in (
                subprocess.CompletedProcess([], 0, "HTTP/2.0 200 OK\n\n{}", ""),
                subprocess.CompletedProcess([], 1, "HTTP/2.0 403 Forbidden\n", "permission denied"),
                subprocess.CompletedProcess([], 1, "", "network unavailable"),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "HTTP/2.0 404 Not Found\n", "")):
            with self.subTest(result=result), patch.object(release_ref, "load_config"), patch.object(
                    release_ref.subprocess, "run", return_value=result) as run:
                with self.assertRaises(ValueError):
                    release_ref.available(self.root, "owner/Destination", "v0.1.0")
                self.assertEqual(run.call_count, 1)

    def test_existing_release_without_tag_still_blocks_creation(self):
        responses = [
            subprocess.CompletedProcess([], 1, "HTTP/2.0 404 Not Found\n", ""),
            subprocess.CompletedProcess([], 0, "HTTP/2.0 200 OK\n", "")]
        with patch.object(release_ref, "load_config"), patch.object(
                release_ref.subprocess, "run", side_effect=responses):
            with self.assertRaisesRegex(ValueError, "already exists"):
                release_ref.available(self.root, "owner/Destination", "v0.1.0")

    def test_invalid_candidate_or_nonmain_dispatch_never_creates_tag(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}
        with patch.dict(os.environ, env), patch.object(release_ref, "available") as available:
            for revision in ("", "HEAD", self.sha[:7], None):
                with self.subTest(revision=revision), self.assertRaisesRegex(ValueError, "normalized"):
                    release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", revision)
            available.assert_not_called()
        with patch.dict(os.environ, {**env, "GITHUB_REF": "refs/heads/feature"}), patch.object(
                release_ref, "available") as available:
            with self.assertRaisesRegex(ValueError, "on main"):
                release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", self.sha)
            available.assert_not_called()

    def test_remote_tag_mismatch_fails_before_success(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}
        remote = subprocess.CompletedProcess([], 0, "b" * 40 + "\trefs/tags/v0.2.0\n", "")
        with patch.dict(os.environ, env), patch.object(release_ref, "available"), patch.object(
                release_ref.subprocess, "run", return_value=remote), patch.object(
                release_ref, "verify") as verify:
            with self.assertRaisesRegex(ValueError, "remote release tag"):
                release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", self.sha)
            verify.assert_not_called()

    def test_create_tag_requires_main_ancestry_and_atomic_creation_before_remote_verification(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}
        remote = subprocess.CompletedProcess([], 0, self.sha + "\trefs/tags/v0.2.0\n", "")
        with patch.dict(os.environ, env), patch.object(release_ref, "available") as available, patch.object(
                release_ref.subprocess, "run", return_value=remote) as run, patch.object(
                release_ref, "verify") as verify:
            release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", self.sha)
        available.assert_called_once_with(self.root, "owner/Destination", "v0.2.0")
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[1], ["git", "merge-base", "--is-ancestor", self.sha,
                                       "refs/remotes/origin/main"])
        self.assertEqual(commands[2], ["gh", "api", "--method", "POST",
                                       "repos/owner/Destination/git/refs",
                                       "-f", "ref=refs/tags/v0.2.0", "-f", "sha=" + self.sha])
        self.assertEqual(commands[3], ["git", "fetch", "--no-tags", "origin",
                                       "refs/tags/v0.2.0:refs/tags/v0.2.0"])
        verify.assert_called_once_with(self.root, "v0.2.0", self.sha)

    def test_creation_stops_if_main_no_longer_contains_candidate_or_tag_collides(self):
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}
        for fail_index in (1, 2):
            responses = [subprocess.CompletedProcess([], 0, "", "")] * fail_index + [
                subprocess.CalledProcessError(1, ["git"])]
            with self.subTest(fail_index=fail_index), patch.dict(os.environ, env), patch.object(
                    release_ref, "available"), patch.object(
                    release_ref.subprocess, "run", side_effect=responses) as run:
                with self.assertRaises(subprocess.CalledProcessError):
                    release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", self.sha)
                self.assertEqual(run.call_count, fail_index + 1)

    def test_real_git_tag_points_at_accepted_commit_even_if_main_advances(self):
        remote = self.root / "fixture-origin.git"
        self.git("init", "-q", "--bare", str(remote))
        self.git("remote", "add", "origin", str(remote))
        self.git("commit", "-q", "--allow-empty", "-m", "main advanced")
        self.git("push", "-q", "origin", "HEAD:refs/heads/main")
        self.git("checkout", "-q", "--detach", self.sha)
        env = {"GITHUB_EVENT_NAME": "workflow_dispatch", "GITHUB_REF": "refs/heads/main"}
        run = subprocess.run

        def fake_api(arguments, **kwargs):
            if arguments[0] == "gh":
                return run(["git", "--git-dir", str(remote), "update-ref",
                            "refs/tags/v0.2.0", self.sha, "0" * 40], **kwargs)
            return run(arguments, **kwargs)

        with patch.dict(os.environ, env), patch.object(release_ref, "available"), patch.object(
                release_ref.subprocess, "run", side_effect=fake_api):
            release_ref.create_tag(self.root, "owner/Destination", "v0.2.0", self.sha)
        self.assertEqual(self.git("ls-remote", "origin", "refs/tags/v0.2.0"),
                         self.sha + "\trefs/tags/v0.2.0")
        self.assertNotEqual(self.git("rev-parse", "origin/main"), self.sha)


if __name__ == "__main__":
    unittest.main()
