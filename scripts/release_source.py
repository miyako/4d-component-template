#!/usr/bin/env python3
"""Source-only version commits and immutable-source Build preflight."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess

from bump_release import STABLE, apply, configuration, next_version, plan, stable
from ci_config import ROOT
from release_ref import available, require_main


def git(root, *arguments):
    return subprocess.run(["git", *arguments], cwd=root, check=True,
                          capture_output=True, text=True, encoding="utf-8").stdout.strip()


def dispatch_source(root, env=None):
    env = os.environ if env is None else env
    ref, revision = env.get("GITHUB_REF", ""), env.get("GITHUB_SHA", "")
    if env.get("GITHUB_EVENT_NAME") != "workflow_dispatch" or not ref.startswith("refs/heads/"):
        raise ValueError("release actions require an explicitly selected branch dispatch")
    git(root, "check-ref-format", ref)
    if not re.fullmatch(r"[0-9a-f]{40}", revision, flags=re.ASCII):
        raise ValueError("dispatch requires a full normalized source SHA")
    if git(root, "rev-parse", "HEAD") != revision:
        raise ValueError("checkout must match the immutable dispatch SHA")
    if git(root, "status", "--porcelain", "--untracked-files=all"):
        raise ValueError("release source checkout must be clean, including the index")
    return ref, revision


def fetch_branch(root, ref):
    remote = "refs/remotes/origin/" + ref.removeprefix("refs/heads/")
    git(root, "fetch", "--no-tags", "origin", "+" + ref + ":" + remote)
    return remote


def bump(root, repository, mode, env=None):
    ref, revision = dispatch_source(root, env)
    remote = fetch_branch(root, ref)
    if git(root, "rev-parse", remote) != revision:
        raise ValueError("selected branch moved since dispatch; run Bump version again")
    result = next_version(root, mode, repository)
    changed = apply(root, result["version"], repository, stage=True)["changed_paths"]
    if not changed:
        raise ValueError("version bump did not change any source metadata")
    git(root, "-c", "user.name=github-actions[bot]", "-c",
        "user.email=41898282+github-actions[bot]@users.noreply.github.com",
        "commit", "-m", "Bump version to " + result["version"])
    git(root, "push", "origin", "HEAD:" + ref)
    return {**result, "source_sha": git(root, "rev-parse", "HEAD"), "branch": ref}


def preflight(root, repository, env=None):
    require_main(env)
    ref, revision = dispatch_source(root, env)
    config = configuration(Path(root).resolve(), repository)
    plan(root, config["version"], repository)
    remote = fetch_branch(root, ref)
    git(root, "merge-base", "--is-ancestor", revision, remote)
    tags = git(root, "tag", "--list").splitlines()
    versions = [stable(tag.removeprefix("v")) for tag in tags
                if re.fullmatch("v?" + STABLE, tag, flags=re.ASCII)]
    if versions and stable(config["version"]) <= max(versions):
        raise ValueError("source version must exceed stable release history; run Bump version first")
    available(root, repository, config["version"])
    return {"source_sha": revision, "release_tag": config["version"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    parser.add_argument("--repository", required=True)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("preflight")
    commands.add_parser("bump").add_argument("--mode", choices=("patch", "minor", "major"), required=True)
    args = parser.parse_args()
    try:
        result = (bump(args.root, args.repository, args.mode) if args.command == "bump"
                  else preflight(args.root, args.repository))
        if os.environ.get("GITHUB_OUTPUT"):
            with Path(os.environ["GITHUB_OUTPUT"]).open("a", encoding="utf-8") as stream:
                for key, value in result.items():
                    stream.write(f"{key}={value}\n")
        print(json.dumps(result))
    except (ValueError, OSError, KeyError, TypeError, subprocess.SubprocessError) as error:
        parser.exit(2, f"release source validation failed: {error}\n")


if __name__ == "__main__":
    main()
