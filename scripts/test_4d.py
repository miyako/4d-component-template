#!/usr/bin/env python3
"""Exercise the namespaced API from an actual host project using free tool4d."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import shutil
import tempfile


def test_4d(root, tool4d, component=None):
    root = Path(root).resolve()
    config = json.loads((root / "template.json").read_text())
    if not config["initialized"]:
        raise ValueError("initialize the destination before running 4D host tests")
    output = root / "build" / "host-status.json"
    output.parent.mkdir(exist_ok=True)
    output.unlink(missing_ok=True)
    request = output.parent / "host-request.json"
    request.write_text(json.dumps({"status": str(output), "expectCompiled": component is not None}) + "\n")
    source = Path(component).resolve() if component else root / "component" / config["repository"]
    with tempfile.TemporaryDirectory(prefix="4d host ", dir=output.parent) as temporary:
        host = Path(temporary) / "Host"
        shutil.copytree(root / "tests" / "host", host,
                        ignore=shutil.ignore_patterns("DerivedData", "userPreferences.*", "Data", "Logs"))
        (host / "environment4d.json").unlink()
        package = host / "Components" / (config["repository"] + ".4dbase")
        shutil.copytree(source, package, ignore=shutil.ignore_patterns("userPreferences.*", "Data", "Logs"))
        subprocess.run([str(Path(tool4d).resolve()), str(host / "Project" / "Host.4DProject"),
                        "--skip-onstartup", "--startup-method=Smoke", "--dataless",
                        "--user-param=" + str(request)], check=True, timeout=120)
    if not output.is_file():
        raise ValueError("tool4d did not write host-status.json; host execution is unverified")
    status = json.loads(output.read_text())
    if status.get("success") is not True or len(status.get("cases", [])) != 6:
        raise ValueError("4D host contract failed: " + json.dumps(status, ensure_ascii=False))
    if component is not None and status.get("compiled") is not True:
        raise ValueError("release component was not running compiled code")
    return status


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--tool4d", type=Path, required=True)
    parser.add_argument("--component", type=Path, help="load this unpacked .4dbase instead of the source project")
    args = parser.parse_args()
    try:
        test_4d(args.root, args.tool4d, args.component)
    except (ValueError, OSError, subprocess.SubprocessError) as error:
        print(f"4D host tests failed: {error}", file=sys.stderr)
        return 1
    print("4D host contract passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
