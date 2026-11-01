#!/usr/bin/env python3
"""Fail-closed Apple signing of a compiled release, notarized through a DMG.

`policy` is secret-free and platform independent; absent policy means unsigned.
`sign` requires macOS GitHub Actions, a matching release tag, and all seven
credentials. It never signs the source component or treats a .4dbase as an app.
Both commands accept --require-apple-signing, which can only upgrade policy.
RELEASE_TAG/RELEASE_SHA override the workflow ref/SHA for manual tag releases;
the checked-out HEAD must equal the resolved release commit.
The resulting ZIP is copied from the accepted, stapled, mounted DMG; the ZIP
itself cannot be stapled. The caller must still run the real compiled host test.
"""
import argparse
import base64
import binascii
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import platform
import plistlib
import re
import shlex
import shutil
import stat
import struct
import subprocess
import sys
import tempfile
import uuid
import zipfile

from ci_config import ROOT, SEMVER, load_config
import package_component


SECRET_NAMES = (
    "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
    "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
    "NOTARYTOOL_PASSWORD", "CODESIGN_APPLE_ID",
)
SECURITY = "/usr/bin/security"
CODESIGN = "/usr/bin/codesign"
HDIUTIL = "/usr/bin/hdiutil"
XCRUN = "/usr/bin/xcrun"
GIT = "/usr/bin/git"
TRUSTED_TOOLS = {SECURITY, CODESIGN, HDIUTIL, XCRUN, GIT}


class SigningError(ValueError):
    pass


class CommandError(SigningError):
    def __init__(self, label, result, secrets):
        self.stdout = result.stdout
        details = redact(result.stderr + "\n" + result.stdout, secrets)
        super().__init__(f"{label}: exit {result.returncode}: {details.strip()}")


def redact(text, secrets):
    values = set(secrets.values())
    certificate = secrets.get("APPLE_DEVELOPER_ID_CERTIFICATE", "")
    if certificate:
        values.add("".join(certificate.split()))
    values.update(json.dumps(value, ensure_ascii=True)[1:-1] for value in tuple(values) if value)
    values.update(json.dumps(value, ensure_ascii=False)[1:-1] for value in tuple(values) if value)
    for value in sorted((value for value in values if value), key=len, reverse=True):
        text = text.replace(value, "[REDACTED]")
    return text


def release_policy(root=ROOT):
    config = load_config(root, initialized=True)
    path = Path(root) / "release-policy.json"
    if not path.exists() and not path.is_symlink():
        return False
    if path.is_symlink() or not path.is_file():
        raise SigningError("release-policy.json must be a regular file")
    policy = json.loads(path.read_text(encoding="utf-8"))
    if (not isinstance(policy, dict)
            or set(policy) != {"schema", "apple_notarized_versions"}
            or type(policy["schema"]) is not int or policy["schema"] != 1
            or not isinstance(policy["apple_notarized_versions"], list)):
        raise SigningError("invalid release-policy.json schema")
    versions = policy["apple_notarized_versions"]
    if (any(not isinstance(version, str) or not re.fullmatch(SEMVER, version, re.ASCII)
            for version in versions) or len(set(versions)) != len(versions)):
        raise SigningError("invalid apple_notarized_versions")
    return config["version"] in versions


