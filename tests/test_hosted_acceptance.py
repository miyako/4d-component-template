"""Hosted orchestration failures must never produce accepted artifact evidence."""
import json
from pathlib import Path
import subprocess
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import accept_hosted
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

    def accept(self):
        with patch.object(accept_hosted, "require_tool4d_host"), patch.object(
                accept_hosted, "assemble"), patch.object(
                accept_hosted, "compile_component", return_value=self.fixture.status), patch.object(
                accept_hosted, "test_4d", side_effect=self.host), patch.object(
                accept_hosted.subprocess, "run",
                return_value=subprocess.CompletedProcess([], 0, "tool4d 20.7 101905\n", "")), patch(
                "build_provenance.commit", return_value=None):
            return accept_hosted.accept(self.root, "owner/example-component", self.tool, "v0.1.0")

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
