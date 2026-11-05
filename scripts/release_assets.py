#!/usr/bin/env python3
"""Verify downloaded accepted assets before creating a release tag and publication."""
import argparse
from pathlib import Path
import re
import subprocess

from build_provenance import commit, sha256, source_digest
from ci_config import ROOT, TARGETS, load_config
from release_ref import create_tag as create_release_tag, verify as verify_tag
from sign_release import release_policy, submission_uuid
from test_4d import _read_json, validate_status


def verify_signing_proof(root, config, revision, compile_input, unsigned_hash, assets):
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("signing proof requires the normalized release SHA")
    proof = _read_json(Path(root) / "dist" / (config["repository"] + "-signing.json"))
    hashes = {asset["path"]: asset["sha256"] for asset in assets}
    prefix = "dist/" + config["repository"]
    if (not isinstance(proof, dict) or type(proof.get("schema")) is not int or proof["schema"] != 1
            or proof.get("version") != config["version"] or proof.get("sourceSHA") != revision
            or proof.get("releaseTag") != config["version"]
            or proof.get("unsignedCompileInputSHA256") != compile_input
            or proof.get("unsignedZIPHashSHA256") != unsigned_hash
            or proof.get("hostValidation") != "required-after-signing"):
        raise ValueError("signing proof does not match the accepted release provenance")
    notary, dmg, archive = (proof.get(name) for name in ("notarization", "dmg", "zip"))
    if (not isinstance(notary, dict) or notary.get("status") != "Accepted"
            or not isinstance(dmg, dict) or dmg.get("stapled") is not True
            or dmg.get("validated") is not True or dmg.get("sha256") != hashes.get(prefix + ".dmg")
            or not isinstance(archive, dict) or archive.get("sha256") != hashes.get(prefix + ".zip")
            or archive.get("stapled") is not False or archive.get("notarizedViaDMG") is not True
            or archive.get("origin") != "final-mounted-accepted-DMG"):
        raise ValueError("signing proof requires Accepted notarization, stapled DMG and final-mounted ZIP hashes")
    submission_uuid(notary.get("submissionUUID"))
    signed = proof.get("signedFiles")
    if (not isinstance(signed, list) or not signed
            or any(not isinstance(entry, dict) or not isinstance(entry.get("path"), str)
                   or entry.get("verified") is not True for entry in signed)):
        raise ValueError("signing proof requires verified CLI and native Libraries")
    paths = [entry["path"] for entry in signed]
    cli = "Resources/bin/macOS/" + config["cli"]
    if (len(set(paths)) != len(paths)
            or not {cli, "Libraries/lib4d-arm64.dylib"} <= set(paths)
            or any(path != cli and (not path.startswith("Libraries/")
                   or any(token in ("", ".", "..") for token in path.split("/"))
                   or "\\" in path or ":" in path) for path in paths)):
        raise ValueError("signing proof paths must identify the configured CLI and native Libraries")
    return proof