def policy_command(root=ROOT, env=None, *, require_apple_signing=False):
    env = os.environ if env is None else env
    enabled = release_policy(root) or require_apple_signing
    if env.get("GITHUB_OUTPUT"):
        with Path(env["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as output:
            output.write("apple_signing=" + str(enabled).lower() + "\n")
    print("apple-notarized" if enabled else "unsigned")
    return enabled


def credentials(env):
    missing = [name for name in SECRET_NAMES if not env.get(name, "").strip()]
    if missing:
        raise SigningError("missing required credentials: " + ", ".join(missing))
    secrets = {name: env[name] for name in SECRET_NAMES}
    if secrets["CODESIGN_APPLE_ID"].strip() == "-":
        raise SigningError("ad-hoc signing identity is prohibited")
    return secrets


class Commands:
    """No command line or unredacted child diagnostic is ever printed."""

    def __init__(self, env, secrets):
        self.secrets = secrets
        self.env = {key: value for key, value in env.items() if key not in SECRET_NAMES}
        self.env["PATH"] = "/usr/bin:/bin:/usr/sbin:/sbin"

    def run(self, label, args, timeout=120, *, cwd=None):
        if not args or args[0] not in TRUSTED_TOOLS:
            raise SigningError("untrusted signing tool")
        try:
            result = subprocess.run(
                [str(arg) for arg in args], env=self.env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
                encoding="utf-8", errors="replace", timeout=timeout, check=False,
                cwd=cwd,
            )
        except (OSError, subprocess.SubprocessError):
            # TimeoutExpired and CalledProcessError stringify the secret argv.
            raise SigningError(label + ": tool launch failed or timed out") from None
        if result.returncode:
            raise CommandError(label, result, self.secrets)
        return result.stdout, result.stderr


def certificate_bytes(secrets):
    try:
        data = base64.b64decode(
            "".join(secrets["APPLE_DEVELOPER_ID_CERTIFICATE"].split()), validate=True)
    except (ValueError, binascii.Error):
        raise SigningError("certificate: invalid base64 PKCS#12 input") from None
    if not data:
        raise SigningError("certificate: empty PKCS#12 input")
    return data


class Keychain:
    def __init__(self, commands, scratch, secrets):
        self.commands = commands
        self.secrets = secrets
        self.path = scratch / ("signing-" + uuid.uuid4().hex + ".keychain-db")
        self.p12 = scratch / "certificate.p12"
        self.previous = None
        self.created = False

    def prepare(self, data):
        fd = os.open(self.p12, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as output:
            output.write(data)
        out, _ = self.commands.run("keychain list", [SECURITY, "list-keychains", "-d", "user"])
        self.previous = shlex.split(out)
        password = self.secrets["KEYCHAIN_PASSWORD"]
        # A tool failure can occur after it has created the keychain on disk.
        self.created = True
        self.commands.run("keychain create", [SECURITY, "create-keychain", "-p", password, self.path])
        self.commands.run("keychain unlock", [SECURITY, "unlock-keychain", "-p", password, self.path])
        self.commands.run("keychain settings", [SECURITY, "set-keychain-settings", "-lut", "21600", self.path])
        self.commands.run("certificate import", [
            SECURITY, "import", self.p12, "-k", self.path,
            "-P", self.secrets["APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD"],
            "-T", CODESIGN,
        ])
        self.commands.run("keychain partition ACL", [
            SECURITY, "set-key-partition-list", "-S", "apple-tool:,apple:,codesign:",
            "-s", "-k", password, self.path,
        ])
        self.commands.run("keychain isolate", [SECURITY, "list-keychains", "-d", "user", "-s", self.path])
        self.p12.unlink()

    def cleanup(self):
        errors = []
        if self.previous is not None:
            try:
                self.commands.run("keychain restore", [
                    SECURITY, "list-keychains", "-d", "user", "-s", *self.previous])
            except (ValueError, OSError) as error:
                errors.append(str(error))
        if self.created:
            try:
                self.commands.run("keychain delete", [SECURITY, "delete-keychain", self.path])
            except (ValueError, OSError) as error:
                errors.append(str(error))
        try:
            self.p12.unlink(missing_ok=True)
        except OSError as error:
            errors.append("certificate cleanup: " + str(error))
        return errors


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


@contextmanager
def private_workspace(build):
    temporary = tempfile.TemporaryDirectory(prefix="apple-signing-", dir=build)
    scratch = Path(temporary.name)
    failure = None
    cleanup = None
    try:
        scratch.chmod(0o700)
        yield scratch
    except Exception as error:
        failure = error
    finally:
        try:
            temporary.cleanup()
        except OSError as error:
            cleanup = "signing workspace cleanup: " + str(error)
    if failure or cleanup:
        raise SigningError("; ".join(([str(failure)] if failure else []) + ([cleanup] if cleanup else [])))


def snapshot(base):
    if base.is_symlink() or not base.is_dir():
        raise SigningError("package root must be a regular directory")
    entries = {".": (None, stat.S_IMODE(base.stat().st_mode))}
    for path in sorted(base.rglob("*")):
        if path.is_symlink() or not (path.is_file() or path.is_dir()):
            raise SigningError("package contains nonregular entry")
        relative = path.relative_to(base).as_posix()
        entries[relative] = (path.read_bytes() if path.is_file() else None,
                             stat.S_IMODE(path.stat().st_mode))
    return entries


def assert_immutable(before, after, signed=()):
    if set(before) != set(after):
        raise SigningError("package layout changed")
    for name in before:
        if before[name][1] != after[name][1] or (name not in signed and before[name] != after[name]):
            raise SigningError("immutable package content or permissions changed: " + name)


def macho_architectures(path):
    data = path.read_bytes()
    thin = {b"\xcf\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xcf": ">",
            b"\xce\xfa\xed\xfe": "<", b"\xfe\xed\xfa\xce": ">"}
    cpus = {0x01000007: "x86_64", 0x0100000C: "arm64"}
    try:
        if data[:4] in thin:
            return [cpus[struct.unpack_from(thin[data[:4]] + "I", data, 4)[0]]]
        if data[:4] in (b"\xca\xfe\xba\xbe", b"\xca\xfe\xba\xbf"):
            wide = data[:4] == b"\xca\xfe\xba\xbf"
            count = struct.unpack_from(">I", data, 4)[0]
            if not 1 <= count <= 2:
                raise SigningError("unsupported Mach-O architectures")
            return [cpus[struct.unpack_from(">I", data, 8 + i * (32 if wide else 20))[0]]
                    for i in range(count)]
    except (KeyError, struct.error):
        raise SigningError("invalid Mach-O header") from None
    raise SigningError("native Library is not a supported Mach-O")


def signature(commands, path, team, *, runtime=True, architectures=None):
    commands.run("signature verify", [CODESIGN, "--verify", "--strict", "--all-architectures", path])
    for architecture in architectures or [None]:
        args = [CODESIGN, "--display", "--verbose=4"]
        if architecture:
            args += ["--arch", architecture]
        out, err = commands.run("signature display", [*args, path])
        display = out + "\n" + err
        actual = re.search(r"^TeamIdentifier=(.+)$", display, re.MULTILINE)
        if (not re.search(r"^Authority=Developer ID Application:", display, re.MULTILINE)
                or actual is None or actual.group(1).strip() != team
                or re.search(r"^Signature=adhoc$", display, re.MULTILINE)
                or (runtime and not re.search(r"^CodeDirectory .*flags=.*\(.*\bruntime\b.*\)",
                                              display, re.MULTILINE))
                or not re.search(r"^Timestamp=.+$", display, re.MULTILINE)):
            raise SigningError("signature display: required Developer ID, team, timestamp or runtime missing")


def sign_file(commands, path, identity, keychain, identifier, *, runtime=True):
    args = [CODESIGN, "--force", "--sign", identity, "--timestamp",
            "--keychain", keychain, "--identifier", identifier]
    if runtime:
        args += ["--options", "runtime"]
    commands.run("codesign sign", [*args, path])


def prepare_payload(root, scratch, config, unsigned):
    """Reproduce the unsigned artifact to bind every archive byte to compilation."""
    mirror = scratch / "inputs"
    mirror.mkdir()
    for name in ("template.json", "package.json", "LICENSE"):
        shutil.copy2(root / name, mirror / name)
    component = root / "component" / config["repository"]
    if component.is_symlink() or component.parent.is_symlink():
        raise SigningError("component directories must not be symlinks")
    shutil.copytree(component, mirror / "component" / config["repository"], symlinks=True)
    (mirror / "build").mkdir()
    marker = json.loads((root / "build/compile-status.json").read_text(encoding="utf-8"))
    marker["project"] = "component/" + config["repository"] + "/Project/" + config["repository"] + ".4DProject"
    (mirror / "build/compile-status.json").write_text(json.dumps(marker), encoding="utf-8")
    expected = package_component.package(
        mirror, repository="owner/" + config["repository"], tag="v" + config["version"])
    if expected.read_bytes() != unsigned.read_bytes():
        raise SigningError("unsigned ZIP does not match freshly compiled package inputs")
    unpacked = package_component.unpack_for_test(mirror, unsigned)
    payload = scratch / "payload"
    payload.mkdir()
    staged = payload / unpacked.name
    shutil.copytree(unpacked, staged)
    package_component.validate_resources(staged, config["cli"])
    return payload, staged


def notary_credentials(secrets):
    return ["--apple-id", secrets["NOTARYTOOL_APPLE_ID"],
            "--team-id", secrets["NOTARYTOOL_TEAM_ID"],
            "--password", secrets["NOTARYTOOL_PASSWORD"]]


def submission_uuid(value):
    if not isinstance(value, str):
        raise SigningError("notarytool: missing submission UUID")
    try:
        parsed = uuid.UUID(value)
    except ValueError:
        raise SigningError("notarytool: invalid submission UUID") from None
    if str(parsed) != value.lower():
        raise SigningError("notarytool: invalid submission UUID")
    return str(parsed)


def notarize(commands, dmg, secrets):
    command_error = None
    try:
        out, _ = commands.run("notarytool submit", [
            XCRUN, "notarytool", "submit", dmg, *notary_credentials(secrets),
            "--wait", "--timeout", "30m", "--output-format", "json",
        ], timeout=1860)
    except CommandError as error:
        # A rejected submission may also exit nonzero; still fetch its issues.
        command_error = error
        out = error.stdout
    try:
        response = json.loads(out)
    except json.JSONDecodeError:
        if command_error:
            raise command_error
        raise SigningError("notarytool submit: invalid JSON response") from None
    if not isinstance(response, dict):
        if command_error:
            raise command_error
        raise SigningError("notarytool submit: invalid response")
    try:
        identifier = submission_uuid(response.get("id"))
    except SigningError:
        if command_error:
            raise command_error
        raise
    if response.get("status") != "Accepted":
        details = []
        try:
            log, _ = commands.run("notarytool rejection log", [
                XCRUN, "notarytool", "log", identifier, *notary_credentials(secrets),
                "--output-format", "json",
            ])
            report = json.loads(log)
            for issue in report.get("issues") or []:
                if isinstance(issue, dict):
                    details.append(json.dumps({key: issue[key] for key in
                                               ("severity", "path", "message", "code") if key in issue}))
        except (ValueError, AttributeError):
            # Do not expose a raw private notary log, even on a tool error.
            details.append("rejection log unavailable: retrieval or JSON validation failed")
        prefix = str(command_error) + "; " if command_error else ""
        raise SigningError(redact(prefix + "notarytool: status is not Accepted; " + "; ".join(details), secrets))
    if command_error:
        raise command_error
    commands.run("DMG staple", [XCRUN, "stapler", "staple", dmg])
    commands.run("DMG staple validate", [XCRUN, "stapler", "validate", dmg])
    return identifier


def detach(commands, mount):
    try:
        commands.run("DMG detach", [HDIUTIL, "detach", mount])
        return []
    except SigningError as first:
        try:
            commands.run("DMG force detach", [HDIUTIL, "detach", "-force", mount])
            return []
        except SigningError as second:
            return [str(first), str(second)]


def zip_from_mount(commands, dmg, scratch, staged, signed_paths, secrets, config):
    mount = scratch / "mount"
    mount.mkdir()
    attached = False
    failure = None
    cleanup = []
    destination = scratch / (config["repository"] + ".zip")
    try:
        # Mark before attach: a failed hdiutil invocation can still leave a mount.
        attached = True
        out, _ = commands.run("DMG attach", [
            HDIUTIL, "attach", dmg, "-readonly", "-nobrowse", "-mountpoint", mount, "-plist"])
        info = plistlib.loads(out.encode("utf-8"))
        if (not isinstance(info, dict) or not isinstance(info.get("system-entities"), list)
                or any(not isinstance(entry, dict) for entry in info["system-entities"])):
            raise SigningError("DMG attach: malformed mount report")
        points = [entry.get("mount-point") for entry in info["system-entities"]
                  if entry.get("mount-point")]
        if points != [str(mount)]:
            raise SigningError("DMG attach: unexpected mount point")
        metadata = {".Trashes", ".fseventsd", ".HFS+ Private Directory Data\r", ".Spotlight-V100"}
        if {path.name for path in mount.iterdir()} - metadata != {staged.name}:
            raise SigningError("mounted DMG payload identity mismatch")
        mounted = mount / staged.name
        after = snapshot(mounted)
        assert_immutable(snapshot(staged), after)
        package_component.validate_resources(mounted, config["cli"])
        for relative in signed_paths:
            signature(commands, mounted / relative, secrets["NOTARYTOOL_TEAM_ID"],
                      architectures=macho_architectures(mounted / relative))
        entries = [(staged.name + "/" + name, data, mode)
                   for name, (data, mode) in after.items() if data is not None]
        package_component.write_zip(destination, entries)
        # Exercise the same safe extraction/layout checks as the caller's host test.
        unpacked = package_component.unpack_for_test(scratch / "inputs", destination)
        assert_immutable(after, snapshot(unpacked))
    except (ValueError, OSError, plistlib.InvalidFileException, TypeError) as error:
        failure = error
    finally:
        if attached:
            cleanup = detach(commands, mount)
    if failure or cleanup:
        raise SigningError("; ".join(([str(failure)] if failure else []) + cleanup))
    return destination


def sign_release(root=ROOT, env=None, *, require_apple_signing=False):
    root = Path(root).resolve()
    env = os.environ if env is None else env
    if platform.system() != "Darwin" or env.get("GITHUB_ACTIONS") != "true":
        raise SigningError("sign requires macOS GitHub Actions")
    tag = env.get("RELEASE_TAG") or env.get("GITHUB_REF_NAME")
    source_sha = env.get("RELEASE_SHA") or env.get("GITHUB_SHA")
    if not env.get("GITHUB_REPOSITORY") or not tag:
        raise SigningError("sign requires actual GITHUB_REPOSITORY and release tag")
    config = load_config(root, initialized=True, repository=env["GITHUB_REPOSITORY"],
                         tag=tag)
    if not (release_policy(root) or require_apple_signing):
        raise SigningError("current release is not opted in to Apple notarization")
    secrets = credentials(env)
    data = certificate_bytes(secrets)
    if not isinstance(source_sha, str) or not re.fullmatch(r"[0-9a-fA-F]{40}", source_sha):
        raise SigningError("sign requires the source commit RELEASE_SHA or GITHUB_SHA")
    component = root / "component" / config["repository"]
    package_component.validate_compile(root, component, config["repository"])
    package_component.validate_resources(component, config["cli"])
    unsigned = root / "dist" / (config["repository"] + ".zip")
    if not unsigned.is_file() or unsigned.is_symlink():
        raise SigningError("fresh unsigned compiled ZIP is required")
    unsigned_hash = sha256(unsigned)
    digest = json.loads((root / "build/compile-status.json").read_text())["input_sha256"]
    build = root / "build"
    if build.is_symlink() or (root / "dist").is_symlink():
        raise SigningError("build and dist must not be symlinks")
    commands = Commands(env, secrets)
    head, _ = commands.run("source HEAD", [GIT, "rev-parse", "HEAD"], cwd=root)
    if head.strip().lower() != source_sha.lower():
        raise SigningError("source HEAD does not match the resolved release commit")
    with private_workspace(build) as scratch:
        keychain = Keychain(commands, scratch, secrets)
        failure = None
        cleanup = []
        try:
            payload, staged = prepare_payload(root, scratch, config, unsigned)
            before = snapshot(staged)
            mac = staged / "Resources/bin/macOS" / config["cli"]
            libraries = [path for path in sorted((staged / "Libraries").rglob("*"))
                         if path.is_file()]
            signed = [mac]
            for path in libraries:
                try:
                    macho_architectures(path)
                    signed.append(path)
                except SigningError:
                    if path.suffix in {".dylib", ".so"}:
                        raise
            relative_paths = [path.relative_to(staged).as_posix() for path in signed]
            keychain.prepare(data)
            for path, relative in zip(signed, relative_paths):
                sign_file(commands, path, secrets["CODESIGN_APPLE_ID"], keychain.path,
                          "org.4d." + config["repository"] + "." + relative.replace("/", "."))
                signature(commands, path, secrets["NOTARYTOOL_TEAM_ID"],
                          architectures=macho_architectures(path))
            assert_immutable(before, snapshot(staged), relative_paths)
            package_component.validate_resources(staged, config["cli"])
            dmg = scratch / (config["repository"] + ".dmg")
            commands.run("DMG create", [
                HDIUTIL, "create", "-srcfolder", payload, "-volname", config["repository"],
                "-fs", "HFS+", "-format", "UDZO", dmg,
            ])
            sign_file(commands, dmg, secrets["CODESIGN_APPLE_ID"], keychain.path,
                      "org.4d." + config["repository"] + ".release", runtime=False)
            signature(commands, dmg, secrets["NOTARYTOOL_TEAM_ID"], runtime=False)
            identifier = notarize(commands, dmg, secrets)
            signature(commands, dmg, secrets["NOTARYTOOL_TEAM_ID"], runtime=False)
            final_zip = zip_from_mount(commands, dmg, scratch, staged, relative_paths, secrets, config)
            proof = {
                "schema": 1, "version": config["version"], "sourceSHA": source_sha.lower(),
                "releaseTag": tag,
                "unsignedCompileInputSHA256": digest, "unsignedZIPHashSHA256": unsigned_hash,
                "signedFiles": [{"path": path, "verified": True} for path in relative_paths],
                "notarization": {"status": "Accepted", "submissionUUID": identifier},
                "dmg": {"stapled": True, "validated": True, "sha256": sha256(dmg)},
                "zip": {"sha256": sha256(final_zip), "stapled": False,
                        "notarizedViaDMG": True, "origin": "final-mounted-accepted-DMG"},
                "hostValidation": "required-after-signing",
            }
            proof_file = scratch / (config["repository"] + "-signing.json")
            proof_file.write_text(json.dumps(proof, indent=2) + "\n", encoding="utf-8")
        except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as error:
            failure = error
        finally:
            cleanup = keychain.cleanup()
        if failure or cleanup:
            raise SigningError(redact("; ".join(([str(failure)] if failure else []) + cleanup), secrets))
        if sha256(unsigned) != unsigned_hash:
            raise SigningError("unsigned input ZIP changed during signing")
        artifacts = [(source.name, source.read_bytes(), stat.S_IMODE(source.stat().st_mode))
                     for source in (dmg, proof_file, final_zip)]
    # No intermediate certificate/keychain/mount/workspace remains at delivery.
    pending = []
    try:
        for name, content, mode in artifacts:
            with tempfile.NamedTemporaryFile(prefix=".apple-release-", dir=root / "dist", delete=False) as output:
                pending.append((Path(output.name), root / "dist" / name))
                output.write(content)
                os.fchmod(output.fileno(), mode)
        # Replace ZIP last: the unchanged unsigned ZIP survives any earlier error.
        for source, destination in pending:
            source.replace(destination)
    finally:
        for source, _ in pending:
            source.unlink(missing_ok=True)
    print("Apple notarization Accepted: " + ", ".join("dist/" + name for name, _, _ in artifacts))
    return proof


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("policy", "sign"))
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--require-apple-signing", action="store_true",
                        help="require signing in addition to version policy; never permits a downgrade")
    args = parser.parse_args(argv)
    try:
        if args.command == "policy":
            policy_command(args.root, require_apple_signing=args.require_apple_signing)
        else:
            sign_release(args.root, require_apple_signing=args.require_apple_signing)
    except (ValueError, OSError, TypeError, KeyError, zipfile.BadZipFile) as error:
        secrets = {name: os.environ.get(name, "") for name in SECRET_NAMES}
        print("Apple release signing failed: " + redact(str(error), secrets), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
