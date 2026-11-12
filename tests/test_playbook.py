"""Check discoverable entry points and local links without installing a skill."""
import json
from pathlib import Path
import re
import unittest
import urllib.parse


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / ".github/skills/4d-cli-component/SKILL.md"


class PlaybookTests(unittest.TestCase):
    def test_skill_has_descriptive_discoverable_frontmatter(self):
        text = SKILL.read_text(encoding="utf-8")
        match = re.match(r"\A---\n(.*?)\n---\n", text, flags=re.DOTALL)
        self.assertIsNotNone(match, "SKILL.md needs YAML frontmatter")
        frontmatter = match[1]
        self.assertRegex(frontmatter, r"(?m)^name: [a-z0-9-]{1,64}\s*$")
        self.assertRegex(frontmatter, r"(?m)^description:")
        for trigger in ("4D", "Go", "Rust", "C++", "tool4d", "namespace", "initializ"):
            self.assertIn(trigger.lower(), frontmatter.lower())
        self.assertIn("AGENTS.md", text)

    def test_local_documentation_links_resolve_inside_repository(self):
        for source in (ROOT / "AGENTS.md", ROOT / "README.md",
                       ROOT / ".github/copilot-instructions.md", SKILL):
            text = source.read_text(encoding="utf-8")
            for target in re.findall(r"\[[^\]]+\]\(([^)]+)\)", text):
                if target.startswith(("https://", "http://", "#")) or "<" in target:
                    continue
                path = urllib.parse.unquote(target.split("#", 1)[0])
                destination = (source.parent / path).resolve()
                with self.subTest(source=source.relative_to(ROOT), target=target):
                    self.assertTrue(destination.is_relative_to(ROOT))
                    self.assertTrue(destination.exists(), "broken local playbook link")

    def test_versioned_public_pin_and_cross_platform_checkout_policy(self):
        tool = json.loads((ROOT / "package.json").read_text())["tool"]
        self.assertEqual(tool["build"], "101905")
        self.assertEqual(len(tool["sha256"]), 64)
        attributes = (ROOT / ".gitattributes").read_text()
        self.assertIn("* text=auto eol=lf", attributes)
        self.assertIn("*.png binary", attributes)

    def test_release_guides_distinguish_prefix_free_semver_from_follow4d(self):
        reference = "https://blog.4d.com/follow-4d-version-a-smarter-way-to-manage-your-dependencies/"
        for source in (ROOT / "AGENTS.md", ROOT / "README.md", SKILL):
            text = source.read_text(encoding="utf-8")
            with self.subTest(source=source.relative_to(ROOT)):
                for required in ("prefix-free", "v0.1.0", "20.2.3", "20R3.2", reference):
                    self.assertIn(required, text)
                self.assertNotIn("--tag v0.1.0", text)
        self.assertIn('"tag": "0.1.0"', (ROOT / "README.md").read_text())

    def test_credential_setup_matches_optional_signed_workflow(self):
        workflow = (ROOT / ".github/workflows/build.yml").read_text()
        names = set(re.findall(r"secrets\.([A-Z_]+)", workflow))
        self.assertEqual(names, {
            "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
            "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
            "NOTARYTOOL_PASSWORD", "CODESIGN_APPLE_ID",
        })
        self.assertNotIn("secrets.", (ROOT / ".github/workflows/ci.yml").read_text())
        guide = (ROOT / "AGENTS.md").read_text()
        for name in names:
            self.assertIn(name, guide)
        for source in (ROOT / "README.md", SKILL):
            text = source.read_text()
            self.assertIn("user-owned-credential-setup-and-reuse", text)
            self.assertIn("scripts/set-release-secrets.sh", text)
            self.assertNotIn("~/.copilot/skills/add-release-secrets-to-repo", text)

    def test_canonical_contract_and_bounded_handoff_are_discoverable(self):
        for source in (ROOT / "AGENTS.md", ROOT / "README.md", SKILL):
            text = source.read_text()
            with self.subTest(source=source):
                self.assertIn("workflow-contract.json", text)
                self.assertIn("scripts/workflow_contract.py", text)
                self.assertIn("tooling/requirements-workflow.txt", text)
        guide = (ROOT / "AGENTS.md").read_text()
        for phrase in ("completion notifications", "one bounded status check",
                       "never select unsigned"):
            self.assertIn(phrase, guide)


if __name__ == "__main__":
    unittest.main()
