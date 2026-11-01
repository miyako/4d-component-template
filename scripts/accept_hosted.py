#!/usr/bin/env python3
"""Create an inspectable compiled ZIP and evidence without publishing a release."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess

from build_provenance import commit, sha256, verify
from ci_config import ROOT, TARGETS, assemble, load_config, require_tool4d_host
from compile_component import compile_component
from package_component import package, unpack_for_test
from test_4d import test_4d


def accept(root, repository, tool4d, tag=None):
    root = Path(root).resolve()
    output = root / "build/hosted-acceptance.json"
    if any(path.is_symlink() for path in (output, *output.parents)):
        raise ValueError("hosted evidence must not traverse symlinks")
    output.parent.mkdir(parents=True, exist_ok=True)
    report = {
        "schema": 1, "scope": "hosted", "commit": commit(root),
        "host": {"system": platform.system(), "machine": platform.machine()},
        "started_at": datetime.now(timezone.utc).isoformat(),
        "result": "failed", "finished": False, "release_ready": False,
        "steps": {name: {"status": "not_run", "reason": "not exercised"} for name in (
            *("cli_test_" + target for target in TARGETS), "assembly", "source_host",
            "compile", "package", "compiled_host", "native_intel_4d", "windows_4d",
            "signing", "release_download")},
    }

    def save():
        output.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    def step(name, action):
        report["steps"][name] = {"status": "failed", "reason": "step did not complete"}
        save()
        result = action()
        report["steps"][name] = {"status": "passed"}
        if isinstance(result, dict):
            report["steps"][name]["details"] = result
        save()
        return result

    save()
    try:
        config = load_config(root, initialized=True, repository=repository, tag=tag)
        report["configuration"] = config
        require_tool4d_host()
        tool = Path(tool4d).resolve()
        version = subprocess.run([str(tool), "--version"], check=True, capture_output=True,
                                 text=True, timeout=30)
        if not version.stdout.strip():
            raise ValueError("tool4d version is unverified")
        report["tool4d"] = {"version": version.stdout.strip(), "binary_sha256": sha256(tool)}
        for target in TARGETS:
            executable = root / "build" / target / (config["cli"] + (
                ".exe" if target == "windows-x64" else ""))
            manifest = verify(root, target, executable)
            if manifest.get("execution") != "passed":
                raise ValueError("hosted acceptance requires native CLI execution: " + target)
            report["steps"]["cli_test_" + target] = {"status": "passed", "details": manifest}
        step("assembly", lambda: assemble(root))
        source = step("source_host", lambda: test_4d(root, tool))
        (output.parent / "source-host-status.json").write_text(json.dumps(source, indent=2) + "\n")
        step("compile", lambda: compile_component(root, tool))
        archive = step("package", lambda: package(
            root, repository=repository, tag=tag or "v" + config["version"]))
        report["artifact"] = {"path": "dist/" + archive.name, "sha256": sha256(archive),
                              "bytes": archive.stat().st_size}
        unpacked = unpack_for_test(root, archive)
        compiled = step("compiled_host", lambda: test_4d(root, tool, unpacked))
        (output.parent / "compiled-host-status.json").write_text(json.dumps(compiled, indent=2) + "\n")
        if sha256(archive) != report["artifact"]["sha256"]:
            raise ValueError("final ZIP changed during host acceptance")
        report.update(result="partial", finished=True,
                      finished_at=datetime.now(timezone.utc).isoformat(),
                      reason="Verified package; native Intel/Windows 4D and published download remain separate checks")
        save()
        evidence = archive.with_suffix(".acceptance.json")
        if any(path.is_symlink() for path in (evidence, *evidence.parents)):
            raise ValueError("stable hosted evidence must not traverse symlinks")
        evidence.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        return report
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        report.update(result="failed", finished=False, error=str(error))
        save()
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tool4d", type=Path, required=True)
    parser.add_argument("--tag", help="explicit version tag; no tag is created or published")
    args = parser.parse_args()
    try:
        report = accept(args.root, args.repository, args.tool4d, args.tag)
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"hosted acceptance failed (see build/hosted-acceptance.json): {error}\n")
    print(json.dumps({"artifact": report["artifact"], "finished": report["finished"],
                      "release_ready": report["release_ready"]}, indent=2))


if __name__ == "__main__":
    main()
