#!/usr/bin/env python3
"""Plan stable release versions and update only the destination's version surfaces.

Run with a complete local tag checkout (fetch tags before ``next``). Both commands
print JSON and append version/tag to GITHUB_OUTPUT. ``apply`` additionally emits
changed_paths as a single-line JSON array of repository-relative paths; callers
can pass that array to ``git add --`` without staging unrelated work. This helper
can stage those exact paths with ``apply --stage``. It does not commit, create
tags, fetch, publish, or change signing policy.

New tags equal the version without a v prefix. Legacy vX.Y.Z tags are read only
as stable version baselines during migration; published history is never changed.
"""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys

from ci_config import ROOT, load_config
from initialize import github_repository
from workflow_contract import configuration as workflow_configuration


STABLE = r"(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)\.(?:0|[1-9][0-9]*)"


def parse_json(text):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate JSON metadata key: {key}")
            result[key] = value
        return result
    return json.loads(text, object_pairs_hook=unique)


def stable(version):
    if not isinstance(version, str) or not re.fullmatch(STABLE, version):
        raise ValueError("version must be stable X.Y.Z without leading zeros")
    return tuple(map(int, version.split(".")))


def regular(root, relative):
    path = root / relative
    if not path.is_file() or any(p.is_symlink() for p in (path, *path.parents)):
        raise ValueError(f"version input must be a regular non-symlink file: {relative}")
    return path


def configuration(root, repository=None):
    # Check paths before load_config follows any component metadata.
    for relative in ("template.json", "package.json"):
        parse_json(regular(root, relative).read_text(encoding="utf-8"))
    actual = github_repository(root)
    expected = repository or os.environ.get("GITHUB_REPOSITORY") or actual
    if not expected or not actual:
        raise ValueError("an exact GitHub origin and destination repository are required")
    if expected != actual:
        raise ValueError("destination repository must exactly match the GitHub origin")
    if actual.lower() == "miyako/4d-component-template":
        raise ValueError("cannot bump the original template repository")
    config = load_config(root, initialized=True, repository=expected)
    stable(config["version"])
    component = Path("component") / config["repository"]
    for relative in (
            component / "Project" / (config["repository"] + ".4DProject"),
            component / "Project/Sources/settings.4DSettings",
            component / "Project/Sources/catalog.4DCatalog"):
        regular(root, relative)
    return config


