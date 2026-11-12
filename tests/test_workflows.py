"""Structural workflow contracts use disposable copies, never GitHub mutations."""
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import workflow_contract


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        for directory in (".github/workflows", "scripts", "tooling"):
            shutil.copytree(ROOT / directory, self.root / directory)
        for name in ("workflow-contract.json", "release-policy.json"):
            shutil.copy2(ROOT / name, self.root / name)

    def document(self, name):
        return workflow_contract.yaml_document(self.root / ".github/workflows" / (name + ".yml"))

    def mutate(self, name, action):
        document = self.document(name)
        action(document)
        (self.root / ".github/workflows" / (name + ".yml")).write_text(
            yaml.safe_dump(document, sort_keys=False), encoding="utf-8")

    def test_canonical_contract(self):
        self.assertEqual(workflow_contract.validate(self.root)["status"], "passed")

    def test_description_and_formatting_changes_preserve_behavior(self):
        self.mutate("ci", lambda d: d["on"]["workflow_call"]["inputs"]["source_sha"].update(
            description="Exact source revision"))
        self.mutate("bump-version", lambda d: d["on"]["workflow_dispatch"]["inputs"]["mode"].update(
            description="Choose increment"))
        self.mutate("ci", lambda d: next(
            step for step in d["jobs"]["native"]["steps"] if "test_cli.py" in step.get("run", "")
        ).update(run='python3  -m unittest discover -s "tests" -p "test_cli.py" -v\n'))
        self.assertEqual(workflow_contract.validate(self.root)["status"], "passed")

    def test_mentions_and_suppressed_failures_do_not_count_as_execution(self):
        for name, job, needle in (
            ("ci", "native", "test_cli.py"),
            ("ci", "native", "scripts/build_cli.py"),
            ("ci", "configuration", "scripts/workflow_contract.py"),
            ("build", "compile", "scripts/accept_hosted.py"),
            ("build", "preflight", "sign_release.py"),
            ("build", "preflight", "release_source.py"),
            ("bump-version", "bump", "release_source.py"),
            ("build", "publish", "scripts/release_assets.py"),
        ):
            path = self.root / ".github/workflows" / (name + ".yml")
            original = path.read_text()
            invocation = next(step["run"] for step in self.document(name)["jobs"][job]["steps"]
                              if needle in step.get("run", ""))
            for replacement in ("echo '{command}'", "{command} || true", "# {command}\necho skipped"):
                with self.subTest(job=job, needle=needle, replacement=replacement):
                    self.mutate(name, lambda d: next(
                        step for step in d["jobs"][job]["steps"] if needle in step.get("run", "")
                    ).update(run=replacement.format(command=invocation)))
                    with self.assertRaises((ValueError, SyntaxError)):
                        workflow_contract.validate(self.root)
                    path.write_text(original)

    def test_main_guard_must_exit_not_only_mention_exit(self):
        self.mutate("build", lambda d: d["jobs"]["preflight"]["steps"][0].update(run="echo 'exit 1'"))
        with self.assertRaisesRegex(ValueError, "main guard"):
            workflow_contract.validate(self.root)

    def test_extra_workflow_extensions_and_names_are_rejected(self):
        for name in ("extra.yml", "extra.yaml"):
            path = self.root / ".github/workflows" / name
            path.write_text("name: Extra\n")
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "exactly"):
                workflow_contract.validate(self.root)
            path.unlink()
        self.mutate("ci", lambda value: value.update(name="Other"))
        with self.assertRaisesRegex(ValueError, "names"):
            workflow_contract.validate(self.root)

    def test_duplicate_yaml_and_configuration_keys_are_rejected(self):
        path = self.root / ".github/workflows/ci.yml"
        text = path.read_text()
        path.write_text(text + "\nname: CI\n")
        with self.assertRaisesRegex(ValueError, "duplicate"):
            workflow_contract.validate(self.root)
        path.write_text(text)
        (self.root / "workflow-contract.json").write_text(
            '{"schema":1,"schema":1,"profile":"cli-universal-v1","version_surfaces":[]}')
        with self.assertRaisesRegex(ValueError, "duplicate"):
            workflow_contract.validate(self.root)

    def test_negative_dispatch_and_graph_mutations(self):
        cases = [
            ("ci", lambda d: d["on"].update(push={"tags": ["*"]})),
            ("build", lambda d: d["on"].update(push={"tags": ["*"]})),
            ("bump-version", lambda d: d["on"].update(push={"tags": ["*"]})),
            ("bump-version", lambda d: d["on"]["workflow_dispatch"]["inputs"]["mode"].update(options=["patch"])),
            ("build", lambda d: d["on"]["workflow_dispatch"]["inputs"].update(version={"type": "string"})),
            ("build", lambda d: d["jobs"]["preflight"]["steps"][0].update({"if": "false"})),
            ("build", lambda d: d["jobs"]["native"]["with"].update(source_sha="main")),
            ("build", lambda d: d["jobs"]["native"]["with"].update(release_call=False)),
            ("build", lambda d: d["jobs"]["compile"].update(needs=["preflight"])),
            ("build", lambda d: d["jobs"]["publish"].update(needs=["preflight"])),
            ("build", lambda d: d["jobs"]["preflight"]["outputs"].update(source_sha="main")),
            ("bump-version", lambda d: d["jobs"]["bump"]["steps"][0]["with"].update(ref="main")),
            ("build", lambda d: d["jobs"]["compile"].update({"if": "false"})),
            ("ci", lambda d: d.update(permissions={"contents": "write"})),
            ("ci", lambda d: d["jobs"]["native"].update({"continue-on-error": True})),
            ("ci", lambda d: d["jobs"]["native"].update({"runs-on": "ubuntu-24.04"})),
            ("ci", lambda d: next(s for s in d["jobs"]["native"]["steps"]
                                if "test_cli.py" in s.get("run", "")).update({"if": "false"})),
            ("build", lambda d: d["jobs"]["compile"]["env"].update(RELEASE_SHA="main")),
            ("build", lambda d: d["jobs"]["compile"].update(env={"LEAK": "${{ secrets.KEYCHAIN_PASSWORD }}"})),
            ("build", lambda d: d["jobs"]["preflight"].update(permissions={"contents": "write"})),
            ("build", lambda d: d["jobs"]["preflight"]["steps"].append({"run": "git push origin HEAD:main"})),
            ("bump-version", lambda d: d["jobs"]["bump"]["steps"].append({"run": "gh workflow run build.yml"})),
            ("bump-version", lambda d: d["jobs"]["bump"]["steps"].append({"run": "python scripts/build_cli.py"})),
            ("ci", lambda d: d["jobs"]["configuration"]["steps"].append({"run": "gh secret set NAME"})),
            ("ci", lambda d: d["jobs"]["configuration"]["steps"].append({"run": "gh release create 1.0.0"})),
        ]
        original = {name: (self.root / ".github/workflows" / (name + ".yml")).read_text()
                    for name in ("ci", "build", "bump-version")}
        for name, action in cases:
            with self.subTest(action=action):
                self.mutate(name, action)
                with self.assertRaises(ValueError):
                    workflow_contract.validate(self.root)
                (self.root / ".github/workflows" / (name + ".yml")).write_text(original[name])

    def test_wrong_checkout_omitted_helper_artifact_and_secret_gate_fail(self):
        path = self.root / ".github/workflows/build.yml"
        original = path.read_text()
        for before, after in (
            ("ref: ${{ needs.preflight.outputs.source_sha }}", "ref: main"),
            ("ref: ${{ github.sha }}", "ref: main"),
            ("--create-tag --publish", "--publish"),
            ("apple_signing == 'true'", "apple_signing == 'false'"),
            ("name: compiled-release", "name: unvalidated-release"),
            ("dist/*.acceptance.json", "dist/*.other.json"),
            ("if: always()", "if: success()"),
        ):
            with self.subTest(before=before):
                path.write_text(original.replace(before, after))
                with self.assertRaises(ValueError):
                    workflow_contract.validate(self.root)
        path.write_text(original)
        (self.root / "scripts/accept_hosted.py").unlink()
        with self.assertRaisesRegex(ValueError, "required regular file"):
            workflow_contract.validate(self.root)

    def test_unsupported_configuration_and_unsafe_extensions_fail(self):
        path = self.root / "workflow-contract.json"
        baseline = json.loads(path.read_text())
        for value in (
            dict(baseline, profile="windows-only"),
            dict(baseline, dependency_builder="image-libraries"),
            dict(baseline, version_surfaces=[{"kind": "shell", "path": "cli/x"}]),
            dict(baseline, version_surfaces=[{"kind": "json-pointer", "path": "../outside", "pointer": "/version"}]),
            dict(baseline, version_surfaces=[{"kind": "json-pointer", "path": "release-policy.json", "pointer": "/version"}]),
            dict(baseline, version_surfaces=[{"kind": "json-pointer", "path": "cli/version.json", "pointer": "/bad~2key"}]),
        ):
            with self.subTest(value=value):
                path.write_text(json.dumps(value))
                with self.assertRaises(ValueError):
                    workflow_contract.configuration(self.root)

    def test_missing_signing_policy_keeps_unsigned_default_supported(self):
        (self.root / "release-policy.json").unlink()
        self.assertEqual(workflow_contract.validate(self.root)["status"], "passed")


if __name__ == "__main__":
    unittest.main()
