#!/usr/bin/env python3
"""Validate the inherited CI, Bump version and Build roles without mutations."""
import argparse
import ast
import json
from pathlib import Path, PurePosixPath
import re
import shlex


ROOT = Path(__file__).resolve().parents[1]
SECRETS = {
    "APPLE_DEVELOPER_ID_CERTIFICATE", "APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD",
    "KEYCHAIN_PASSWORD", "NOTARYTOOL_APPLE_ID", "NOTARYTOOL_TEAM_ID",
    "NOTARYTOOL_PASSWORD", "CODESIGN_APPLE_ID",
}
COMMANDS = {
    "workflow_contract.py": "python scripts/workflow_contract.py",
    "generate_icons.py": "python scripts/generate_icons.py --check",
    "unittest discover": "python -m unittest discover -s tests -v",
    "ci_config.py matrix": "python scripts/ci_config.py matrix",
    "test_cli.py": "python -m unittest discover -s tests -p test_cli.py -v",
    "scripts/build_cli.py": 'python scripts/build_cli.py --target "$CLI_TARGET" --language "$CLI_LANGUAGE"',
    "ci_config.py assemble": "python scripts/ci_config.py assemble",
    "ci_config.py download-tool4d": "python scripts/ci_config.py download-tool4d",
    "release_source.py --repository": 'python scripts/release_source.py --repository "$GITHUB_REPOSITORY" preflight',
    "release_source.py": 'python scripts/release_source.py --repository "$GITHUB_REPOSITORY" bump --mode "$MODE"',
    "ci_config.py validate": 'python scripts/ci_config.py validate --release --tag "$RELEASE_TAG"',
    "pip install -r tooling/requirements-workflow.txt": "python -m pip install -r tooling/requirements-workflow.txt",
    "scripts/release_assets.py": '''
signing=()
if [ "$APPLE_SIGNING" = "true" ]; then signing+=(--require-apple-signing); fi
python scripts/release_assets.py --repository "$GH_REPO" --tag "$RELEASE_TAG" \\
  --sha "$RELEASE_SHA" "${signing[@]}" --create-tag --publish
''',
}
POLICY_PROGRAM = '''
import os, subprocess, sys
arguments = [sys.executable, "scripts/sign_release.py", "policy", "--root", "."]
if os.environ["REQUIRE_APPLE_SIGNING"] == "true":
    arguments.append("--require-apple-signing")
subprocess.run(arguments, check=True)
'''


def shell_tokens(text):
    tokens = shlex.split(text.replace("\\\n", ""), comments=True)
    if tokens and tokens[0] == "python3":
        tokens[0] = "python"
    return tokens


def invocation(step, expected, label):
    require(shell_tokens(step["run"]) == shell_tokens(expected),
            "required executable invocation: " + label)


def require(condition, message):
    if not condition:
        raise ValueError("workflow contract: " + message)


def regular(root, relative):
    path = root / relative
    require(path.is_file() and not any(p.is_symlink() for p in (path, *path.parents)),
            "required regular file: " + str(relative))
    return path


def unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "duplicate configuration key: " + str(key))
        result[key] = value
    return result


def configuration(root):
    value = json.loads(regular(root, "workflow-contract.json").read_text(),
                       object_pairs_hook=unique)
    require(isinstance(value, dict) and set(value) == {"schema", "profile", "version_surfaces"},
            "unsupported configuration fields")
    require(type(value["schema"]) is int and value["schema"] == 1
            and value["profile"] == "cli-universal-v1", "unsupported workflow profile")
    require(isinstance(value["version_surfaces"], list), "version_surfaces must be an array")
    identities = set()
    for surface in value["version_surfaces"]:
        require(isinstance(surface, dict), "version surface must be an object")
        kind = surface.get("kind")
        fields = ({"kind", "path", "pointer"} if kind == "json-pointer"
                  else {"kind", "path", "prefix", "suffix", "count"})
        require(kind in {"json-pointer", "literal"} and set(surface) == fields,
                "unsupported version surface")
        path = surface["path"]
        require(isinstance(path, str) and path and "\\" not in path and ":" not in path
                and not PurePosixPath(path).is_absolute()
                and all(part not in {"", ".", ".."} for part in path.split("/"))
                and path.split("/")[0] not in {".git", ".github", "build", "dist", ".tools"}
                and path not in {"workflow-contract.json", "release-policy.json"},
                "unsafe version surface path")
        if kind == "json-pointer":
            pointer = surface["pointer"]
            require(isinstance(pointer, str) and pointer.startswith("/")
                    and not re.search(r"~(?![01])", pointer), "invalid version JSON pointer")
            identity = (path, kind, pointer)
        else:
            require(all(isinstance(surface[field], str) and surface[field]
                        for field in ("prefix", "suffix"))
                    and type(surface["count"]) is int and surface["count"] > 0,
                    "literal surface requires delimiters and a positive exact count")
            identity = (path, kind, surface["prefix"], surface["suffix"])
        require(identity not in identities, "duplicate version surface")
        identities.add(identity)
    return value