def plan(root, version, repository=None):
    """Validate every surface before returning the complete in-memory write set."""
    root = Path(root).resolve()
    stable(version)
    config = configuration(root, repository)
    old = config["version"]
    updates = {}

    def read(relative):
        return regular(root, relative).read_text(encoding="utf-8")

    def save(relative, before, after):
        if before != after:
            updates[str(relative)] = after

    def literal(relative, pattern, *, required=False, placeholders=()):
        before = read(relative)
        matches = [match for match in re.finditer(pattern, before, re.MULTILINE)
                   if match["version"] not in placeholders]
        if required and not matches:
            raise ValueError(f"missing supported component version surface: {relative}")
        for match in matches:
            if match["version"] != old:
                raise ValueError(f"inconsistent component version in {relative}: {match['version']}")
        after = re.sub(pattern, lambda m: m[0] if m["version"] in placeholders else
                       m[0][:m.start("version") - m.start()] + version
                       + m[0][m.end("version") - m.start():], before, flags=re.MULTILINE)
        save(relative, before, after)
        return len(matches)

    def metadata(relative):
        before = read(relative)
        value = parse_json(before)
        if not isinstance(value, dict) or value.get("version") != old:
            raise ValueError(f"inconsistent component version in {relative}")
        value["version"] = version
        if old != version:
            save(relative, before, json.dumps(value, indent=2, ensure_ascii=False) + "\n")

    for relative in ("template.json", "package.json"):
        metadata(relative)

    # These are protocol examples, not arbitrary SemVer mentions in prose, URLs,
    # dependency manifests, compiler pins, or historical release instructions.
    protocol = r'(?:"protocol"|protocol)\s*:\s*1\s*,\s*(?:"version"|version)\s*:\s*"(?P<version>[^"\r\n]*)"'
    assignment = (
        r'(?i:\b(?:const|var|let|constexpr)\s+'
        r'(?:(?:char\s*\*|std::string_view|auto)\s*)?'
        r'(?:component_?version|cli_?version|kVersion|version)\b'
        r'(?:\s*:\s*[^=\r\n]+|\s+string)?\s*=\s*")(?P<version>[^"\r\n]*)"')
    component = Path("component") / config["repository"]
    feature = config.get("feature_class", "Greeting")
    source = {"go": "cli/main.go", "rust": "cli/src/main.rs", "cpp": "cli/main.cpp"}[config["language"]]
    source_text = read(source)
    placeholders = {"go": ("%s",), "rust": ("{}",), "cpp": (")",)}[config["language"]]
    count = literal(source, protocol, placeholders=placeholders)
    # Combine edits against the original text, rather than losing a protocol edit.
    if re.search(assignment, source_text):
        for match in re.finditer(assignment, source_text):
            if match["version"] != old:
                raise ValueError(f"inconsistent component version in {source}")
        updates[source] = re.sub(assignment, lambda m: m[0].replace('"' + old + '"', '"' + version + '"'),
                                 updates.get(source, source_text))
        if updates[source] == source_text:
            updates.pop(source)
        count += 1
    if not count and not (config["language"] == "rust" and 'env!("CARGO_PKG_VERSION")' in source_text):
        raise ValueError(f"missing supported CLI version surface: {source}")

    if config["language"] == "rust":
        for relative, header in (("cli/Cargo.toml", r"\[package\]"),
                                 ("cli/Cargo.lock", r"\[\[package\]\]")):
            before = read(relative)
            blocks = list(re.finditer(
                r"(?ms)^" + header + r"[ \t]*\r?\n.*?(?=^\[|\Z)", before))
            own = [block for block in blocks if re.search(
                r'^name\s*=\s*"' + re.escape(config["cli"]) + r'"\s*$', block[0], re.MULTILINE)]
            if len(own) != 1:
                raise ValueError(f"expected exactly one CLI package in {relative}")
            block = own[0]
            pattern = r'(?m)^version\s*=\s*"([^"]+)"[ \t]*$'
            values = list(re.finditer(pattern, block[0]))
            if len(values) != 1 or values[0][1] != old:
                raise ValueError(f"inconsistent CLI package version in {relative}")
            changed = re.sub(pattern, lambda m: m[0].replace('"' + old + '"', '"' + version + '"'), block[0])
            save(relative, before, before[:block.start()] + changed + before[block.end():])
    elif config["language"] == "cpp":
        cmake = "cli/CMakeLists.txt"
        literal(cmake, r'(?i:\bproject\(\s*' + re.escape(config["cli"])
                + r'\s+VERSION\s+)(?P<version>[^\s)]+)')
        # Combine independent CMake surfaces in memory if both are present.
        before = read(cmake)
        pattern = (r'(?i:\bset\(\s*(?:COMPONENT_VERSION|CLI_VERSION)\s+")'
                   r'(?P<version>[^"\r\n]*)"')
        for match in re.finditer(pattern, before):
            if match["version"] != old:
                raise ValueError(f"inconsistent component version in {cmake}")
        after = re.sub(pattern, lambda m: m[0].replace('"' + old + '"', '"' + version + '"'),
                       updates.get(cmake, before))
        save(cmake, before, after)

    feature_path = component / "Project/Sources/Classes" / (feature + ".4dm")
    # Adopted features sometimes expose a component version on the constructor.
    literal(feature_path, r'(?i:\bThis\.(?:componentVersion|cliVersion|version)\s*:=\s*")(?P<version>[^"\r\n]*)"')
    literal("tests/host/Project/Sources/Methods/Smoke.4dm",
            r'\.value\.version\s*[#=]\s*"(?P<version>[^"\r\n]+)"', required=True)
    literal("README.md", r"^\|[^\n]*`" + re.escape(config["cli"])
            + r" --version`[^\n]*" + protocol, required=True)
    literal(component / "Documentation/Classes" / (feature + ".md"), protocol, required=True)
    # The independent Python CLI test also contains a literal --version response.
    literal("tests/test_cli.py", protocol, required=True)

    def payload(value, *, placeholder=False):
        if isinstance(value, dict) and "version" in value and type(value.get("protocol")) is int and value["protocol"] == 1:
            if value["version"] == "$VERSION":
                if placeholder:
                    return value
                raise ValueError("host version assertions must contain the concrete version")
            if value["version"] != old:
                raise ValueError("inconsistent protocol version response in contract")
            return dict(value, version=version)
        if isinstance(value, str):
            try:
                decoded = parse_json(value)
            except json.JSONDecodeError as error:
                raise ValueError("malformed version protocol response in contract") from error
            if not isinstance(decoded, dict):
                raise ValueError("version protocol response must be an object")
            changed = payload(decoded, placeholder=placeholder)
            if changed != decoded:
                return json.dumps(changed, separators=(",", ":"), ensure_ascii=False) + (
                    "\n" if value.endswith("\n") else "")
            return value
        raise ValueError("missing protocol/version fields in version contract")

    for relative in ("tests/host/contract.json", "tests/cli-contract.json"):
        before = read(relative)
        contract = parse_json(before)
        if not isinstance(contract, dict) or contract.get("schema") != 1:
            raise ValueError(f"unsupported contract: {relative}")
        seen = 0
        if relative == "tests/host/contract.json":
            for section in ("feature", "execution"):
                assertions = contract[section]["assertions"]
                for assertion in assertions:
                    path = assertion.get("path", "")
                    if path in ("/version/stdout", "/version/value", "/version/value/version",
                                "/renamedExecutable", "/renamedExecutable/stdout"):
                        if "equals" not in assertion:
                            raise ValueError("version host assertions must use exact equals")
                        value = assertion["equals"]
                        if path.endswith("/value/version"):
                            if value != old:
                                raise ValueError("inconsistent host version assertion")
                            assertion["equals"] = version
                        elif path == "/renamedExecutable":
                            assertion["equals"] = dict(value, stdout=payload(value["stdout"]))
                        else:
                            assertion["equals"] = payload(value)
                        seen += 1
        else:
            for case in contract["cases"]:
                if case.get("args") == ["--version"]:
                    case["stdout"] = payload(case["stdout"], placeholder=True)
                    seen += 1
        if not seen:
            raise ValueError(f"missing exact version contract assertions: {relative}")
        if contract != parse_json(before):
            save(relative, before, json.dumps(contract, indent=2, ensure_ascii=False) + "\n")
    for surface in workflow_configuration(root)["version_surfaces"]:
        relative = surface["path"]
        before = updates.get(relative, read(relative))
        if surface["kind"] == "json-pointer":
            value = parse_json(before)
            current = value
            tokens = [token.replace("~1", "/").replace("~0", "~")
                      for token in surface["pointer"][1:].split("/")]
            for token in tokens[:-1]:
                if not isinstance(current, dict) or token not in current:
                    raise ValueError("missing version JSON pointer: " + relative)
                current = current[token]
            if not isinstance(current, dict) or current.get(tokens[-1]) != old:
                raise ValueError("inconsistent version JSON pointer: " + relative)
            current[tokens[-1]] = version
            after = before if old == version else json.dumps(value, indent=2, ensure_ascii=False) + "\n"
        else:
            prefix, suffix = surface["prefix"], surface["suffix"]
            pattern = re.escape(prefix) + r"(?P<version>[^\r\n]*?)" + re.escape(suffix)
            matches = list(re.finditer(pattern, before))
            if len(matches) != surface["count"] or any(match["version"] != old for match in matches):
                raise ValueError("inconsistent literal version surface: " + relative)
            after = re.sub(pattern, lambda match: prefix + version + suffix, before)
        save(relative, before, after)
    return config, updates


