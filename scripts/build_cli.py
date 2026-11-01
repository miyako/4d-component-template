#!/usr/bin/env python3
"""Build only the configured CLI with the native host toolchain and test its protocol."""
import argparse
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess

from ci_config import ROOT, TARGETS, load_config


def native_target():
    system = platform.system()
    machine = platform.machine().lower()
    architecture = {"x86_64": "x64", "amd64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if system == "Darwin" and architecture in ("x64", "arm64"):
        # A translated x86 process on ARM is not a native Intel runner.
        translated = subprocess.run(
            ["sysctl", "-in", "sysctl.proc_translated"], capture_output=True, text=True, check=False)
        if translated.stdout.strip() == "1":
            raise ValueError("Rosetta translation is not a native build host")
        return "macos-" + architecture
    if system == "Windows" and architecture == "x64":
        if os.environ.get("PROCESSOR_ARCHITEW6432", "").lower() in ("arm64", "aarch64"):
            raise ValueError("Windows ARM emulation is not a native x64 build host")
        return "windows-x64"
    raise ValueError(f"unsupported native host: {system}/{machine}")


def smoke_test(executable, version):
    def check(arguments, status, stdout, stderr):
        result = subprocess.run([str(executable), *arguments], capture_output=True, timeout=20)
        if (result.returncode, result.stdout, result.stderr) != (status, stdout, stderr):
            raise ValueError(f"CLI protocol smoke test failed for {arguments!r}: {result!r}")

    def line(value):
        return (json.dumps(value, ensure_ascii=False, separators=(",", ":")) + "\n").encode("utf-8")

    check(["--version"], 0, line({"protocol": 1, "version": version}), b"")
    for name in ("World", "世界 café 😀", 'quotes" and \\ slash', "line\nbreak"):
        check(["greet", "--name", name], 0, line({"protocol": 1, "message": f"Hello, {name}!"}), b"")
    error = line({"protocol": 1, "error": {"code": "invalid_arguments",
                 "message": "expected greet --name <non-empty UTF-8 name> or --version"}})
    for arguments in ([], ["unknown"], ["greet", "--name", ""], ["--version", "extra"],
                      ["greet", "--name"], ["greet", "--name", "World", "extra"]):
        check(arguments, 2, b"", error)


def require_toolchain(language):
    if language == "go":
        command, pattern, minimum = ["go", "version"], r"\bgo(\d+)\.(\d+)\.(\d+)\b", (1, 23, 0)
    else:
        command, pattern, minimum = ["rustc", "--version"], r"\brustc (\d+)\.(\d+)\.(\d+)\b", (1, 82, 0)
    output = subprocess.run(command, check=True, capture_output=True, text=True).stdout
    match = re.search(pattern, output)
    if not match or tuple(map(int, match.groups())) < minimum:
        raise ValueError(f"{language} {'.'.join(map(str, minimum))} or newer is required")


def build(root, target, language=None):
    root = Path(root).resolve()
    config = load_config(root, initialized=True, repository=os.environ.get("GITHUB_REPOSITORY"))
    if target not in TARGETS or native_target() != target:
        raise ValueError("requested target does not match the native host architecture")
    selected = config["language"]
    if language is not None and language != selected:
        raise ValueError("requested language does not match template.json")
    source = root / "cli"
    if not source.is_dir():
        raise ValueError("initialized CLI source is missing")
    output = root / "build" / target
    output.mkdir(parents=True, exist_ok=True)
    executable = output / (config["cli"] + (".exe" if target == "windows-x64" else ""))
    executable.unlink(missing_ok=True)
    env = os.environ.copy()
    if target.startswith("macos-"):
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
    if selected == "go":
        require_toolchain("go")
        env.update(CGO_ENABLED="0", GOTOOLCHAIN="local",
                   GOOS="windows" if target == "windows-x64" else "darwin",
                   GOARCH="arm64" if target == "macos-arm64" else "amd64")
        commands = [["go", "build", "-trimpath", "-o", str(executable), "."]]
    elif selected == "rust":
        require_toolchain("rust")
        env.pop("CARGO_BUILD_TARGET", None)
        env["CARGO_TARGET_DIR"] = str(output / "cargo")
        commands = [["cargo", "build", "--release", "--locked"]]
    else:
        architecture_options = (
            ["-A", "x64"] if target == "windows-x64" else
            ["-DCMAKE_OSX_ARCHITECTURES=" + ("arm64" if target == "macos-arm64" else "x86_64")])
        commands = [
            ["cmake", "-S", str(source), "-B", str(output / "cmake"),
             "-DCMAKE_BUILD_TYPE=Release", "-DCMAKE_CXX_STANDARD=17", "-DCMAKE_CXX_EXTENSIONS=OFF",
             *architecture_options],
            ["cmake", "--build", str(output / "cmake"), "--config", "Release"],
        ]
    for command in commands:
        subprocess.run(command, cwd=source, env=env, check=True, timeout=600)
    if selected == "rust":
        shutil.copyfile(output / "cargo" / "release" / executable.name, executable)
    elif selected == "cpp":
        candidates = [output / "cmake" / executable.name, output / "cmake" / "Release" / executable.name]
        built = next((path for path in candidates if path.is_file()), None)
        if built is None:
            raise ValueError("CMake did not produce the configured executable")
        shutil.copyfile(built, executable)
    executable.chmod(0o755)
    smoke_test(executable, config["version"])
    return executable


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    parser.add_argument("--language", choices=("go", "rust", "cpp"))
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(build(args.root, args.target, args.language))
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        parser.exit(2, f"CLI build failed: {error}\n")


if __name__ == "__main__":
    main()
