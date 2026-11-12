"""Publication verifies downloaded bytes and full host contracts; gh is always mocked."""
import copy
import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import release_assets
import test_delivery
import test_host_runner


class ReleaseAssetsTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_delivery.DeliveryTests("test_matrix_only_selected_language")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.revision = "a" * 40
        contract = self.root / "tests/host/contract.json"
        contract.parent.mkdir(parents=True)
        contract.write_text(json.dumps(test_host_runner.CONTRACT))
        archive = self.fixture.package()
        self.evidence = archive.with_suffix(".acceptance.json")
        self.report = {
            "schema": 1, "scope": "hosted", "commit": self.revision,
            "finished": True, "result": "partial", "release_ready": False,
            "configuration": self.fixture.config,
            "steps": {
                "assembly": {"status": "passed"}, "package": {"status": "passed"},
                "compile": {"status": "passed", "details": self.fixture.status},
                "source_host": {"status": "passed", "details": test_host_runner.valid_status(False)},
                "compiled_host": {"status": "passed", "details": test_host_runner.valid_status(True)},
                "signing": {"status": "not_run"},
            },
            "assets": [{"path": "dist/" + archive.name, "sha256": release_assets.sha256(archive),
                        "bytes": archive.stat().st_size}],
        }
        for target in release_assets.TARGETS:
            self.report["steps"]["cli_test_" + target] = {
                "status": "passed", "details": {
                    "target": target, "execution": "passed", "commit": self.revision,
                    "source_sha256": release_assets.source_digest(self.root)}}
        self.report["artifact"] = self.report["assets"][0]
        self.save()

    def save(self):
        self.evidence.write_text(json.dumps(self.report))

    def verify(self, signed=False):
        with patch.object(release_assets, "commit", return_value=self.revision):
            return release_assets.verify_assets(
                self.root, "owner/example-component", "0.1.0", self.revision, signed)

    def test_unsigned_exact_bytes_and_complete_contract_pass_without_secrets(self):
        with patch.dict("os.environ", {}, clear=True):
            assets = self.verify()
        self.assertEqual([path.name for path in assets],
                         ["example-component.zip", "example-component.acceptance.json"])

    def test_false_finished_wrong_commit_and_source_shaped_host_are_rejected(self):
        original = copy.deepcopy(self.report)
        for field, value in (("finished", False), ("finished", 1), ("commit", "b" * 40),
                             ("result", "failed"), ("scope", "local")):
            self.report = {**copy.deepcopy(original), field: value}
            self.save()
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                self.verify()
        self.report = original
        self.report["steps"]["compiled_host"]["details"]["compiled"] = False
        self.save()
        with self.assertRaisesRegex(ValueError, "exact compiled"):
            self.verify()

    def test_missing_negative_assertion_and_compiler_provenance_fail(self):
        original = copy.deepcopy(self.report)
        del self.report["steps"]["source_host"]["details"]["rejectedNul"]
        self.save()
        with self.assertRaisesRegex(ValueError, "missing host contract"):
            self.verify()
        self.report = original
        del self.report["steps"]["compile"]["details"]["output_sha256"]
        self.save()
        with self.assertRaisesRegex(ValueError, "compiler targets"):
            self.verify()

    def test_cross_only_or_other_source_native_evidence_fails(self):
        details = self.report["steps"]["cli_test_windows-x64"]["details"]
        original = details.copy()
        for field, value in (("execution", "not_run"), ("commit", "b" * 40),
                             ("source_sha256", "0" * 64)):
            details.clear()
            details.update({**original, field: value})
            self.save()
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "native build evidence"):
                self.verify()

    def test_tampered_extra_or_traversal_assets_fail(self):
        archive = self.root / self.report["artifact"]["path"]
        original = archive.read_bytes()
        archive.write_bytes(original + b"tamper")
        with self.assertRaisesRegex(ValueError, "accepted bytes"):
            self.verify()
        archive.write_bytes(original)
        self.report["assets"][0]["path"] = "../outside.zip"
        self.save()
        with self.assertRaisesRegex(ValueError, "exact policy-required"):
            self.verify()
        self.report["assets"][0]["path"] = "dist/" + archive.name
        self.save()
        (archive.parent / "unexpected.zip").write_bytes(b"unvalidated")
        with self.assertRaisesRegex(ValueError, "unvalidated assets"):
            self.verify()

    def test_policy_cannot_downgrade_or_approve_missing_signed_assets(self):
        with self.assertRaisesRegex(ValueError, "signing"):
            self.verify(signed=True)
        self.report["steps"]["signing"] = {"status": "passed"}
        self.report["steps"]["signing_proof"] = {"status": "passed"}
        self.report["steps"]["unsigned_compiled_host"] = {
            "status": "passed", "details": test_host_runner.valid_status(True)}
        self.save()
        with self.assertRaisesRegex(ValueError, "unsigned publication"):
            self.verify()
        with self.assertRaisesRegex(ValueError, "policy-required"):
            self.verify(signed=True)

    def test_publication_rechecks_version_policy_without_secrets(self):
        (self.root / "release-policy.json").write_text(
            '{"schema":1,"apple_notarized_versions":["0.1.0"]}')
        with self.assertRaisesRegex(ValueError, "cannot downgrade"):
            self.verify()

    def signed_assets(self):
        name = "example-component"
        dmg = self.root / "dist" / (name + ".dmg")
        dmg.write_bytes(b"synthetic DMG, not Apple evidence")
        proof = {
            "schema": 1, "version": "0.1.0", "sourceSHA": self.revision, "releaseTag": "0.1.0",
            "unsignedCompileInputSHA256": self.fixture.status["input_sha256"],
            "unsignedZIPHashSHA256": "0" * 64, "hostValidation": "required-after-signing",
            "notarization": {"status": "Accepted", "submissionUUID": "12345678-1234-4321-8765-123456789abc"},
            "dmg": {"stapled": True, "validated": True, "sha256": release_assets.sha256(dmg)},
            "zip": {"stapled": False, "notarizedViaDMG": True, "origin": "final-mounted-accepted-DMG",
                    "sha256": self.report["artifact"]["sha256"]},
            "signedFiles": [{"path": path, "verified": True} for path in (
                "Resources/bin/macOS/example-cli", "Libraries/lib4d-arm64.dylib")],
        }
        signing = dmg.with_name(name + "-signing.json")
        signing.write_text(json.dumps(proof))
        self.report["unsigned_artifact"] = {"path": "dist/" + name + ".zip", "sha256": "0" * 64}
        self.report["steps"]["signing"] = {"status": "passed"}
        self.report["steps"]["signing_proof"] = {"status": "passed", "details": proof}
        self.report["steps"]["unsigned_compiled_host"] = {
            "status": "passed", "details": test_host_runner.valid_status(True)}
        self.report["assets"] += [
            {"path": "dist/" + path.name, "sha256": release_assets.sha256(path),
             "bytes": path.stat().st_size} for path in (dmg, signing)]
        self.save()
        return signing, proof

    def test_signed_publication_requires_proof_and_separate_final_host(self):
        signing, proof = self.signed_assets()
        self.assertEqual(len(self.verify(signed=True)), 4)
        original = copy.deepcopy(proof)
        for section, field, value in (
                ("notarization", "status", "Rejected"), ("notarization", "submissionUUID", "bad"),
                ("dmg", "stapled", False), ("dmg", "validated", 1), ("dmg", "sha256", "0" * 64),
                ("zip", "origin", "staged-copy"), ("zip", "stapled", True)):
            altered = copy.deepcopy(original)
            altered[section][field] = value
            signing.write_text(json.dumps(altered))
            asset = self.report["assets"][-1]
            asset.update(sha256=release_assets.sha256(signing), bytes=signing.stat().st_size)
            self.save()
            with self.subTest(section=section, field=field), self.assertRaises(ValueError):
                self.verify(signed=True)
        proof = copy.deepcopy(original)
        proof["signedFiles"][0]["verified"] = False
        signing.write_text(json.dumps(proof))
        self.report["assets"][-1].update(
            sha256=release_assets.sha256(signing), bytes=signing.stat().st_size)
        self.save()
        with self.assertRaisesRegex(ValueError, "verified CLI"):
            self.verify(signed=True)

    def test_legacy_prefixed_signing_proof_cannot_approve_new_release(self):
        signing, proof = self.signed_assets()
        proof["releaseTag"] = "v0.1.0"
        signing.write_text(json.dumps(proof))
        self.report["steps"]["signing_proof"]["details"] = proof
        self.report["assets"][-1].update(
            sha256=release_assets.sha256(signing), bytes=signing.stat().st_size)
        self.save()
        with self.assertRaisesRegex(ValueError, "release provenance"):
            self.verify(signed=True)

    def test_prefixed_publication_never_creates_tag_or_release(self):
        with patch.object(release_assets, "create_release_tag") as tag, patch.object(
                release_assets.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "without a v prefix"):
                release_assets.publish(self.root, "owner/example-component", "v0.1.0",
                                       self.revision, create_tag=True)
            tag.assert_not_called()
            run.assert_not_called()

    def test_gh_receives_only_verified_literal_assets_and_existing_tag(self):
        with patch.object(release_assets, "commit", return_value=self.revision), patch.object(
                release_assets, "verify_tag") as tag, patch.object(
                release_assets.subprocess, "run") as run:
            release_assets.publish(self.root, "owner/example-component", "0.1.0", self.revision)
        tag.assert_called_once_with(self.root, "0.1.0", self.revision)
        arguments = run.call_args.args[0]
        self.assertEqual(arguments[:4], ["gh", "release", "create", "0.1.0"])
        self.assertIn("--verify-tag", arguments)
        self.assertIn(str(self.evidence), arguments)
        self.assertNotIn("shell", run.call_args.kwargs)
        self.assertNotIn("*.zip", arguments)

    def test_release_secret_gate_and_manual_escalation_are_explicit(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        unsigned = workflow.split("name: Build and accept unsigned component without Apple secrets")[1].split(
            "name: Sign, notarize, staple")[0]
        self.assertIn("apple_signing == 'false'", unsigned)
        self.assertNotIn("secrets.", unsigned)
        signed = workflow.split("name: Sign, notarize, staple")[1].split(
            "uses: actions/upload-artifact")[0]
        self.assertIn("apple_signing == 'true'", signed)
        self.assertEqual(signed.count("secrets."), 7)
        self.assertIn("--require-apple-signing", signed)
        self.assertIn("require_apple_signing:", workflow)
        self.assertIn("scripts/release_assets.py", workflow)
        self.assertNotIn("continue-on-error", workflow)

    def test_new_tag_is_created_only_after_assets_pass_and_before_release(self):
        order = []
        with patch.object(release_assets, "verify_assets", side_effect=lambda *args: order.append("assets") or [
                self.evidence]), patch.object(
                release_assets, "create_release_tag", side_effect=lambda *args: order.append("tag")), patch.object(
                release_assets.subprocess, "run", side_effect=lambda *args, **kwargs: order.append("release")):
            release_assets.publish(self.root, "owner/example-component", "0.1.0",
                                   self.revision, create_tag=True)
        self.assertEqual(order, ["assets", "tag", "release"])

    def test_failed_or_unexecuted_acceptance_never_mutates_refs_or_releases(self):
        baseline = copy.deepcopy(self.report)
        for check in ("assembly", "package", "compile", "source_host", "compiled_host",
                      "cli_test_macos-x64", "cli_test_macos-arm64", "cli_test_windows-x64"):
            for status in ("failed", "not_run"):
                self.report = copy.deepcopy(baseline)
                self.report["steps"][check]["status"] = status
                self.save()
                with self.subTest(check=check, status=status), patch.object(
                        release_assets, "commit", return_value=self.revision), patch.object(
                        release_assets, "create_release_tag") as tag, patch.object(
                        release_assets.subprocess, "run") as run:
                    with self.assertRaisesRegex(ValueError, "did not pass"):
                        release_assets.publish(self.root, "owner/example-component", "0.1.0",
                                               self.revision, create_tag=True)
                    tag.assert_not_called()
                    run.assert_not_called()

    def test_invalid_assets_or_tag_collision_never_create_release(self):
        with patch.object(release_assets, "verify_assets", side_effect=ValueError("asset mismatch")), patch.object(
                release_assets, "create_release_tag") as tag, patch.object(
                release_assets.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "asset mismatch"):
                release_assets.publish(self.root, "owner/example-component", "0.1.0",
                                       self.revision, create_tag=True)
            tag.assert_not_called()
            run.assert_not_called()
        with patch.object(release_assets, "verify_assets", return_value=[self.evidence]), patch.object(
                release_assets, "create_release_tag", side_effect=ValueError("collision")), patch.object(
                release_assets.subprocess, "run") as run:
            with self.assertRaisesRegex(ValueError, "collision"):
                release_assets.publish(self.root, "owner/example-component", "0.1.0",
                                       self.revision, create_tag=True)
            run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