def next_version(root, mode, repository=None, *, tags=None):
    """Increment the higher of synchronized source and stable release history."""
    config, _ = plan(root, configuration(Path(root).resolve(), repository)["version"], repository)
    if mode not in ("patch", "minor", "major"):
        raise ValueError("mode must be patch, minor, or major")
    if tags is None:
        result = subprocess.run(["git", "tag", "--list"], cwd=root, check=True,
                                capture_output=True, text=True, encoding="utf-8")
        tags = result.stdout.splitlines()
    if not isinstance(tags, (list, tuple)) or not all(isinstance(tag, str) for tag in tags):
        raise ValueError("tags must be a list of tag names")
    releases = [stable(tag.removeprefix("v")) for tag in tags
                if re.fullmatch("v?" + STABLE, tag)]
    base = max([stable(config["version"]), *releases])
    major, minor, patch = base
    value = {"patch": (major, minor, patch + 1), "minor": (major, minor + 1, 0),
             "major": (major + 1, 0, 0)}[mode]
    version = ".".join(map(str, value))
    return {"version": version, "tag": version}


def apply(root, version, repository=None, *, stage=False):
    root = Path(root).resolve()
    _, updates = plan(root, version, repository)
    for relative, content in updates.items():
        (root / relative).write_text(content, encoding="utf-8")
    if stage and updates:
        subprocess.run(["git", "add", "--", *sorted(updates)], cwd=root, check=True,
                       capture_output=True, text=True, encoding="utf-8")
    return {"version": version, "tag": version, "changed_paths": sorted(updates)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository", help="exact owner/name; defaults to GITHUB_REPOSITORY or origin")
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("next").add_argument("--mode", choices=("patch", "minor", "major"), required=True)
    applier = commands.add_parser("apply")
    applier.add_argument("--version", required=True)
    applier.add_argument("--stage", action="store_true", help="git add only the validated changed paths")
    args = parser.parse_args()
    try:
        result = (next_version(args.root, args.mode, args.repository) if args.command == "next"
                  else apply(args.root, args.version, args.repository, stage=args.stage))
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
                for key, value in result.items():
                    stream.write(f"{key}={json.dumps(value) if isinstance(value, list) else value}\n")
        print(json.dumps(result, ensure_ascii=False))
    except (ValueError, OSError, KeyError, TypeError, subprocess.CalledProcessError) as error:
        parser.exit(2, f"bump_release: {error}\n")


if __name__ == "__main__":
    main()
