"""Apple release regressions use synthetic files and mocked vendor tools only."""
import base64
import contextlib
import io
import json
import os
from pathlib import Path
import plistlib
import shutil
import stat
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import sign_release as signing
import package_component
import test_delivery as delivery


SUBMISSION = "12345678-1234-4321-8765-123456789abc"


class FakeTools:
    def __init__(self, secrets):
        self.secrets = secrets
        self.calls = []
        self.fail = None
        self.status = "Accepted"
        self.identifier = SUBMISSION
        self.payload = None
        self.mount = None
        self.display_team = secrets["NOTARYTOOL_TEAM_ID"]
        self.runtime = True
        self.timestamp = True
        self.immutable_change = False
        self.mutate_mount = False
        self.malformed_mount = False
        self.cleanup_fail = set()
        self.head = "a" * 40

    def run(self, args, **kwargs):
        self.calls.append(list(args))
        assert kwargs["stdin"] == subprocess.DEVNULL
        assert kwargs["stdout"] == subprocess.PIPE
        assert kwargs["stderr"] == subprocess.PIPE
        assert kwargs["check"] is False
        assert not set(signing.SECRET_NAMES) & set(kwargs["env"])
        assert kwargs["env"]["PATH"] == "/usr/bin:/bin:/usr/sbin:/sbin"
        action = args[1]
        out = ""
        err = ""
        if self.fail and self.fail(args):
            return subprocess.CompletedProcess(args, 9, "\n".join(self.secrets.values()),
                                               "diagnostic " + " ".join(self.secrets.values()))
        if action in self.cleanup_fail or (
                "restore" in self.cleanup_fail and action == "list-keychains" and "-s" in args
                and any("login" in str(arg) for arg in args)):
            return subprocess.CompletedProcess(args, 7, "", "cleanup failed")
        if args[0] == signing.GIT:
            assert args == [signing.GIT, "rev-parse", "HEAD"]
            assert kwargs["cwd"] is not None
            out = self.head + "\n"
        elif args[0] == signing.SECURITY:
            if action == "list-keychains" and "-s" not in args:
                out = '    "/Users/runner/Library/Keychains/login.keychain-db"\n    "/a spaced keychain"\n'
            elif action == "create-keychain":
                Path(args[-1]).write_bytes(b"keychain")
            elif action == "delete-keychain":
                Path(args[-1]).unlink(missing_ok=True)
            elif action == "import":
                certificate = Path(args[2])
                assert stat.S_IMODE(certificate.stat().st_mode) == 0o600
                assert certificate.read_bytes() == b"synthetic not-a-real-p12"
        elif args[0] == signing.CODESIGN:
            path = Path(args[-1])
            if action == "--force":
                path.write_bytes(path.read_bytes() + b"signature")
                if self.immutable_change and path.suffix != ".dmg":
                    (path.parents[3] / "Resources/bin/Windows/uuid-test.exe").write_bytes(b"changed")
            elif action == "--display":
                out = ""
                err = ("Authority=Developer ID Application: Private Identity\n"
                       "TeamIdentifier=" + self.display_team + "\n"
                       "CodeDirectory v=20500 size=123 flags=0x10000("
                       + ("runtime" if self.runtime else "none") + ")\n"
                       + ("Timestamp=Nov 1, 2026\n" if self.timestamp else ""))
        elif args[0] == signing.HDIUTIL:
            if action == "create":
                self.payload = Path(args[args.index("-srcfolder") + 1])
                assert [path.name for path in self.payload.iterdir()] == ["UuidTest.4dbase"]
                Path(args[-1]).write_bytes(b"synthetic DMG")
            elif action == "attach":
                self.mount = Path(args[args.index("-mountpoint") + 1])
                shutil.copytree(self.payload / "UuidTest.4dbase", self.mount / "UuidTest.4dbase")
                if self.mutate_mount:
                    (self.mount / "UuidTest.4dbase/Resources/bin/Windows/uuid-test.exe").write_bytes(b"tampered")
                report = [] if self.malformed_mount else {"system-entities": [{"mount-point": str(self.mount)}]}
                out = plistlib.dumps(report).decode()
            elif action == "detach":
                if self.mount is None or not (self.mount / "UuidTest.4dbase").exists():
                    return subprocess.CompletedProcess(args, 1, "", "not mounted")
                shutil.rmtree(self.mount / "UuidTest.4dbase")
        elif args[0] == signing.XCRUN:
            if args[1:3] == ["notarytool", "submit"]:
                assert kwargs["timeout"] == 1860
                out = json.dumps({"id": self.identifier, "status": self.status})
            elif args[1:3] == ["notarytool", "log"]:
                out = json.dumps({"issues": [{
                    "severity": "error", "path": "UuidTest/secret/" + self.secrets["NOTARYTOOL_APPLE_ID"],
                    "message": "bad signature " + self.secrets["NOTARYTOOL_PASSWORD"],
                    "code": 4000, "private": "not for publication",
                }]})
            elif args[1:3] == ["stapler", "staple"]:
                path = Path(args[-1])
                path.write_bytes(path.read_bytes() + b"ticket")
        return subprocess.CompletedProcess(args, 0, out, err)


