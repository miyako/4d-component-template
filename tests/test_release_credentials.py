"""User-run helper tests: synthetic values and an exclusively mocked PATH."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]
HELPER = ROOT / "scripts/set-release-secrets.sh"
ZSH = shutil.which("zsh")
NAMES = {
    "APPLE_DEVELOPER_ID_CERTIFICATE",
    "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
    "KEYCHAIN_PASSWORD",
    "NOTARYTOOL_APPLE_ID",
    "NOTARYTOOL_PASSWORD",
    "NOTARYTOOL_TEAM_ID",
}
TOOLS = ("gh", "security", "openssl", "base64", "tr", "mktemp", "rm")

MOCK = r'''
import base64, json, os, pathlib, sys
tool = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
root = pathlib.Path(os.environ["MOCK_ROOT"])
with (root / "calls.jsonl").open("a") as log:
    log.write(json.dumps([tool, args]) + "\n")
if tool == "security":
    state = json.loads((root / "keychain.json").read_text())
    assert args[args.index("-s") + 1] == "4d-plugin-release"
    name = args[args.index("-a") + 1]
    if args[0] == "find-generic-password":
        if name == os.environ.get("MOCK_INACCESSIBLE_NAME"):
            sys.exit(36)
        if name not in state:
            sys.exit(44)
        print(state[name])
    else:
        assert args[0] == "add-generic-password"
        index = args.index("-w")
        state[name] = args[index + 1] if index + 1 < len(args) else "synthetic-prompt"
        (root / "keychain.json").write_text(json.dumps(state))
elif tool == "gh":
    if args[:2] == ["auth", "status"]:
        sys.exit(int(os.environ.get("MOCK_AUTH_FAILURE", "0")))
    if args[:2] == ["secret", "set"]:
        value = sys.stdin.read()
        assert value
        with (root / "uploads.jsonl").open("a") as log:
            log.write(json.dumps([args[2], args[4], value]) + "\n")
    else:
        assert args[:2] == ["secret", "list"]
elif tool == "openssl":
    data = sys.stdin.read()
    if args[0] == "pkcs12":
        mode = os.environ.get("MOCK_CERT_MODE", "valid")
        path = pathlib.Path(args[args.index("-in") + 1])
        assert path.read_bytes() == b"synthetic-p12"
        assert path.stat().st_mode & 0o077 == 0
        if mode == "invalid" or (mode == "legacy" and "-legacy" not in args):
            sys.exit(1)
        print("synthetic-certificate")
    else:
        assert args[0] == "x509"
        if not data:
            sys.exit(1)
        print("subject=synthetic Developer ID Application\nnotAfter=synthetic expiry")
elif tool == "base64":
    if os.environ.get("MOCK_ENCODING_FAILURE") == "1":
        sys.exit(1)
    if args == ["-D"]:
        sys.stdout.buffer.write(base64.b64decode(sys.stdin.buffer.read(), validate=False))
    else:
        assert args[0] == "-i"
        print(base64.b64encode(pathlib.Path(args[1]).read_bytes()).decode())
elif tool == "tr":
    assert args == ["-d", "\\n"]
    sys.stdout.write(sys.stdin.read().replace("\n", ""))
elif tool == "mktemp":
    path = root / "decoded.p12"
    path.touch(mode=0o600)
    print(path)
elif tool == "rm":
    assert args == ["-f", str(root / "decoded.p12")]
    (root / "decoded.p12").unlink(missing_ok=True)
'''


@unittest.skipUnless(ZSH, "zsh unavailable; mock helper execution not_run")
class ReleaseCredentialHelperTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.bin = self.root / "bin"
        self.bin.mkdir()
        for tool in TOOLS:
            path = self.bin / tool
            path.write_text(f"#!{sys.executable}\n" + MOCK)
            path.chmod(0o755)
        self.state = {name: "synthetic-" + name for name in NAMES}
        self.state["APPLE_DEVELOPER_ID_CERTIFICATE"] = base64.b64encode(b"synthetic-p12").decode()

    def run_helper(self, repos=("owner/one",), **changes):
        (self.root / "keychain.json").write_text(json.dumps(self.state))
        environment = {
            "PATH": str(self.bin),
            "HOME": str(self.root),
            "MOCK_ROOT": str(self.root),
            "MOCK_CONFIRM": "yes",
            **changes,
        }
        # Override only the interactive builtin; all external commands are mocks.
        result = subprocess.run(
            [ZSH, "-f", "-c",
             'read() { [[ "$MOCK_CONFIRM" == yes ]]; }; helper=$1; shift; source "$helper" "$@"',
             "mock-helper", str(HELPER), *repos],
            env=environment, capture_output=True, text=True, timeout=20,
        )
        self.assertFalse((self.root / "decoded.p12").exists(), "decoded file must be cleaned")
        return result

    def records(self, name):
        path = self.root / name
        return [json.loads(line) for line in path.read_text().splitlines()] if path.exists() else []

    def test_zero_arguments(self):
        result = self.run_helper(repos=())
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("usage:", result.stderr)
        self.assertEqual(self.records("calls.jsonl"), [])

    def test_missing_prerequisites(self):
        for tool in TOOLS:
            with self.subTest(tool=tool):
                path = self.bin / tool
                saved = self.root / tool
                path.rename(saved)
                try:
                    result = self.run_helper()
                    self.assertNotEqual(result.returncode, 0)
                    self.assertIn(f"{tool} is not installed", result.stderr)
                    self.assertEqual(self.records("uploads.jsonl"), [])
                finally:
                    saved.rename(path)

    def test_missing_authentication(self):
        result = self.run_helper(MOCK_AUTH_FAILURE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gh auth login", result.stderr)
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_missing_certificate(self):
        del self.state["APPLE_DEVELOPER_ID_CERTIFICATE"]
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("CERT_P12=", result.stderr)
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_missing_certificate_override(self):
        result = self.run_helper(CERT_P12=str(self.root / "missing.p12"))
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("not found:", result.stderr)
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_inaccessible_keychain_stops_without_prompt_or_writes(self):
        result = self.run_helper(MOCK_INACCESSIBLE_NAME="KEYCHAIN_PASSWORD")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Keychain lookup failed for KEYCHAIN_PASSWORD (status 36)", result.stderr)
        self.assertNotIn("enter KEYCHAIN_PASSWORD", result.stdout)
        self.assertFalse(any(tool == "security" and args[0] == "add-generic-password"
                             for tool, args in self.records("calls.jsonl")))
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_certificate_password_failure_and_legacy_retry(self):
        result = self.run_helper(MOCK_CERT_MODE="invalid")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("cannot be opened", result.stderr)
        calls = [args for tool, args in self.records("calls.jsonl")
                 if tool == "openssl" and args[0] == "pkcs12"]
        self.assertEqual(len(calls), 2)
        self.assertIn("-legacy", calls[1])
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_confirmation_rejection(self):
        result = self.run_helper(MOCK_CONFIRM="no")
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("subject=synthetic", result.stdout)
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_multiple_repositories_reuse_exactly_six_values(self):
        result = self.run_helper(repos=("owner/one", "owner/two"))
        self.assertEqual(result.returncode, 0, result.stderr)
        uploads = self.records("uploads.jsonl")
        self.assertEqual(len(uploads), 12)
        for repo in ("owner/one", "owner/two"):
            self.assertEqual({name for name, target, _ in uploads if target == repo}, NAMES)
        self.assertFalse(any(tool == "security" and args[0] == "add-generic-password"
                             for tool, args in self.records("calls.jsonl")))
        for value in self.state.values():
            self.assertNotIn(value, result.stdout + result.stderr)

    def test_first_time_override_hidden_values_and_legacy_success(self):
        self.state = {}
        certificate = self.root / "user selected.p12"
        certificate.write_bytes(b"synthetic-p12")
        result = self.run_helper(CERT_P12=str(certificate), MOCK_CERT_MODE="legacy")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(self.records("uploads.jsonl")), 6)
        writes = [args for tool, args in self.records("calls.jsonl")
                  if tool == "security" and args[0] == "add-generic-password"]
        self.assertEqual(len(writes), 6)
        self.assertTrue(all(args[-1] == "-w" for args in writes[1:]))

    def test_upload_failure_stops_and_cleans(self):
        (self.bin / "gh").write_text(
            f"#!{sys.executable}\n" + MOCK.replace(
                'value = sys.stdin.read()', 'sys.exit(1)\n        value = sys.stdin.read()'))
        result = self.run_helper()
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(self.records("uploads.jsonl"), [])

    def test_encoding_failure_does_not_replace_certificate(self):
        certificate = self.root / "selected.p12"
        certificate.write_bytes(b"synthetic-p12")
        result = self.run_helper(CERT_P12=str(certificate), MOCK_ENCODING_FAILURE="1")
        self.assertNotEqual(result.returncode, 0)
        self.assertFalse(any(tool == "security" and args[0] == "add-generic-password"
                             for tool, args in self.records("calls.jsonl")))
        self.assertEqual(self.records("uploads.jsonl"), [])


if __name__ == "__main__":
    unittest.main()
