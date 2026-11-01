# 4D CLI component template

An agent-ready **real 4D component project** wrapping a native CLI on macOS and
Windows. Choose **Go, Rust or C++**; initialization keeps only that starter.
The working greeting example uses the same deterministic UTF-8 JSON protocol in
each language. Replace the example with your feature, not the generic adapter.

## Use this template

Click **Use this template → Create a new repository**, then prompt your agent:

> Implement a 4D component in this repository that [FEATURE]. Use [Go/Rust/C++],
> unique class namespace [NAMESPACE], CLI basename [CLI_NAME], and these
> constraints: [DEPENDENCIES, LICENSE, LIMITS, ERROR BEHAVIOR]. Follow AGENTS.md,
> initialize the exact destination repository name, implement the feature and
> its host API/docs/tests, and deliver a compiled component release. Report
> unvalidated platforms and required setup honestly.

```sh
python3 scripts/initialize.py --repository hello-tools --namespace AcmeHello \
  --cli hello-cli --language go --feature "The requested feature"
```

The repository argument is the **exact new GitHub repository basename**, not
`owner/name`, the worktree name or this template's original name. Validation
allows ASCII letters/digits/`_`/`-` up to 80 characters, namespace identifiers
up to 31 characters, and lowercase CLI letters/digits/`-` up to 63 characters.
Namespace uniqueness across a host's components is the user's responsibility.

Initialization renames the component root, project, catalog name/UUID, XML
namespace, CLI identity/manifests, class docs, README samples, host fixtures and
package metadata. Workflows derive paths/asset names from `template.json`.
It stages/validates replacements first, preserves binary icons and keeps only
the selected `cli/`. Identical reruns are unchanged; conflicting reconfiguration
requires a fresh template. **The feature description is recorded, not automatically
implemented.** Read [AGENTS.md](AGENTS.md) for the end-to-end agent workflow.

The uninitialized template is **not releasable** and normal template CI does not
install three unrelated language toolchains.

## Requirements and specifications

| Surface | Specification |
| --- | --- |
| 4D source | Project compatibilityVersion 2060; 4D 20.7 LTS tool4d used locally |
| Host installation | Dependency manager GitHub support: 20 R6 or later / compatible current LTS; confirm your release |
| macOS CLI | macOS 12+ with pinned Go 1.26; Rust/C++ deploy to 11+; universal x86_64 + arm64; follow your 4D host's requirements |
| Windows CLI | x64, hosted Windows Server 2022; explicitly select `Windows-x64` in the API |
| Windows ARM64 | No native CLI artifact or verified native 4D compiler target; x64 emulation is not a supported/tested promise |
| Go | CI 1.26.10 (source minimum 1.23), stdlib only, CGO disabled |
| Rust | CI 1.99.1, edition 2021, std only |
| C++ | C++17/CMake, hosted Xcode/MSVC, static Windows CRT |
| Python | 3.10+ locally, CI 3.12 |

Only the selected language is built. Pins are a starting point, not a security
support promise: update deliberately and repeat checks. GitHub services runner
images/Xcode/MSVC, so compiler patch versions are not immutable.
`package.json` is name/version metadata, not a Node application.

## Architecture and exposed API

```text
template.json                         initialization/release identity
cli/                                  one selected language implementation
component/<repository>/
  Project/<repository>.4DProject       real 4D anchor
  Project/Sources/Classes/
    _CLI.4dm                          generic resource resolver
    _Process.4dm                      generic quoting/execution/status adapter
    Greeting.4dm                      replaceable feature API
  Project/Sources/Methods/_CaptureError.4dm
  Documentation/Classes/*.md           class contracts
  Resources/logo.png + logo.svg        original icon/reference wrapper
  Resources/bin/macOS/<cli>            assembled universal executable
  Resources/bin/Windows/<cli>.exe      x64 executable
tooling/compiler/                     real Compile project driver
tests/host/                           namespaced host runtime fixture
scripts/                              initialize/build/compile/package/test
```

The **component/project/catalog/package/release ZIP name MUST equal the repository
basename** for dependency-manager releases. Namespace is independent:
`settings.4DSettings` is XML with
`<general component_classStore_name="TemplateCLI"/>`.
Host code uses `cs.TemplateCLI.Greeting`; internal code uses `cs.Greeting`.
4D shares classes through the namespace: underscores are internal **by
convention**, not private access or an exported-class manifest.

Class docs:
[Greeting](component/4d-component-template/Documentation/Classes/Greeting.md),
[_CLI](component/4d-component-template/Documentation/Classes/_CLI.md),
[_Process](component/4d-component-template/Documentation/Classes/_Process.md).
The actual compiler generates `Resources/en.lproj/syntaxEN.json`, preventing
stale completion metadata.

### Working host sample

After installation, use your initialized namespace:

```4d
var $tool : cs.TemplateCLI.Greeting
var $result : Object
var $target : Text
$target:="macOS-universal"
If (Is Windows)
  $target:="Windows-x64"
End if
$tool:=cs.TemplateCLI.Greeting.new($target)
$result:=$tool.greet("4D")
If ($result.ok)
  ALERT($result.value.message)  // Hello, 4D!
Else
  ALERT($result.error.code+": "+$result.error.message)
End if
```

Calls are synchronous with a 30-second process timeout. Success preserves
`{ok:true,stdout,stderr,exitCode:0,value}`. Failure has `ok:false`,
`error:{code,message{,details}}`; process output/status are retained when
available, while prelaunch errors do not invent an exit code.
Missing executable, unsupported target/platform, invalid argument, launch
failure, abnormal termination, nonzero CLI status and malformed protocol are
explicit. Nonempty stderr alone is not failure. No PATH fallback, runtime
download, unchecked chmod or global host error handler.

### CLI contract

UTF-8, exactly one JSON line, LF on both systems, protocol version 1:

| Invocation | Status / stdout / stderr |
| --- | --- |
| `hello-cli greet --name "4D"` | 0 / `{"protocol":1,"message":"Hello, 4D!"}` + LF / empty |
| `hello-cli --version` | 0 / `{"protocol":1,"version":"0.1.0"}` + LF / empty |
| Invalid/unknown/missing/duplicate args, empty or malformed UTF-8 name | 2 / empty / error JSON below + LF |

```json
{"protocol":1,"error":{"code":"invalid_arguments","message":"expected greet --name <non-empty UTF-8 name> or --version"}}
```

No shell is used. `4D.SystemWorker.new` takes **command-line Text**, not argv
Collection. Each literal argument/path is quoted; File/Folder virtual Resources
paths are expanded with actual 4D APIs. stdin closes immediately. UTF-8 names,
spaces, quotes, backslashes, newlines and metacharacters are data. Windows CRT
and 4D macOS parsing require real native round-trip checks, not shell tests.
Add an explicit Blob mode if your future feature returns binary output.

## Install after release

In the host's Dependency manager add **GitHub** dependency `OWNER/REPOSITORY`
and choose the released tag/version. The asset must be exactly `REPOSITORY.zip`.
Alternatively declare in the host's `Project/Sources/dependencies.json`:

```json
{
  "version": 2100,
  "dependencies": {
    "hello-tools": {"github": "OWNER/hello-tools", "tag": "v0.1.0"}
  }
}
```

Reload the host and use your namespace. Manual installation: unzip and copy
`REPOSITORY.4dbase` into the host's `Components/` folder.
Local source dependencies point at the component package root, not the anchor.
`tests/host/environment4d.json` documents this mapping; automated runtime checks
install an isolated copy under `Components/` to test actual component loading.

## Build, validate and release

```sh
python3 -m unittest discover -s tests -v
python3 scripts/generate_icons.py --check
python3 scripts/build_cli.py --target macos-arm64
```

Use your native target: `macos-x64`, `macos-arm64`, `windows-x64`.
CI builds/tests only the selected language in native hosted jobs, uploads
same-commit binaries and combines macOS slices using `lipo`.
CI executable artifacts are **not compiled component releases**.

### Real 4D tooling and configuration