class SigningTests(unittest.TestCase):
    def setUp(self):
        fixture = delivery.DeliveryTests("test_matrix_only_selected_language")
        fixture.setUp()
        self.addCleanup(fixture.doCleanups)
        self.root = fixture.root
        old = fixture.component
        component = old.with_name("UuidTest")
        old.rename(component)
        (component / "Project/example-component.4DProject").rename(component / "Project/UuidTest.4DProject")
        (component / "Resources/bin/macOS/example-cli").rename(component / "Resources/bin/macOS/uuid-test")
        (component / "Resources/bin/Windows/example-cli.exe").rename(component / "Resources/bin/Windows/uuid-test.exe")
        (component / "Project/Sources/settings.4DSettings").write_text(
            '<preferences><com.4d><general component_classStore_name="UuidTest"/></com.4d></preferences>')
        (component / "Project/Sources/catalog.4DCatalog").write_text('<base name="UuidTest"/>')
        fixture.config.update(repository="UuidTest", namespace="UuidTest", cli="uuid-test")
        fixture.component = component
        fixture.project = component / "Project/UuidTest.4DProject"
        fixture.status["project"] = fixture.project.relative_to(self.root).as_posix()
        fixture.write_config()
        library = component / "Libraries/lib4d-arm64.dylib"
        library.write_bytes(delivery.synthetic_universal()[80:112])
        fixture.write_status()
        self.fixture = fixture
        self.policy = self.root / "release-policy.json"
        self.policy.write_text('{"schema":1,"apple_notarized_versions":["0.1.0"]}')
        self.unsigned = package_component.package(
            self.root, repository="miyako/UuidTest", tag="v0.1.0")
        self.original_zip = self.unsigned.read_bytes()
        self.source_snapshot = signing.snapshot(component)
        self.env = {
            name: "synthetic-sensitive-" + str(index) + "-value"
            for index, name in enumerate(signing.SECRET_NAMES)
        }
        self.env["APPLE_DEVELOPER_ID_CERTIFICATE"] = base64.b64encode(
            b"synthetic not-a-real-p12").decode()
        self.env.update(GITHUB_ACTIONS="true", GITHUB_REPOSITORY="miyako/UuidTest",
                        GITHUB_REF_NAME="v0.1.0", GITHUB_SHA="a" * 40)
        self.secrets = {name: self.env[name] for name in signing.SECRET_NAMES}
        self.tools = FakeTools(self.secrets)

    def sign(self, *, require_apple_signing=False):
        with patch.object(signing.platform, "system", return_value="Darwin"), \
                patch.object(signing.subprocess, "run", side_effect=self.tools.run), \
                contextlib.redirect_stdout(io.StringIO()):
            return signing.sign_release(self.root, self.env, require_apple_signing=require_apple_signing)

    def assert_clean(self):
        self.assertEqual(list((self.root / "build").glob("apple-signing-*")), [])
        self.assertEqual(signing.snapshot(self.fixture.component), self.source_snapshot)
        self.assertEqual(self.unsigned.read_bytes(), self.original_zip)
        self.assertFalse((self.root / "dist/UuidTest.dmg").exists())
        self.assertFalse((self.root / "dist/UuidTest-signing.json").exists())

    def assert_no_leak(self, text):
        for value in self.secrets.values():
            self.assertNotIn(value, text)

    def test_policy_absent_unsigned_current_opt_in_and_other_version(self):
        output = self.root / "github-output"
        for policy, expected in ((None, False), (["0.1.0"], True), (["0.2.0"], False)):
            if policy is None:
                self.policy.unlink()
            else:
                self.policy.write_text(json.dumps({"schema": 1, "apple_notarized_versions": policy}))
            with patch.object(signing.platform, "system", return_value="Linux"), \
                    contextlib.redirect_stdout(io.StringIO()) as text:
                self.assertEqual(signing.policy_command(self.root, {"GITHUB_OUTPUT": str(output)}), expected)
            self.assertEqual(text.getvalue().strip(), "apple-notarized" if expected else "unsigned")
        self.assertEqual(output.read_text(), "apple_signing=false\napple_signing=true\napple_signing=false\n")

    def test_malformed_policy_fails(self):
        for policy in ("{", "[]", '{"schema":true,"apple_notarized_versions":[]}',
                       '{"schema":2,"apple_notarized_versions":[]}',
                       '{"schema":1,"apple_notarized_versions":"0.1.0"}',
                       '{"schema":1,"apple_notarized_versions":[null]}',
                       '{"schema":1,"apple_notarized_versions":["01.1.0"]}',
                       '{"schema":1,"apple_notarized_versions":["0.1.0","0.1.0"]}',
                       '{"schema":1,"apple_notarized_versions":[],"extra":1}'):
            self.policy.write_text(policy)
            with self.subTest(policy=policy), self.assertRaises(ValueError):
                signing.release_policy(self.root)

    def test_explicit_signing_upgrades_absent_policy_and_cannot_downgrade(self):
        self.policy.unlink()
        output = self.root / "github-output"
        with contextlib.redirect_stdout(io.StringIO()) as text:
            self.assertTrue(signing.policy_command(
                self.root, {"GITHUB_OUTPUT": str(output)}, require_apple_signing=True))
        self.assertEqual(text.getvalue().strip(), "apple-notarized")
        self.assertEqual(output.read_text(), "apple_signing=true\n")
        proof = self.sign(require_apple_signing=True)
        self.assertEqual(proof["notarization"]["status"], "Accepted")
        self.policy.write_text('{"schema":1,"apple_notarized_versions":["0.1.0"]}')
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertTrue(signing.policy_command(self.root, {}, require_apple_signing=False))
        self.policy.write_text("malformed")
        with self.assertRaises(ValueError):
            signing.policy_command(self.root, {}, require_apple_signing=True)

    def test_manual_release_identity_overrides_workflow_branch_and_checks_head(self):
        self.env.update(GITHUB_REF_NAME="main", GITHUB_SHA="b" * 40,
                        RELEASE_TAG="v0.1.0", RELEASE_SHA="a" * 40)
        proof = self.sign(require_apple_signing=True)
        self.assertEqual(proof["sourceSHA"], "a" * 40)
        self.assertEqual(proof["releaseTag"], "v0.1.0")
        self.assertEqual(self.tools.calls[0], [signing.GIT, "rev-parse", "HEAD"])

    def test_resolved_source_commit_mismatch_fails_before_keychain_use(self):
        self.env.update(RELEASE_TAG="v0.1.0", RELEASE_SHA="b" * 40)
        with self.assertRaisesRegex(ValueError, "source HEAD does not match"):
            self.sign(require_apple_signing=True)
        self.assertEqual(self.tools.calls, [[signing.GIT, "rev-parse", "HEAD"]])
        self.assert_clean()

    def test_policy_cli_accepts_explicit_flag(self):
        self.policy.unlink()
        with patch.dict(os.environ, {}, clear=True), contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(signing.main(
                ["policy", "--require-apple-signing", "--root", str(self.root)]), 0)
        self.assertEqual(output.getvalue().strip(), "apple-notarized")

    def test_preflight_platform_actions_identity_policy_and_commit(self):
        with patch.object(signing.platform, "system", return_value="Linux"), \
                self.assertRaisesRegex(signing.SigningError, "macOS GitHub Actions"):
            signing.sign_release(self.root, self.env)
        for updates, message in (({"GITHUB_ACTIONS": "false"}, "GitHub Actions"),
                                 ({"GITHUB_REPOSITORY": ""}, "actual"),
                                 ({"GITHUB_REPOSITORY": "miyako/Wrong"}, "actual repository"),
                                 ({"GITHUB_REF_NAME": "main"}, "release tag"),
                                 ({"GITHUB_SHA": ""}, "source commit")):
            with self.subTest(updates=updates), patch.dict(self.env, updates), \
                    self.assertRaisesRegex(ValueError, message):
                self.sign()
        self.policy.unlink()
        with self.assertRaisesRegex(ValueError, "not opted in"):
            self.sign()
        self.assertEqual(self.tools.calls, [])
        self.assert_clean()

    def test_missing_credentials_lists_all_names_without_values(self):
        with self.assertRaises(signing.SigningError) as caught:
            signing.credentials({})
        for name in signing.SECRET_NAMES:
            self.assertIn(name, str(caught.exception))
        for name in signing.SECRET_NAMES:
            with self.subTest(name=name), patch.dict(self.env, {name: " \n"}), \
                    self.assertRaisesRegex(ValueError, name) as caught:
                self.sign()
            self.assert_no_leak(str(caught.exception))
        self.assert_clean()

    def test_invalid_base64_empty_and_adhoc_refused_without_tools(self):
        for updates, message in (({"APPLE_DEVELOPER_ID_CERTIFICATE": "%%%bad"}, "invalid base64"),
                                 ({"APPLE_DEVELOPER_ID_CERTIFICATE": "===="}, "invalid base64"),
                                 ({"CODESIGN_APPLE_ID": " - "}, "ad-hoc")):
            with patch.dict(self.env, updates), self.assertRaisesRegex(ValueError, message):
                self.sign()
        self.assertEqual(self.tools.calls, [])
        whitespace = dict(self.secrets)
        whitespace["APPLE_DEVELOPER_ID_CERTIFICATE"] = " \n".join(
            self.secrets["APPLE_DEVELOPER_ID_CERTIFICATE"][i:i + 4]
            for i in range(0, len(self.secrets["APPLE_DEVELOPER_ID_CERTIFICATE"]), 4))
        self.assertEqual(signing.certificate_bytes(whitespace), b"synthetic not-a-real-p12")

    def test_command_error_redacts_every_value_and_does_not_echo_argv(self):
        self.tools.fail = lambda args: True
        commands = signing.Commands(self.env, self.secrets)
        with patch.object(signing.subprocess, "run", side_effect=self.tools.run), \
                self.assertRaisesRegex(ValueError, "explicit label: exit 9") as caught:
            commands.run("explicit label", [signing.SECURITY, "import"])
        self.assert_no_leak(str(caught.exception))
        self.assertIn("[REDACTED]", str(caught.exception))
        for error in (subprocess.TimeoutExpired(["secret-argv"], 30),
                      OSError("private path " + self.secrets["NOTARYTOOL_PASSWORD"])):
            with patch.object(signing.subprocess, "run", side_effect=error), \
                    self.assertRaises(ValueError) as caught:
                commands.run("launch", [signing.XCRUN, "notarytool"])
            self.assert_no_leak(str(caught.exception))
            self.assertNotIn("secret-argv", str(caught.exception))

    def test_redacts_json_escaped_credentials_in_rejection_diagnostics(self):
        secret = 'synthetic "password" \\ newline\n日本語'
        secrets = {"NOTARYTOOL_PASSWORD": secret}
        for value in (secret, json.dumps(secret, ensure_ascii=True)[1:-1],
                      json.dumps(secret, ensure_ascii=False)[1:-1]):
            self.assertEqual(signing.redact("diagnostic: " + value, secrets),
                             "diagnostic: [REDACTED]")

    def test_cleanup_import_sign_submit_and_verification_failures(self):
        failures = {
            "import": lambda args: args[1] == "import",
            "sign": lambda args: args[1] == "--force",
            "notary": lambda args: args[1:3] == ["notarytool", "submit"],
            "verify": lambda args: args[1] == "--verify",
        }
        for name, predicate in failures.items():
            self.tools = FakeTools(self.secrets)
            self.tools.fail = predicate
            with self.subTest(stage=name), self.assertRaises(ValueError) as caught:
                self.sign()
            self.assert_no_leak(str(caught.exception))
            self.assertTrue(any(args[1] == "delete-keychain" for args in self.tools.calls))
            if name != "import":
                restores = [args for args in self.tools.calls if args[1] == "list-keychains" and "-s" in args]
                self.assertEqual(restores[-1][-2:], [
                    "/Users/runner/Library/Keychains/login.keychain-db", "/a spaced keychain"])
            self.assert_clean()

    def test_cleanup_failure_is_fatal_and_preserves_primary_error(self):
        self.tools.fail = lambda args: args[1] == "--force"
        self.tools.cleanup_fail = {"restore", "delete-keychain"}
        with self.assertRaises(ValueError) as caught:
            self.sign()
        text = str(caught.exception)
        self.assertIn("codesign sign: exit 9", text)
        self.assertIn("keychain restore: exit 7", text)
        self.assertIn("keychain delete: exit 7", text)
        self.assert_no_leak(text)
        self.assert_clean()

    def test_cleanup_failure_after_otherwise_success_never_delivers(self):
        for action in ("restore", "delete-keychain"):
            self.tools = FakeTools(self.secrets)
            self.tools.cleanup_fail = {action}
            with self.subTest(action=action), self.assertRaisesRegex(ValueError, "cleanup failed"):
                self.sign()
            self.assert_clean()

    def test_create_failure_attempts_keychain_deletion_and_searchlist_restore(self):
        self.tools.fail = lambda args: args[1] == "create-keychain"
        with self.assertRaisesRegex(ValueError, "keychain create"):
            self.sign()
        self.assertTrue(any(args[1] == "delete-keychain" for args in self.tools.calls))
        self.assertTrue(any(args[1] == "list-keychains" and "-s" in args for args in self.tools.calls))
        self.assert_clean()

    def test_stapling_mount_and_mounted_data_failures_always_cleanup(self):
        for stage, predicate in (
                ("staple", lambda args: args[1:3] == ["stapler", "staple"]),
                ("validate", lambda args: args[1:3] == ["stapler", "validate"]),
                ("attach", lambda args: args[1] == "attach")):
            self.tools = FakeTools(self.secrets)
            self.tools.fail = predicate
            with self.subTest(stage=stage), self.assertRaises(ValueError):
                self.sign()
            self.assert_clean()
        for attribute, message in (("mutate_mount", "immutable"), ("malformed_mount", "malformed mount")):
            self.tools = FakeTools(self.secrets)
            setattr(self.tools, attribute, True)
            with self.subTest(attribute=attribute), self.assertRaisesRegex(ValueError, message):
                self.sign()
            self.assertTrue(any(args[1] == "detach" for args in self.tools.calls))
            self.assert_clean()

    def test_signer_cannot_change_windows_data(self):
        self.tools.immutable_change = True
        # Change occurs only on the CLI's signing operation, before any library.
        original_run = self.tools.run
        def run(args, **kwargs):
            if args[-1].endswith(".dylib"):
                self.tools.immutable_change = False
            return original_run(args, **kwargs)
        with patch.object(self.tools, "run", side_effect=run), \
                self.assertRaisesRegex(ValueError, "immutable package"):
            self.sign()
        self.assert_clean()

    def test_workspace_cleanup_error_does_not_mask_primary_or_deliver(self):
        original_cleanup = signing.tempfile.TemporaryDirectory.cleanup
        def cleanup(temporary):
            original_cleanup(temporary)
            raise OSError("synthetic workspace removal failure")
        with patch.object(signing.tempfile.TemporaryDirectory, "cleanup", cleanup), \
                self.assertRaisesRegex(ValueError, "workspace cleanup"):
            self.sign()
        self.assert_clean()
        self.tools = FakeTools(self.secrets)
        self.tools.fail = lambda args: args[1] == "import"
        with patch.object(signing.tempfile.TemporaryDirectory, "cleanup", cleanup), \
                self.assertRaises(ValueError) as caught:
            self.sign()
        self.assertIn("certificate import", str(caught.exception))
        self.assertIn("workspace cleanup", str(caught.exception))
        self.assert_no_leak(str(caught.exception))
        self.assert_clean()

    def test_nonaccepted_exit_zero_and_sanitized_rejection_issues(self):
        for status in ("Invalid", "Rejected", "In Progress", "accepted", None):
            self.tools = FakeTools(self.secrets)
            self.tools.status = status
            with self.subTest(status=status), self.assertRaisesRegex(ValueError, "not Accepted") as caught:
                self.sign()
            text = str(caught.exception)
            self.assert_no_leak(text)
            self.assertIn('"severity": "error"', text)
            self.assertIn('"code": 4000', text)
            self.assertIn('"path":', text)
            self.assertIn('"message":', text)
            self.assertNotIn("not for publication", text)
            self.assertFalse(any(args[1:3] == ["stapler", "staple"] for args in self.tools.calls))
            self.assert_clean()

    def test_notary_submission_uuid_must_be_valid(self):
        for identifier in (None, "not-a-uuid", "12345678123443218765123456789abc"):
            self.tools.identifier = identifier
            with self.subTest(identifier=identifier), self.assertRaisesRegex(ValueError, "submission UUID"):
                self.sign()
            self.assert_clean()

    def test_notary_nonzero_rejection_retrieves_log_and_nonzero_accepted_fails(self):
        original_run = self.tools.run
        def run(args, **kwargs):
            result = original_run(args, **kwargs)
            if args[1:3] == ["notarytool", "submit"]:
                result.returncode = 65
            return result
        with patch.object(self.tools, "run", side_effect=run):
            self.tools.status = "Invalid"
            with self.assertRaises(ValueError) as caught:
                self.sign()
            text = str(caught.exception)
            self.assertIn("notarytool submit: exit 65", text)
            self.assertIn('"code": 4000', text)
            self.assert_no_leak(text)
            self.assert_clean()
            self.tools.status = "Accepted"
            with self.assertRaisesRegex(ValueError, "exit 65"):
                self.sign()
            self.assert_clean()

    def test_required_signature_team_runtime_and_timestamp(self):
        for field, value in (("display_team", "WRONG"), ("runtime", False), ("timestamp", False)):
            self.tools = FakeTools(self.secrets)
            setattr(self.tools, field, value)
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "signature display"):
                self.sign()
            self.assert_clean()

    def test_fail_closed_on_stale_compile_or_unsigned_archive_tampering(self):
        self.fixture.status["input_sha256"] = "bad"
        self.fixture.marker.write_text(json.dumps(self.fixture.status))
        with self.assertRaisesRegex(ValueError, "recompile"):
            self.sign()
        self.fixture.write_status()
        with zipfile.ZipFile(self.unsigned, "a") as packed:
            packed.writestr("UuidTest.4dbase/Resources/extra", b"unbound")
        with self.assertRaisesRegex(ValueError, "unsigned ZIP does not match"):
            self.sign()
        self.assertEqual(self.tools.calls, [[signing.GIT, "rev-parse", "HEAD"]])

    def test_snapshot_checks_windows_docs_layout_and_permissions(self):
        before = {"a": (b"old", 0o755), "b": (b"stable", 0o644), "dir": (None, 0o755)}
        signing.assert_immutable(before, dict(before, a=(b"signed", 0o755)), ["a"])
        for after in (dict(before, a=(b"signed", 0o644)), dict(before, b=(b"changed", 0o644)),
                      dict(before, extra=(b"x", 0o644))):
            with self.assertRaisesRegex(ValueError, "changed"):
                signing.assert_immutable(before, after, ["a"])

    def test_final_zip_from_mounted_container_and_minimal_signing_order(self):
        with patch.object(signing, "snapshot", wraps=signing.snapshot) as snapshots:
            proof = self.sign()
        self.assertTrue(any("mount/UuidTest.4dbase" in str(call.args[0]) for call in snapshots.call_args_list))
        calls = self.tools.calls
        imported = next(args for args in calls if args[1] == "import")
        self.assertIn("-T", imported)
        self.assertEqual(imported[imported.index("-T") + 1], signing.CODESIGN)
        self.assertNotIn("-A", imported)
        acl = next(args for args in calls if args[1] == "set-key-partition-list")
        self.assertEqual(acl[acl.index("-S") + 1], "apple-tool:,apple:,codesign:")
        searches = [args for args in calls if args[1] == "list-keychains"]
        self.assertEqual(len(searches), 3)
        self.assertEqual(len(searches[1][searches[1].index("-s") + 1:]), 1)
        self.assertFalse(any(args[1] == "default-keychain" for args in calls))
        signed = [args for args in calls if args[0] == signing.CODESIGN and args[1] == "--force"]
        self.assertEqual(len(signed), 3)
        for args in signed:
            self.assertIn("--timestamp", args)
            self.assertIn("--keychain", args)
            self.assertIn("--identifier", args)
            self.assertNotIn("--entitlements", args)
            self.assertNotIn("--deep", args)
            if not args[-1].endswith(".dmg"):
                self.assertEqual(args[args.index("--options") + 1], "runtime")
            else:
                self.assertNotIn("--options", args)
        verify = [args for args in calls if args[1] == "--verify"]
        self.assertTrue(all("--strict" in args and "--all-architectures" in args for args in verify))
        submit_index = next(i for i, args in enumerate(calls) if args[1:3] == ["notarytool", "submit"])
        staple_index = next(i for i, args in enumerate(calls) if args[1:3] == ["stapler", "staple"])
        validate_index = next(i for i, args in enumerate(calls) if args[1:3] == ["stapler", "validate"])
        attach_index = next(i for i, args in enumerate(calls) if args[1] == "attach")
        detach_index = next(i for i, args in enumerate(calls) if args[1] == "detach")
        delete_index = next(i for i, args in enumerate(calls) if args[1] == "delete-keychain")
        self.assertLess(submit_index, staple_index)
        self.assertLess(staple_index, validate_index)
        self.assertLess(validate_index, attach_index)
        self.assertLess(attach_index, detach_index)
        self.assertLess(detach_index, delete_index)
        self.assertTrue(all(args[-1].endswith(".dmg") for args in calls if args[1] == "stapler"))
        attach = calls[attach_index]
        self.assertIn("-readonly", attach)
        self.assertIn("-nobrowse", attach)
        self.assertIn("-plist", attach)
        self.assertEqual(signing.snapshot(self.fixture.component), self.source_snapshot)
        self.assertEqual(list((self.root / "build").glob("apple-signing-*")), [])
        self.assertEqual(proof["notarization"], {"status": "Accepted", "submissionUUID": SUBMISSION})
        self.assertEqual(proof["hostValidation"], "required-after-signing")
        self.assertTrue(proof["zip"]["notarizedViaDMG"])
        self.assertFalse(proof["zip"]["stapled"])
        self.assert_no_leak(json.dumps(proof))
        self.assertNotIn("Private Identity", json.dumps(proof))
        self.assertEqual(proof["zip"]["sha256"], signing.sha256(self.unsigned))
        self.assertEqual(proof["dmg"]["sha256"], signing.sha256(self.root / "dist/UuidTest.dmg"))
        with zipfile.ZipFile(self.unsigned) as packed:
            self.assertIn("UuidTest.4dbase/", packed.namelist())
            self.assertIn("UuidTest.4dbase/Resources/bin/macOS/", packed.namelist())
            cli = packed.getinfo("UuidTest.4dbase/Resources/bin/macOS/uuid-test")
            self.assertEqual((cli.external_attr >> 16) & 0o777, 0o755)
            self.assertEqual(packed.read("UuidTest.4dbase/Resources/bin/Windows/uuid-test.exe"),
                             delivery.synthetic_pe())
            nested = packed.read("UuidTest.4dbase/UuidTest.4DZ")
            with zipfile.ZipFile(io.BytesIO(self.original_zip)) as old:
                self.assertEqual(nested, old.read("UuidTest.4dbase/UuidTest.4DZ"))
            with zipfile.ZipFile(io.BytesIO(nested)) as project:
                self.assertIn("Project/UuidTest.4DProject", project.namelist())
                self.assertFalse(any(name.lower().endswith(".4dm") for name in project.namelist()))
        self.assertEqual(json.loads((self.root / "dist/UuidTest-signing.json").read_text()), proof)

    def test_detach_force_retry_and_failure_report(self):
        commands = signing.Commands(self.env, self.secrets)
        with patch.object(commands, "run", side_effect=[signing.SigningError("busy"), ("", "")]) as run:
            self.assertEqual(signing.detach(commands, Path("owned-mount")), [])
        self.assertEqual(run.call_args_list[-1].args[1],
                         [signing.HDIUTIL, "detach", "-force", Path("owned-mount")])
        with patch.object(commands, "run", side_effect=signing.SigningError("detach failed")):
            self.assertEqual(signing.detach(commands, Path("owned-mount")), ["detach failed", "detach failed"])

    def test_zip_reads_final_mount_not_staging_files(self):
        original_snapshot = signing.snapshot
        poisoned = []
        def snapshot(path):
            entries = original_snapshot(path)
            if self.tools.mount is not None and path.parent.name == "payload":
                # After the equality check's read, destroy the staged CLI. Only
                # the final mounted container remains a valid archive source.
                cli = path / "Resources/bin/macOS/uuid-test"
                cli.write_bytes(b"staging tree is not the final release source")
                poisoned.append(cli)
            return entries
        with patch.object(signing, "snapshot", side_effect=snapshot):
            self.sign()
        self.assertEqual(len(poisoned), 1)
        with zipfile.ZipFile(self.unsigned) as archive:
            self.assertEqual(archive.read("UuidTest.4dbase/Resources/bin/macOS/uuid-test"),
                             delivery.synthetic_universal() + b"signature")


if __name__ == "__main__":
    unittest.main()