def verify_assets(root, repository, tag, revision, apple_signing=False):
    root = Path(root).resolve()
    config = load_config(root, initialized=True, repository=repository, tag=tag)
    if release_policy(root) and not apple_signing:
        raise ValueError("publication cannot downgrade the version signing policy")
    if not isinstance(revision, str) or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("asset verification requires the normalized release SHA")
    if commit(root) != revision:
        raise ValueError("publication checkout must match the resolved release SHA")
    evidence = root / "dist" / (config["repository"] + ".acceptance.json")
    if not evidence.is_file() or any(path.is_symlink() for path in (evidence, *evidence.parents)):
        raise ValueError("regular adjacent acceptance evidence is required")
    report = _read_json(evidence)
    if (not isinstance(report, dict) or type(report.get("schema")) is not int or report["schema"] != 1
            or report.get("finished") is not True or report.get("result") != "partial"
            or report.get("scope") != "hosted" or report.get("commit") != revision
            or report.get("configuration") != config):
        raise ValueError("acceptance evidence must identify the exact completed release inputs")
    steps = report.get("steps")
    if not isinstance(steps, dict):
        raise ValueError("acceptance steps are missing")

    def passed(name):
        step = steps.get(name)
        if not isinstance(step, dict) or step.get("status") != "passed":
            raise ValueError("required acceptance step did not pass: " + name)
        return step.get("details")

    contract = _read_json(root / "tests/host/contract.json")
    validate_status(passed("source_host"), contract, False)
    validate_status(passed("compiled_host"), contract, True)
    for name in ("assembly", "package"):
        passed(name)
    compiled = passed("compile")
    if (not isinstance(compiled, dict) or compiled.get("success") is not True
            or not isinstance(compiled.get("targets"), list)
            or set(compiled["targets"]) != {"x86_64_generic", "arm64_macOS_lib"}
            or any(not isinstance(compiled.get(field), str)
                   or not re.fullmatch(r"[0-9a-f]{64}", compiled[field])
                   for field in ("input_sha256", "output_sha256"))):
        raise ValueError("both compiler targets and input/output provenance are required")
    source = source_digest(root)
    for target in TARGETS:
        manifest = passed("cli_test_" + target)
        if (not isinstance(manifest, dict) or manifest.get("target") != target
                or manifest.get("execution") != "passed" or manifest.get("commit") != revision
                or manifest.get("source_sha256") != source):
            raise ValueError("native build evidence does not match the release source: " + target)
    name = config["repository"]
    expected = ["dist/" + name + ".zip"]
    if apple_signing:
        passed("signing")
        passed("signing_proof")
        validate_status(passed("unsigned_compiled_host"), contract, True)
        expected += ["dist/" + name + ".dmg", "dist/" + name + "-signing.json"]
    elif not isinstance(steps.get("signing"), dict) or steps["signing"].get("status") != "not_run":
        raise ValueError("unsigned publication must not conceal signing evidence")
    assets = report.get("assets")
    if (not isinstance(assets, list) or len(assets) != len(expected)
            or not all(isinstance(asset, dict) for asset in assets)
            or [asset.get("path") for asset in assets] != expected
            or report.get("artifact") != assets[0]):
        raise ValueError("acceptance evidence does not list the exact policy-required assets")
    paths = []
    for asset in assets:
        path = root / asset["path"]
        if (type(asset.get("bytes")) is not int or asset["bytes"] <= 0
                or not isinstance(asset.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", asset["sha256"])
                or not path.is_file() or any(item.is_symlink() for item in (path, *path.parents))
                or path.stat().st_size != asset["bytes"] or sha256(path) != asset["sha256"]):
            raise ValueError("downloaded asset does not match accepted bytes: " + path.name)
        paths.append(path)
    if apple_signing:
        unsigned = report.get("unsigned_artifact")
        if (not isinstance(unsigned, dict) or unsigned.get("path") != expected[0]
                or not isinstance(unsigned.get("sha256"), str)
                or not re.fullmatch(r"[0-9a-f]{64}", unsigned["sha256"])):
            raise ValueError("unsigned ZIP provenance is required before signing")
        proof = verify_signing_proof(
            root, config, revision, compiled["input_sha256"], unsigned["sha256"], assets)
        if passed("signing_proof") != proof:
            raise ValueError("accepted signing proof differs from the downloaded proof")
    if {path.name for path in evidence.parent.iterdir()} != {
            path.name for path in (*paths, evidence)}:
        raise ValueError("release artifact directory contains unvalidated assets")
    return [*paths, evidence]


def publish(root, repository, tag, revision, apple_signing=False, *, create_tag=False):
    assets = verify_assets(root, repository, tag, revision, apple_signing)
    if create_tag:
        create_release_tag(root, repository, tag, revision)
    else:
        verify_tag(root, tag, revision)
    notes = (
        "Compiled component with universal macOS and x64 Windows CLI resources. "
        "Class/method source is excluded; the exact final ZIP passed compiled-host acceptance. "
        + ("macOS CLI and native libraries are Developer ID signed; the DMG is notarized and stapled. "
           "The dependency-manager ZIP was repacked from that final mounted DMG. "
           if apple_signing else "Unsigned release; no Apple credentials were used. ")
        + "Adjacent acceptance evidence binds the assets, source revision, native manifests and host reports. "
        "Native Intel/Windows 4D and installed-release download checks remain separate observations.")
    subprocess.run(["gh", "release", "create", tag, *(str(path) for path in assets),
                    "--repo", repository, "--verify-tag", "--title", tag, "--notes", notes],
                   cwd=root, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--require-apple-signing", action="store_true")
    parser.add_argument("--publish", action="store_true",
                        help="publish verified assets; default only verifies without creating tags/releases")
    parser.add_argument("--create-tag", action="store_true",
                        help="create a new main-only version tag after asset verification; requires --publish")
    args = parser.parse_args()
    try:
        if args.create_tag and not args.publish:
            raise ValueError("--create-tag requires --publish")
        if args.publish:
            publish(args.root, args.repository, args.tag, args.sha, args.require_apple_signing,
                    create_tag=args.create_tag)
        else:
            for asset in verify_assets(args.root, args.repository, args.tag, args.sha,
                                       args.require_apple_signing):
                print(asset)
    except (ValueError, OSError, TypeError, KeyError, subprocess.SubprocessError) as error:
        parser.exit(2, f"release asset verification/publication failed: {error}\n")


if __name__ == "__main__":
    main()