[tool4d](https://developer.4d.com/docs/20/Admin/cli#tool4d) is the official **free
standalone headless tool** used by the reference component pipelines. This flow
does not require a license/serial secret. Full IDE, Server and merged applications
have separate vendor licensing. Never bundle tool4d into the MIT component.

Set these repository **Actions variables** for hosted 4D validation/releases:

| Variable | Value |
| --- | --- |
| `FOURD_ENABLED` | `true` to enable vendor tool download/use; mandatory for release |
| `TOOL4D_URL` | Official macOS ARM64 tool4d `.tar.xz` URL for your approved fixed 20.7+ build |
| `TOOL4D_SHA256` | Exact archive SHA256, verified out of band |

Reference URL form:
`https://resources-download.4d.com/release/20.x/20.7/BUILD/mac/tool4d_arm64.tar.xz`.
`latest` is discovery-only/mutable; checksum mismatch fails. Local validation
used 20.7 `latest` resolving **build 101905**, SHA256
`40a5d177a4f73165f52abf6ec8000249d81411c41353ccf258cece8e74639261`.
The fixed `101905` endpoint was also observed available. Verify its downloaded
hash before configuring CI.
No imagined setup action or unpinned external compiler is used.

```sh
python3 scripts/test_4d.py --tool4d /path/to/tool4d
python3 scripts/compile_component.py --tool4d /path/to/tool4d
python3 scripts/package_component.py --repository OWNER/REPOSITORY \
  --tag v0.1.0 --unpack-test
python3 scripts/test_4d.py --tool4d /path/to/tool4d \
  --component build/release-test/REPOSITORY.4dbase
```

The driver runs real `Compile project` for `x86_64_generic` and
`arm64_macOS_lib`, requiring a **fresh successful JSON result**. Errors or absent
results fail even when tool4d exits zero. It cleans generated DerivedData before
recompile (stale compiled projects can otherwise be treated as sourceless).
Native Libraries and CompiledCode are required, not source-shaped substitutes.

Align `template.json.version`, `package.json.version` and the CLI version,
commit and push `v<version>`, e.g. `v0.1.0`. Release builds all CLI targets from
that same tag, compiles after Resources assembly, packs `REPOSITORY.zip`,
and **loads the unpacked compiled package in a real 4D host before publishing**.
Uninitialized/misnamed projects, missing tool/binary/library, failed compile or
failed host test fail closed. Only the publish job receives `contents:write`
through built-in `GITHUB_TOKEN`; no personal token/version-bot commit needed.

```text
REPOSITORY.zip
  REPOSITORY.4dbase/
    REPOSITORY.4DZ                     standard ZIP: Project metadata + CompiledCode
    Libraries/lib4d-arm64.dylib        OUTSIDE .4DZ
    Resources/bin/macOS/CLI            universal, executable ZIP mode
    Resources/bin/Windows/CLI.exe      x64
    Resources/licenses/LICENSE        redistribution notice included
    Resources/logo.* + en.lproj/...
    Documentation/Classes/...
```

Packed `.4DZ` excludes `.4dm` Classes/Methods source. ZIP order/timestamps/modes
are deterministic; serviced native compiler outputs need not be bit-identical.
Explicit nested directory ZIP records are required: omitting them caused a real
tool4d compiled-component loader crash, despite producing a generally valid ZIP.

### Optional signing/notarization

Signing is **not required** by this unsigned build/release pipeline. PDF references
sign macOS distributions; their release policy is not an intrinsic 4D requirement.
Windows Authenticode and Apple notarization are not configured here.

For production, explicitly add opt-in signing before final package validation:
certificate/password, ephemeral keychain password, identity and notarization
credentials in Actions **secrets only**; minimum entitlements; fail each codesign
error; require notarization JSON `Accepted`; clean temporary keychain in
`always()`; retest the final signed package. Bare CLI executables cannot be
stapled. Stapling a signed container and Apple's recommended `Contents/` component
layout require deliberate packaging changes. Never `continue-on-error` signing.
Gatekeeper/quarantine can block unsigned downloaded executables; no runtime
trust bypass is supplied.

## Icons

Original `assets/icon-source.svg` is rendered to a **real 1024×1024 RGBA PNG**.
Resources `logo.svg` is a reference-style **64×64 SVG embedding a PNG data URI**
whose decoded bytes equal `logo.png`. The convention is **PNG-in-SVG**, not the
reverse (verified across all three inspirations).

```sh
python3 scripts/generate_icons.py
python3 scripts/generate_icons.py --check
```

Regenerate both icons together. The dependency-free renderer supports this
original rectangle/polygon artwork; unsupported elements fail explicitly.
Use a pinned real SVG rasterizer for richer artwork, never rename SVG to PNG.

## Remarks and validation limitations

No PDF settings/algorithms, tables/authentication schema, async queue, network
installer or external PATH search. Generic helpers are internal-by-convention.
Implement cancellation/streaming explicitly for features needing more than the
finite synchronous timeout.

Local Apple Silicon validation covers all three CLI starters, initialization,
icon/package invariants, actual free tool4d compilation and namespaced host
calls against both source and the unpacked source-stripped release artifact,
including `Is compiled mode = True`. Hosted Windows/macOS Intel, Windows **4D** quoting, dependency-manager
download from a new release, and signing are separate observations; Python or
CLI tests alone do not prove them. See PR results for exact observed checks.

## Licensing and provenance

New scaffold, CLI starters, tests and original icon are **MIT**: [LICENSE](LICENSE).
Keep its copyright/license in redistributed source/binary assets. Future bundled
tools, libraries and static dependencies carry their own upstream license/NOTICE
obligations: include notices in `component/<name>/Resources/licenses/`.
4D/tool4d are separately licensed vendor tools, not MIT dependencies.

Conventions were verified from
[pdfdistill-pdfcpu](https://github.com/miyako/pdfdistill-pdfcpu),
[pdfdistill-qpdf](https://github.com/miyako/pdfdistill-qpdf),
[pdfdistill-lopdf](https://github.com/miyako/pdfdistill-lopdf)
(MIT, 2026 Keisuke Miyako), and
[4d-class-compiler](https://github.com/miyako/4d-class-compiler)
(MIT, 2022 Keisuke Miyako). No feature algorithms, binaries or artwork were copied.
[4d-plugin-tutorial](https://github.com/miyako/4d-plugin-tutorial) inspired the
agent-driven tutorial UX; this is a component/standalone CLI, not its native
plug-in SDK/code. Official references:
[dependency naming](https://developer.4d.com/docs/Project/components),
[Compile project](https://developer.4d.com/docs/commands/compile-project),
[SystemWorker](https://developer.4d.com/docs/API/SystemWorkerClass) and
[error handling](https://developer.4d.com/docs/20/Concepts/error-handling).
