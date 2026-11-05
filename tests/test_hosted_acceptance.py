"""Hosted orchestration failures must never produce accepted artifact evidence."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import accept_hosted
import accept_local
from build_provenance import record
import test_delivery


class HostedAcceptanceTests(unittest.TestCase):
    def setUp(self):
        self.fixture = test_delivery.DeliveryTests("test_matrix_only_selected_language")
        self.fixture.setUp()
        self.addCleanup(self.fixture.doCleanups)
        self.root = self.fixture.root
        self.tool = self.root / "tool4d"
        self.tool.write_bytes(b"synthetic tool identity")
        for target in accept_hosted.TARGETS:
            executable = self.root / "build" / target / (
                "example-cli.exe" if target == "windows-x64" else "example-cli")
            executable.parent.mkdir()
            executable.write_bytes(test_delivery.synthetic_pe() if target == "windows-x64" else b"native slice")
            record(self.root, target, executable, True, "synthetic test compiler")
        self.host_calls = []

    def host(self, root, tool, component=None):
        self.host_calls.append(component is not None)
        return {"success": True, "finished": True, "compiled": component is not None}

    def accept(self, signed=False, subprocess_run=None, tag="0.1.0"):
        with patch.object(accept_hosted, "require_tool4d_host"), patch.object(
                accept_hosted, "assemble"), patch.object(
                accept_hosted, "compile_component", return_value=self.fixture.status), patch.object(
                accept_hosted, "test_4d", side_effect=self.host), patch.object(
                accept_hosted.subprocess, "run", side_effect=subprocess_run,
                return_value=subprocess.CompletedProcess([], 0, "tool4d 20.7 101905\n", "")), patch(
                "build_provenance.commit", return_value=None), patch.object(
                accept_hosted, "commit", return_value="a" * 40 if signed else None):
            return accept_hosted.accept(self.root, "owner/example-component", self.tool, tag, signed)

    def test_default_package_tag_is_the_prefix_free_configured_version(self):
        report = self.accept(tag=None)
        self.assertTrue(report["finished"])
        self.assertEqual(report["steps"]["package"]["status"], "passed")
        self.assertEqual(self.host_calls, [False, True])

    def test_local_orchestrator_packages_with_prefix_free_version(self):
        with patch.object(accept_local, "doctor", return_value={}), patch.object(
                accept_local, "require_tool4d_host"), patch.object(
                accept_local, "native_target", return_value="macos-arm64"), patch.object(
                accept_local, "build"), patch.object(accept_local, "assemble"), patch.object(
                accept_local, "compile_component", return_value=self.fixture.status), patch.object(
                accept_local, "test_4d", side_effect=self.host), patch.object(
                accept_local.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, "synthetic tool4d identity\n", "")):
            report = accept_local.accept(self.root, "owner/example-component", self.tool)
        self.assertTrue(report["finished"])
        self.assertEqual(report["steps"]["package"]["status"], "passed")
        self.assertEqual(self.host_calls, [False, True])
        self.assertFalse(report["release_ready"])

    def test_prefixed_tag_is_rejected_before_host_or_package_acceptance(self):
        with self.assertRaisesRegex(ValueError, "without a v prefix"):
            self.accept(tag="v0.1.0")
        self.assertEqual(self.host_calls, [])
        self.assertFalse((self.root / "dist/example-component.acceptance.json").exists())

    def test_accepted_zip_has_embedded_native_and_both_host_reports(self):
        report = self.accept()
        self.assertEqual(self.host_calls, [False, True])
        self.assertTrue(report["finished"])
        self.assertEqual(report["result"], "partial")
        self.assertFalse(report["release_ready"])
        self.assertEqual(report["steps"]["native_intel_4d"]["status"], "not_run")
        self.assertEqual(report["steps"]["windows_4d"]["status"], "not_run")
        self.assertEqual(report["steps"]["signing"]["status"], "not_run")
        for target in accept_hosted.TARGETS:
            self.assertEqual(report["steps"]["cli_test_" + target]["status"], "passed")
        archive = self.root / report["artifact"]["path"]
        self.assertEqual(accept_hosted.sha256(archive), report["artifact"]["sha256"])
        self.assertEqual(json.loads(archive.with_suffix(".acceptance.json").read_text()), report)
        for name in ("source-host-status.json", "compiled-host-status.json"):
            self.assertTrue((self.root / "build" / name).is_file())

    def test_cross_only_or_changed_manifest_stops_before_any_host(self):
        manifest = self.root / "build/windows-x64/build-manifest.json"
        content = json.loads(manifest.read_text())
        for field, value in (("execution", "not_run"), ("binary_sha256", "0" * 64)):
            manifest.write_text(json.dumps({**content, field: value}))
            with self.subTest(field=field), self.assertRaises(ValueError):
                self.accept()
            report = json.loads((self.root / "build/hosted-acceptance.json").read_text())
            self.assertFalse(report["finished"])
            self.assertEqual(report["result"], "failed")
            self.assertEqual(self.host_calls, [])
        self.assertFalse((self.root / "dist/example-component.acceptance.json").exists())

    def test_final_host_failure_retains_failure_not_stable_acceptance(self):
        with patch.object(self, "host", side_effect=[
                {"success": True, "finished": True, "compiled": False},
                ValueError("final compiled package did not load")]):
            with self.assertRaisesRegex(ValueError, "did not load"):
                self.accept()
        report = json.loads((self.root / "build/hosted-acceptance.json").read_text())
        self.assertFalse(report["finished"])
        self.assertEqual(report["steps"]["compiled_host"]["status"], "failed")
        self.assertFalse((self.root / "dist/example-component.acceptance.json").exists())

    def test_failed_compile_marker_cannot_upload_a_source_shaped_success(self):
        self.fixture.marker.unlink()
        with self.assertRaisesRegex(ValueError, "compile-status"):
            self.accept()
        report = json.loads((self.root / "build/hosted-acceptance.json").read_text())
        self.assertFalse(report["finished"])
        self.assertEqual(report["steps"]["package"]["status"], "failed")
        self.assertEqual(report["steps"]["compiled_host"]["status"], "not_run")
        self.assertFalse((self.root / "dist/example-component.acceptance.json").exists())

    def test_required_signing_never_downgrades_when_helper_is_missing(self):
        with self.assertRaisesRegex(ValueError, "verified scripts/sign_release"):
            self.accept(signed=True)
        report = json.loads((self.root / "build/hosted-acceptance.json").read_text())
        self.assertEqual(self.host_calls, [False, True])
        self.assertEqual(report["steps"]["signing"]["status"], "failed")
        self.assertEqual(report["steps"]["compiled_host"]["status"], "not_run")
        self.assertFalse(report["finished"])
        self.assertFalse((self.root / "dist/example-component.acceptance.json").exists())

    def test_signing_boundary_tests_exact_final_zip_and_binds_all_assets(self):
        helper = self.root / "scripts/sign_release.py"
        helper.parent.mkdir()
        helper.write_text("# synthetic boundary fixture; never executed\n")
        commands = []

        def run(arguments, **options):
            commands.append(arguments)
            if arguments[1:3] == [str(helper), "sign"]:
                archive = self.root / "dist/example-component.zip"
                with accept_hosted.unpack_for_test(self.root, archive).joinpath(
                        "Resources/signed-boundary.txt").open("wb") as output:
                    output.write(b"synthetic signed fixture, not Apple verification")
                with zipfile.ZipFile(archive, "a") as packed:
                    packed.writestr("example-component.4dbase/Resources/signed-boundary.txt",
                                    b"synthetic signed fixture, not Apple verification")
                dmg = archive.with_suffix(".dmg")
                dmg.write_bytes(b"synthetic DMG")
                unsigned = json.loads((self.root / "build/hosted-acceptance.json").read_text())[
                    "unsigned_artifact"]
                proof = {
                    "schema": 1, "version": "0.1.0", "sourceSHA": "a" * 40, "releaseTag": "0.1.0",
                    "unsignedCompileInputSHA256": self.fixture.status["input_sha256"],
                    "unsignedZIPHashSHA256": unsigned["sha256"],
                    "hostValidation": "required-after-signing",
                    "signedFiles": [{"path": path, "verified": True} for path in (
                        "Resources/bin/macOS/example-cli", "Libraries/lib4d-arm64.dylib")],
                    "notarization": {"status": "Accepted",
                                     "submissionUUID": "12345678-1234-4321-8765-123456789abc"},
                    "dmg": {"stapled": True, "validated": True, "sha256": accept_hosted.sha256(dmg)},
                    "zip": {"stapled": False, "notarizedViaDMG": True,
                            "origin": "final-mounted-accepted-DMG", "sha256": accept_hosted.sha256(archive)},
                }
                (archive.parent / "example-component-signing.json").write_text(json.dumps(proof))
            return subprocess.CompletedProcess(arguments, 0, "tool4d 20.7 101905\n", "")

        def host(root, tool, component=None):
            self.host_calls.append(component is not None)
            if len(self.host_calls) == 3:
                self.assertTrue((component / "Resources/signed-boundary.txt").is_file())
            return {"success": True, "finished": True, "compiled": component is not None}

        with patch.object(self, "host", side_effect=host):
            report = self.accept(signed=True, subprocess_run=run)
        self.assertEqual(self.host_calls, [False, True, True])
        self.assertEqual(report["steps"]["signing"]["status"], "passed")
        self.assertNotEqual(report["unsigned_artifact"]["sha256"], report["artifact"]["sha256"])
        self.assertEqual(len(report["assets"]), 3)
        for asset in report["assets"]:
            self.assertEqual(accept_hosted.sha256(self.root / asset["path"]), asset["sha256"])
        self.assertIn([sys.executable, str(helper), "sign", "--root", str(self.root),
                       "--require-apple-signing"], commands)

    def test_zero_exit_without_signing_assets_cannot_approve_release(self):
        helper = self.root / "scripts/sign_release.py"
        helper.parent.mkdir()
        helper.write_text("# synthetic helper boundary\n")
        with self.assertRaisesRegex(ValueError, "did not produce"):
            self.accept(signed=True)
        report = json.loads((self.root / "build/hosted-acceptance.json").read_text())
        self.assertEqual(report["steps"]["signing"]["status"], "failed")
        self.assertEqual(report["steps"]["compiled_host"]["status"], "not_run")
        self.assertFalse(report["finished"])

    def test_manual_ci_uploads_component_not_just_executables(self):
        workflow = (ROOT / ".github/workflows/ci.yml").read_text()
        self.assertIn('accept_hosted.py --repository "$GITHUB_REPOSITORY"', workflow)
        self.assertIn("name: compiled-component", workflow)
        self.assertIn("dist/*.acceptance.json", workflow)
        self.assertIn("name: component-acceptance-diagnostics", workflow)
        self.assertLess(workflow.index("accept_hosted.py"), workflow.index("name: compiled-component"))
        self.assertNotIn("gh release", workflow)


if __name__ == "__main__":
    unittest.main()