def yaml_document(path):
    try:
        import yaml
    except ImportError as error:
        raise ValueError("install tooling/requirements-workflow.txt before workflow validation") from error

    class Loader(yaml.SafeLoader):
        pass

    Loader.yaml_implicit_resolvers = {
        key: [(tag, regex) for tag, regex in entries
              if tag != "tag:yaml.org,2002:bool"]
        for key, entries in Loader.yaml_implicit_resolvers.items()
    }
    Loader.add_implicit_resolver("tag:yaml.org,2002:bool",
                                 re.compile(r"^(?:true|false)$"), list("tf"))

    def mapping(loader, node):
        require(not any(key.value == "<<" for key, _ in node.value),
                "YAML merge keys are not supported")
        return unique([(loader.construct_object(key), loader.construct_object(value))
                       for key, value in node.value])

    Loader.add_constructor("tag:yaml.org,2002:map", mapping)
    try:
        value = yaml.load(path.read_text(encoding="utf-8"), Loader=Loader)
    except yaml.YAMLError as error:
        raise ValueError("invalid workflow YAML: " + str(error)) from error
    require(isinstance(value, dict), "workflow YAML must be an object")
    return value


def validate(root=ROOT):
    root = Path(root).resolve()
    configuration(root)
    folder = root / ".github/workflows"
    require(folder.is_dir() and not folder.is_symlink(), "missing workflow directory")
    require({p.name for p in folder.iterdir()} == {"ci.yml", "bump-version.yml", "build.yml"},
            "exactly ci.yml, bump-version.yml and build.yml are required")
    documents = {name: yaml_document(regular(root, ".github/workflows/" + name + ".yml"))
                 for name in ("ci", "bump-version", "build")}
    ci, bump, build = documents["ci"], documents["bump-version"], documents["build"]
    require(ci.get("name") == "CI" and bump.get("name") == "Bump version"
            and build.get("name") == "Build", "workflow names must be CI/Bump version/Build")
    ci_trigger = ci.get("on")
    require(isinstance(ci_trigger, dict), "CI triggers must be an object")
    reusable = ci_trigger.get("workflow_call")
    require(isinstance(reusable, dict) and set(reusable) == {"inputs"}, "unexpected reusable CI fields")
    calls = reusable["inputs"]
    require(isinstance(calls, dict) and all(isinstance(value, dict) for value in calls.values()),
            "reusable CI inputs must be objects")
    semantic_trigger = dict(ci_trigger, workflow_call={"inputs": {
        name: {key: value for key, value in fields.items() if key != "description"}
        for name, fields in calls.items()}})
    require(semantic_trigger == {
        "push": {"branches": ["**"]}, "pull_request": None, "workflow_dispatch": None,
        "workflow_call": {"inputs": {
            "source_sha": {"type": "string", "default": ""},
            "release_call": {"type": "boolean", "default": False}}},
    }, "CI triggers/reusable inputs must retain the canonical contract")
    for document in (bump, build):
        trigger = document.get("on")
        require(isinstance(trigger, dict) and set(trigger) == {"workflow_dispatch"},
                "release-facing actions must be manual only")
    bump_inputs = bump["on"]["workflow_dispatch"]["inputs"]
    require(set(bump_inputs) == {"mode"}, "Bump version accepts only mode")
    mode = bump_inputs["mode"]
    require(mode.get("type") == "choice" and mode.get("required") is True
            and mode.get("options") == ["patch", "minor", "major"] and mode.get("default") == "patch",
            "Bump version requires patch/minor/major with default patch")
    inputs = build["on"]["workflow_dispatch"]["inputs"]
    require(set(inputs) == {"require_apple_signing"}, "Build has no tag/version/bump inputs")
    signing = inputs["require_apple_signing"]
    require(signing.get("type") == "boolean" and signing.get("default") is False
            and signing.get("required") is False, "signing input must remain optional escalation")
    require(build.get("concurrency") == {"group": "publish", "cancel-in-progress": False},
            "Build must not cancel an active publication")
    require(bump.get("concurrency") == {
        "group": "bump-version-${{ github.ref }}", "cancel-in-progress": False},
        "serialize source bumps per selected branch")
    expected_jobs = {
        "ci": {"configuration": None, "native": "configuration", "assembly": ["configuration", "native"]},
        "bump-version": {"bump": None},
        "build": {"preflight": None, "native": "preflight", "compile": ["preflight", "native"],
                  "publish": ["preflight", "compile"]},
    }
    for name, document in documents.items():
        require(document.get("permissions") == {"contents": "read"}, "default contents permission must be read")
        jobs = document["jobs"]
        require(set(jobs) == set(expected_jobs[name]), "unsupported job graph: " + name)
        for job_name, job in jobs.items():
            require(job.get("needs") == expected_jobs[name][job_name], "missing mandatory job dependency")
            permissions = ({"contents": "write"} if (name, job_name) in {
                ("bump-version", "bump"), ("build", "publish")} else None)
            require(job.get("permissions") == permissions, "unexpected job write permission")
            require(name == "ci" or "if" not in job, "release jobs cannot bypass acceptance")
            require("continue-on-error" not in job, "job failure bypass prohibited")
            for step in job.get("steps", []):
                require("continue-on-error" not in step, "step failure bypass prohibited")
                if step.get("uses") == "actions/checkout@v4":
                    expected_ref = ("${{ inputs.source_sha || github.sha }}" if name == "ci" else
                                    "${{ github.sha }}" if job_name in {"bump", "preflight"}
                                    else "${{ needs.preflight.outputs.source_sha }}")
                    require(step.get("with", {}).get("ref") == expected_ref, "checkout must use canonical source SHA")
                    if job_name in {"bump", "preflight", "publish"}:
                        require(step["with"].get("fetch-depth") == 0, "release source requires full history")
    native = build["jobs"]["native"]
    require(native.get("uses") == "./.github/workflows/ci.yml"
            and native.get("with") == {"source_sha": "${{ needs.preflight.outputs.source_sha }}", "release_call": True},
            "Build must reuse CI at the dispatch SHA without duplicate host acceptance")

    def command(job, needle, condition=None):
        steps = job["steps"]
        matches = [(index, step) for index, step in enumerate(steps) if needle in step.get("run", "")]
        require(len(matches) == 1, "required unique entry point: " + needle)
        require(matches[0][1].get("if") == condition, "required step cannot be skipped: " + needle)
        if needle in COMMANDS:
            invocation(matches[0][1], COMMANDS[needle], needle)
        return matches[0]

    version = build["jobs"]["preflight"]
    guard = version["steps"][0]
    guard_commands = [tokens for line in guard.get("run", "").splitlines()
                      if (tokens := shell_tokens(line))]
    require(guard.get("if") == "github.ref != 'refs/heads/main'"
            and len(guard_commands) == 2 and guard_commands[0][0] == "echo"
            and guard_commands[1] == ["exit", "1"], "Build requires a fail-closed main guard")
    order = [command(version, needle)[0] for needle in (
        "scripts/workflow_contract.py", "release_source.py --repository",
        "ci_config.py validate", "sign_release.py")]
    require(order == sorted(order), "release preparation order changed")
    require(version["outputs"] == {
        "source_sha": "${{ steps.source.outputs.source_sha }}", "release_tag": "${{ steps.source.outputs.release_tag }}",
        "apple_signing": "${{ steps.signing_policy.outputs.apple_signing }}"},
        "preflight outputs must identify the dispatch SHA/source version/policy")
    source = command(version, "release_source.py --repository")[1]
    require(source.get("id") == "source" and source.get("env") == {"GH_TOKEN": "${{ github.token }}"},
            "preflight must check authenticated remote availability")
    bump_job = bump["jobs"]["bump"]
    require(command(bump_job, "scripts/workflow_contract.py")[0]
            < command(bump_job, "release_source.py")[0], "validate before source mutation")
    require(command(bump_job, "release_source.py")[1].get("env") == {"MODE": "${{ inputs.mode }}"},
            "source-only bump consumes the semantic selector")
    require(command(version, "ci_config.py validate")[1].get("env") == {
        "FOURD_ENABLED": "${{ vars.FOURD_ENABLED }}", "RELEASE_TAG": "${{ steps.source.outputs.release_tag }}"},
        "preflight requires explicit hosted 4D opt-in for the source version")
    for job, allowed in ((bump_job, {"workflow_contract.py", "release_source.py",
                                    "pip install -r tooling/requirements-workflow.txt"}),
                         (version, {"workflow_contract.py", "release_source.py --repository",
                                    "ci_config.py validate", "sign_release.py",
                                    "pip install -r tooling/requirements-workflow.txt"})):
        for step in job["steps"]:
            if step is guard:
                continue
            if "run" in step:
                require(sum(needle in step["run"] for needle in allowed) == 1,
                        "source preparation cannot build, tag, release or dispatch")
            else:
                require(step.get("uses") in {"actions/checkout@v4", "actions/setup-python@v5"},
                        "source preparation may only use checkout and Python setup")
        require(sum(step.get("uses") == "actions/checkout@v4" for step in job["steps"]) == 1,
                "source preparation requires exactly one immutable checkout")
    compile_job = build["jobs"]["compile"]
    require(compile_job["env"].get("RELEASE_SHA") == "${{ needs.preflight.outputs.source_sha }}"
            and compile_job["env"].get("RELEASE_TAG") == "${{ needs.preflight.outputs.release_tag }}",
            "compiler/signing environment must use the version SHA/tag")
    command(compile_job, "ci_config.py validate")
    command(compile_job, "ci_config.py download-tool4d")
    acceptance = [step for step in compile_job["steps"] if "scripts/accept_hosted.py" in step.get("run", "")]
    require(len(acceptance) == 2, "require separate unsigned/signed acceptance branches")
    for step, enabled in zip(acceptance, ("false", "true")):
        require(step.get("if") == "needs.preflight.outputs.apple_signing == '" + enabled + "'",
                "acceptance must follow effective signing policy")
        require(("--require-apple-signing" in step["run"]) == (enabled == "true"),
                "signing cannot be downgraded")
        expected = ('python scripts/accept_hosted.py --repository "$GITHUB_REPOSITORY" '
                    '--tool4d .tools/tool4d.app/Contents/MacOS/tool4d --tag "$RELEASE_TAG"'
                    + (" --require-apple-signing" if enabled == "true" else ""))
        invocation(step, expected, "final package acceptance")
        require(step.get("env", {}) == ({key: "${{ secrets." + key + " }}" for key in SECRETS}
                                       if enabled == "true" else {}), "signing secret contract changed")
    for name, document in documents.items():
        references = re.findall(r"secrets\.([A-Z_]+)", json.dumps(document))
        require(sorted(references) == (sorted(SECRETS) if name == "build" else []),
                "secret references outside the signed acceptance step")
        for job in document["jobs"].values():
            for step in job.get("steps", []):
                text = json.dumps(step)
                require("set-release-secrets.sh" not in text and "gh secret set" not in text,
                        "credential setup is user-owned")
                if step is not acceptance[1]:
                    require("secrets." not in text, "secrets must only reach the gated signing stage")
    publication = command(build["jobs"]["publish"], "scripts/release_assets.py")[1]
    require("--create-tag --publish" in publication["run"]
            and '"$RELEASE_SHA"' in publication["run"], "verify accepted assets before atomic tag/publication")
    require(publication["env"].get("RELEASE_SHA") == "${{ needs.preflight.outputs.source_sha }}"
            and publication["env"].get("RELEASE_TAG") == "${{ needs.preflight.outputs.release_tag }}"
            and publication["env"].get("APPLE_SIGNING") == "${{ needs.preflight.outputs.apple_signing }}",
            "publication environment must use the accepted SHA/tag/policy")
    for needle in ("workflow_contract.py", "generate_icons.py", "unittest discover", "ci_config.py matrix"):
        command(ci["jobs"]["configuration"], needle)
    native_job = ci["jobs"]["native"]
    require(native_job.get("runs-on") == "${{ matrix.runner }}"
            and native_job.get("strategy") == {
                "fail-fast": False, "matrix": "${{ fromJSON(needs.configuration.outputs.matrix) }}"},
            "native jobs must consume the configured target matrix")
    command(native_job, "test_cli.py")
    command(native_job, "scripts/build_cli.py")
    command(ci["jobs"]["assembly"], "ci_config.py assemble")
    for job in (native_job, ci["jobs"]["assembly"]):
        require(job.get("if") == "needs.configuration.outputs.initialized == 'true'",
                "native/assembly jobs must require initialization")
    for name, jobs in documents.items():
        for job_name, job in jobs["jobs"].items():
            if not (name == "ci" and job_name == "native") and "uses" not in job:
                expected_runner = "macos-15" if job_name in {"assembly", "compile"} else "ubuntu-24.04"
                require(job.get("runs-on") == expected_runner, "unsupported runner for the canonical profile")
            for step in job.get("steps", []):
                if step.get("uses") == "actions/download-artifact@v4":
                    require("if" not in step, "mandatory artifact download cannot be skipped")
                run = step.get("run", "")
                require(not re.search(r"\bgh\s+release\s+(?:create|edit|upload)\b|\bgit\s+tag\b", run),
                        "release mutations belong only in the validated publication helper")
    optional = "vars.FOURD_ENABLED == 'true' && github.ref_type != 'tag' && !inputs.release_call"
    host = command(ci["jobs"]["assembly"], "scripts/accept_hosted.py", optional)[1]
    require(host.get("if") == optional, "CI host acceptance must remain opt-in and nonduplicated")
    invocation(host, 'python scripts/accept_hosted.py --repository "$GITHUB_REPOSITORY" '
                     '--tool4d .tools/tool4d.app/Contents/MacOS/tool4d', "CI package acceptance")
    for name, job, artifacts in (
        ("ci", ci["jobs"]["assembly"], {"component-resources", "compiled-component", "component-acceptance-diagnostics"}),
        ("build", compile_job, {"compiled-release", "release-acceptance-diagnostics"}),
    ):
        uploads = {step["with"]["name"]: step for step in job["steps"]
                   if step.get("uses") == "actions/upload-artifact@v4"}
        require(set(uploads) == artifacts, "missing canonical acceptance artifacts")
        for artifact, step in uploads.items():
            if artifact.endswith("diagnostics"):
                require(step.get("if", "").startswith("always()"), "diagnostics must survive failure")
            elif artifact != "component-resources":
                require("dist/*.zip" in step["with"]["path"]
                        and "dist/*.acceptance.json" in step["with"]["path"]
                        and step["with"].get("if-no-files-found") == "error",
                        "accepted ZIP and adjacent evidence are required")
    policy = command(version, "sign_release.py")[1]
    require(policy.get("env") == {"REQUIRE_APPLE_SIGNING": "${{ inputs.require_apple_signing }}"}
            and policy.get("shell") == "python", "manual signing must only escalate policy")
    try:
        require(ast.dump(ast.parse(policy["run"])) == ast.dump(ast.parse(POLICY_PROGRAM)),
                "signing policy must execute the checked escalation-only program")
    except SyntaxError as error:
        raise ValueError("invalid signing policy program") from error
    for job in (ci["jobs"]["configuration"], version, bump_job):
        install = command(job, "pip install -r tooling/requirements-workflow.txt")[0]
        require(install < command(job, "workflow_contract.py")[0],
                "install pinned parser before contract validation")
    for helper in ("workflow_contract.py", "bump_release.py", "release_source.py", "ci_config.py", "build_cli.py",
                   "accept_hosted.py", "sign_release.py", "release_assets.py", "release_ref.py",
                   "set-release-secrets.sh"):
        regular(root, "scripts/" + helper)
    if (root / "release-policy.json").exists():
        regular(root, "release-policy.json")
    regular(root, "tooling/requirements-workflow.txt")
    return {"schema": 1, "profile": "cli-universal-v1", "status": "passed"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=ROOT)
    args = parser.parse_args()
    try:
        print(json.dumps(validate(args.root)))
    except (ValueError, OSError, KeyError, TypeError) as error:
        parser.exit(2, f"workflow validation failed: {error}\n")


if __name__ == "__main__":
    main()
