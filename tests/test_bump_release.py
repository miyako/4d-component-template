"""Version changes use disposable initialized destinations, never this template."""
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
import rename_feature


class BumpReleaseTests(unittest.TestCase):
    def setUp(self):
        self.root = ROOT / (".bump-release-test-" + uuid.uuid4().hex)
        self.root.mkdir()
        self.addCleanup(shutil.rmtree, self.root)
        for name in ("component", "cli-starters", "tests/host", ".github/workflows", "scripts", "tooling"):
            shutil.copytree(ROOT / name, self.root / name)
        for name in ("template.json", "package.json", "README.md", "release-policy.json", "workflow-contract.json"):
            shutil.copy2(ROOT / name, self.root / name)
        shutil.copy2(ROOT / "tests/test_cli.py", self.root / "tests/test_cli.py")
        shutil.copy2(ROOT / "tests/cli-contract.json", self.root / "tests/cli-contract.json")
        self.git("init", "-q")
        self.git("config", "user.name", "Release fixture")
        self.git("config", "user.email", "release-fixture@example.invalid")
        self.git("remote", "add", "origin", "https://github.com/owner/CaseTools.git")
        self.git("commit", "-q", "--allow-empty", "-m", "fixture")
        self.environment = patch.dict(os.environ, {"GITHUB_REPOSITORY": "owner/CaseTools"})
        self.environment.start()
        self.addCleanup(self.environment.stop)

    def git(self, *args):
        return subprocess.run(["git", *args], cwd=self.root, check=True,
                              capture_output=True, text=True, encoding="utf-8").stdout.strip()

    def configure(self, language="go"):
        initialize.initialize(self.root, "CaseTools", "IndependentNS", "case-cli",
                              language, "A release fixture")

    def snapshot(self):
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*") if p.is_file() and ".git" not in p.parts}

    def extensions(self, surfaces):
        path = self.root / "workflow-contract.json"
        value = json.loads(path.read_text())
        value["version_surfaces"] = surfaces
        path.write_text(json.dumps(value) + "\n")

    def test_bounded_version_extensions_compose_and_preserve_unrelated_fields(self):
        self.configure("cpp")
        metadata = self.root / "cli/extra.json"
        metadata.write_text('{"own":{"version":"0.1.0"},"dependency":"0.1.0"}\n')
        header = self.root / "cli/extra.hpp"
        header.write_text('const auto release = "0.1.0";\n// dependency 0.1.0\n')
        self.extensions([
            {"kind": "json-pointer", "path": "cli/extra.json", "pointer": "/own/version"},
            {"kind": "literal", "path": "cli/extra.hpp", "prefix": 'release = "',
             "suffix": '";', "count": 1},
        ])
        bump_release.apply(self.root, "0.2.0")
        self.assertEqual(json.loads(metadata.read_text()), {"own": {"version": "0.2.0"}, "dependency": "0.1.0"})
        self.assertIn('release = "0.2.0";', header.read_text())
        self.assertIn("// dependency 0.1.0", header.read_text())
        self.assertEqual(bump_release.apply(self.root, "0.2.0")["changed_paths"], [])

    def test_invalid_extension_validates_before_any_version_writes(self):
        self.configure()
        extra = self.root / "cli/extra.json"
        extra.write_text('{"version":"9.9.9"}')
        self.extensions([{"kind": "json-pointer", "path": "cli/extra.json", "pointer": "/version"}])
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            bump_release.apply(self.root, "0.2.0")
        self.assertEqual(before, self.snapshot())
        extra.unlink()
        extra.symlink_to(self.root / "package.json")
        with self.assertRaisesRegex(ValueError, "non-symlink"):
            bump_release.apply(self.root, "0.2.0")

    def test_all_languages_case_identity_renamed_class_and_idempotency(self):
        pristine = self.snapshot()
        for language in ("go", "rust", "cpp"):
            with self.subTest(language=language):
                for child in list(self.root.iterdir()):
                    if child.name != ".git":
                        if child.is_dir():
                            shutil.rmtree(child)
                        else:
                            child.unlink()
                for relative, content in pristine.items():
                    path = self.root / relative
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(content)
                self.configure(language)
                rename_feature.rename_feature(self.root, "Identifier")
                feature = self.root / "component/CaseTools/Project/Sources/Classes/Identifier.4dm"
                feature.write_text(feature.read_text() + '\n// unrelated version 8.9.0\n'
                                   'Function fixtureVersion()\n\tThis.version:="0.1.0"\n')
                before = self.snapshot()
                result = bump_release.apply(self.root, "1.2.3")
                changed = sorted(name for name, value in self.snapshot().items() if before[name] != value)
                self.assertEqual(result["changed_paths"], changed)
                self.assertEqual(result["tag"], "1.2.3")
                self.assertIn('This.version:="1.2.3"', feature.read_text())
                self.assertIn("// unrelated version 8.9.0", feature.read_text())
                self.assertEqual(json.loads((self.root / "template.json").read_text())["version"], "1.2.3")
                self.assertIn('"version":"1.2.3"', (self.root / "tests/test_cli.py").read_text())
                _, plan = bump_release.plan(self.root, "1.2.3")
                self.assertEqual(plan, {})
                snapshot = self.snapshot()
                self.assertEqual(bump_release.apply(self.root, "1.2.3")["changed_paths"], [])
                self.assertEqual(snapshot, self.snapshot())
                if language == "rust":
                    for name in ("Cargo.toml", "Cargo.lock"):
                        self.assertIn('version = "1.2.3"', (self.root / "cli" / name).read_text())

    def test_next_highest_stable_numeric_tag_and_modes(self):
        self.configure()
        for tag in ("1.9.9", "1.10.2", "1.10.1", "20.0.0-rc.1", "9.0.0+build",
                    "01.0.0", "v01.0.0", "v20.0.0-rc.1", "v9.0.0+build", "20R3.2", "unrelated"):
            self.git("tag", tag)
        before = self.snapshot()
        for mode, version in (("patch", "1.10.3"), ("minor", "1.11.0"), ("major", "2.0.0")):
            self.assertEqual(bump_release.next_version(self.root, mode),
                             {"version": version, "tag": version})
        self.assertEqual(before, self.snapshot())

    def test_legacy_and_mixed_tag_history_uses_highest_baseline_without_rewriting(self):
        self.configure()
        for tag in ("v1.10.2", "1.9.9"):
            self.git("tag", tag)
        self.assertEqual(bump_release.next_version(self.root, "patch"),
                         {"version": "1.10.3", "tag": "1.10.3"})
        self.git("tag", "1.11.0")
        before = self.git("show-ref", "--tags")
        self.assertEqual(bump_release.next_version(self.root, "patch"),
                         {"version": "1.11.1", "tag": "1.11.1"})
        self.assertEqual(self.git("show-ref", "--tags"), before)
        self.assertEqual(bump_release.next_version(self.root, "minor", tags=["v2.3.4"]),
                         {"version": "2.4.0", "tag": "2.4.0"})

    def test_no_stable_tag_bumps_configured_base(self):
        self.configure()
        bump_release.apply(self.root, "3.4.5")
        for tag in ("99.0.0-preview", "v99.0.0-preview", "20R3.2"):
            self.git("tag", tag)
        for mode, version in (("patch", "3.4.6"), ("minor", "3.5.0"), ("major", "4.0.0")):
            self.assertEqual(bump_release.next_version(self.root, mode)["version"], version)

    def test_repeated_bump_advances_source_and_still_validates_all_surfaces(self):
        self.configure()
        bump_release.apply(self.root, "1.2.4")
        for tags in (["1.2.3"], ["v1.2.3"], ["1.2.3", "v1.2.3", "2.0.0-rc.1"]):
            self.assertEqual(bump_release.next_version(self.root, "patch", tags=tags),
                             {"version": "1.2.5", "tag": "1.2.5"})
        contract = self.root / "tests/host/contract.json"
        contract.write_text(contract.read_text().replace('\\"version\\":\\"1.2.4\\"',
                                                         '\\"version\\":\\"1.2.3\\"'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            bump_release.next_version(self.root, "patch", tags=["v1.2.3"])
        self.assertEqual(before, self.snapshot())

    def test_source_ahead_of_tags_is_the_bump_base(self):
        self.configure()
        bump_release.apply(self.root, "3.4.5")
        before = self.snapshot()
        for mode, version in (("patch", "3.4.6"), ("minor", "3.5.0"), ("major", "4.0.0")):
            with self.subTest(mode=mode):
                self.assertEqual(bump_release.next_version(self.root, mode, tags=["v1.2.3"])["version"], version)
        self.assertEqual(before, self.snapshot())

    def test_empty_optional_feature_version_is_rejected_on_equal_retry(self):
        self.configure()
        feature = self.root / "component/CaseTools/Project/Sources/Classes/Greeting.4dm"
        feature.write_text(feature.read_text() + '\nFunction fixtureVersion()\n\tThis.version:=""\n')
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            bump_release.apply(self.root, "0.1.0", stage=True)
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            bump_release.next_version(self.root, "patch", tags=["v0.0.9"])
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_stage_adds_only_changed_paths_and_empty_retry_is_noop(self):
        self.configure()
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "initialized fixture")
        unrelated = self.root / "unrelated.txt"
        unrelated.write_text("must remain untracked\n")
        result = bump_release.apply(self.root, "0.2.0", stage=True)
        staged = self.git("diff", "--cached", "--name-only").splitlines()
        self.assertEqual(staged, result["changed_paths"])
        self.assertNotIn("unrelated.txt", staged)
        self.git("commit", "-q", "-m", "bump fixture")
        self.assertEqual(bump_release.apply(self.root, "0.2.0", stage=True)["changed_paths"], [])
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")
        self.assertEqual(unrelated.read_text(), "must remain untracked\n")

    def test_stage_validation_failure_neither_writes_nor_stages(self):
        self.configure()
        self.git("add", "--", ".")
        self.git("commit", "-q", "-m", "initialized fixture")
        contract = self.root / "tests/host/contract.json"
        contract.write_text(contract.read_text().replace('\\"version\\":\\"0.1.0\\"',
                                                         '\\"version\\":\\"0.0.1\\"'))
        before = self.snapshot()
        with self.assertRaisesRegex(ValueError, "inconsistent"):
            bump_release.apply(self.root, "0.2.0", stage=True)
        self.assertEqual(before, self.snapshot())
        self.assertEqual(self.git("diff", "--cached", "--name-only"), "")

    def test_uninitialized_original_and_exact_destination_guards(self):
        before = self.snapshot()
        with self.assertRaises(ValueError):
            bump_release.apply(self.root, "1.0.0")
        self.assertEqual(before, self.snapshot())
        self.configure()
        for repository in ("owner/casetools", "other/CaseTools", "owner/Wrong"):
            with self.subTest(repository=repository), self.assertRaises(ValueError):
                bump_release.apply(self.root, "1.0.0", repository)
        self.git("remote", "set-url", "origin", "https://github.com/miyako/4d-component-template.git")
        with patch.dict(os.environ, {"GITHUB_REPOSITORY": "miyako/4d-component-template"}):
            with self.assertRaisesRegex(ValueError, "original template"):
                bump_release.apply(self.root, "1.0.0")

    def test_invalid_new_versions_make_no_changes(self):
        self.configure()
        before = self.snapshot()
        for version in ("v1.0.0", "01.2.3", "1.2", "1.2.3\n", "1.2.3-beta", "1.2.3+build", None):
            with self.subTest(version=version), self.assertRaises(ValueError):
                bump_release.apply(self.root, version)
            self.assertEqual(before, self.snapshot())

    def test_inconsistent_or_malformed_surfaces_fail_before_writes(self):
        self.configure("rust")
        targets = {
            "template.json": ('"version": "0.1.0"', '"version": "not-semver"'),
            "package.json": ('"version": "0.1.0"', '"version": "0.2.0"'),
            "cli/Cargo.toml": ('version = "0.1.0"', 'version = "0.3.0"'),
            "cli/Cargo.lock": ('version = "0.1.0"', 'version = "0.3.0"'),
            "cli/src/main.rs": ('"version":"0.1.0"', '"version":"bad"'),
            "tests/host/Project/Sources/Methods/Smoke.4dm": ('#"0.1.0"', '#"0.3.0"'),
            "tests/host/contract.json": ('\\"version\\":\\"0.1.0\\"', '\\"version\\":\\"0.8.0\\"'),
            "README.md": ('"version":"0.1.0"', '"version":"0.9.0"'),
        }
        for relative, (old, new) in targets.items():
            path = self.root / relative
            text = path.read_text()
            self.assertIn(old, text)
            path.write_text(text.replace(old, new))
            before = self.snapshot()
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                bump_release.apply(self.root, "1.2.3")
            self.assertEqual(before, self.snapshot())
            path.write_text(text)

    def test_preserves_history_policy_dependencies_and_unrelated_versions(self):
        self.configure("rust")
        readme = self.root / "README.md"
        original = readme.read_text()
        history = ('\nHistorical release v0.1.0; dependency 0.1.0\n'
                   'Historical response {"protocol":1,"version":"0.1.0"}\n')
        readme.write_text(original + history)
        cargo = self.root / "cli/Cargo.lock"
        cargo.write_text(cargo.read_text() + '\n[[package]]\nname = "third-party"\nversion = "0.1.0"\n')
        manifest = self.root / "cli/Cargo.toml"
        manifest.write_text(manifest.read_text() + 'third-party = "0.1.0"\n')
        policy = self.root / "release-policy.json"
        policy.write_text('{"schema":1,"apple_notarized_versions":["0.1.0"]}\n')
        bump_release.apply(self.root, "0.2.0")
        after = readme.read_text()
        # Only the live CLI response example changes, not release commands,
        # upstream links, dependency-manager examples or historical observations.
        self.assertEqual(after, original.replace('"version":"0.1.0"', '"version":"0.2.0"') + history)
        self.assertIn('name = "third-party"\nversion = "0.1.0"', cargo.read_text())
        self.assertIn('third-party = "0.1.0"', manifest.read_text())
        self.assertIn('["0.1.0"]', policy.read_text())
        self.assertEqual(json.loads((self.root / "package.json").read_text())["tool"]["version"], "20.7")

    def test_injected_go_version_assignment(self):
        self.configure()
        source = self.root / "cli/main.go"
        source.write_text(source.read_text().replace(
            'fmt.Println(`{"protocol":1,"version":"0.1.0"}`)',
            'fmt.Printf(`{"protocol":1,"version":"%s"}`, version)').replace(
                "func main()", 'var version string = "0.1.0"\n\nfunc main()'))
        bump_release.apply(self.root, "2.3.4")
        self.assertIn('var version string = "2.3.4"', source.read_text())
        self.assertIn('"version":"%s"', source.read_text())

    def test_rust_cargo_package_version_injection(self):
        self.configure("rust")
        source = self.root / "cli/src/main.rs"
        source.write_text(source.read_text().replace(
            'println!(r#"{{"protocol":1,"version":"0.1.0"}}"#);',
            'println!(r#"{{"protocol":1,"version":"{}"}}"#, env!("CARGO_PKG_VERSION"));'))
        before = source.read_bytes()
        result = bump_release.apply(self.root, "2.3.4")
        self.assertEqual(before, source.read_bytes())
        self.assertNotIn("cli/src/main.rs", result["changed_paths"])
        self.assertIn('version = "2.3.4"', (self.root / "cli/Cargo.toml").read_text())

    def test_cpp_constant_and_cmake_project_version(self):
        self.configure("cpp")
        source = self.root / "cli/main.cpp"
        source.write_text('constexpr auto kVersion = "0.1.0";\n' + source.read_text().replace(
            'R"({"protocol":1,"version":"0.1.0"})"',
            'R"({"protocol":1,"version":")" << kVersion << R"("})"'))
        cmake = self.root / "cli/CMakeLists.txt"
        cmake.write_text(cmake.read_text().replace(
            "project(case-cli LANGUAGES CXX)", "project(case-cli VERSION 0.1.0 LANGUAGES CXX)")
                        + '\nset(CLI_VERSION "0.1.0")\n')
        bump_release.apply(self.root, "2.3.4")
        self.assertIn('kVersion = "2.3.4"', source.read_text())
        self.assertIn("project(case-cli VERSION 2.3.4 LANGUAGES CXX)", cmake.read_text())
        self.assertIn('set(CLI_VERSION "2.3.4")', cmake.read_text())
        self.assertIn("VERSION 3.16", cmake.read_text())

    def test_malformed_contract_and_duplicate_metadata_fail_without_writes(self):
        self.configure()
        for relative, edit in (
                ("template.json", lambda text: text.replace('"version": "0.1.0"',
                                                           '"version": "0.1.0", "version": "0.1.0"')),
                ("tests/host/contract.json", lambda text: text.replace(
                    '\\"protocol\\":1,\\"version\\":\\"0.1.0\\"', 'not json')),
                ("tests/cli-contract.json", lambda text: text.replace(
                    '"version": "$VERSION"', '"version": "bad"'))):
            path = self.root / relative
            text = path.read_text()
            path.write_text(edit(text))
            before = self.snapshot()
            with self.subTest(relative=relative), self.assertRaises(ValueError):
                bump_release.apply(self.root, "2.3.4")
            self.assertEqual(before, self.snapshot())
            path.write_text(text)

    def test_cli_outputs_json_changed_paths_and_github_outputs(self):
        self.configure()
        output = self.root / "github-output"
        env = dict(os.environ, GITHUB_OUTPUT=str(output))
        command = [sys.executable, str(ROOT / "scripts/bump_release.py"), "--root", str(self.root)]
        next_result = subprocess.run(command + ["next", "--mode", "minor"], env=env,
                                     capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(next_result.stdout)["version"], "0.2.0")
        applied = subprocess.run(command + ["apply", "--version", "0.2.0", "--stage"], env=env,
                                 capture_output=True, text=True, check=True)
        result = json.loads(applied.stdout)
        self.assertTrue(result["changed_paths"])
        lines = output.read_text().splitlines()
        self.assertIn("version=0.2.0", lines)
        self.assertIn("tag=0.2.0", lines)
        self.assertFalse(any(line.startswith("tag=v") for line in lines))
        self.assertEqual(json.loads(next(line.split("=", 1)[1] for line in lines
                                       if line.startswith("changed_paths="))), result["changed_paths"])
        self.assertEqual(self.git("diff", "--cached", "--name-only").splitlines(), result["changed_paths"])

    def test_missing_and_symlink_surfaces_fail_without_writes(self):
        self.configure()
        source = self.root / "cli/main.go"
        content = source.read_bytes()
        source.unlink()
        before = self.snapshot()
        with self.assertRaises(ValueError):
            bump_release.apply(self.root, "1.0.0")
        self.assertEqual(before, self.snapshot())
        source.symlink_to(self.root / "README.md")
        before = self.snapshot()
        with self.assertRaises(ValueError):
            bump_release.apply(self.root, "1.0.0")
        self.assertEqual(before, self.snapshot())
        source.unlink()
        source.write_bytes(content)


if __name__ == "__main__":
    unittest.main()
