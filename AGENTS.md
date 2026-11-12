# 4D CLI component: THINK / ASK → RUN playbook

This is the canonical implementation and acceptance guide. Read `README.md`,
`template.json`, this file, class documentation, relevant scripts and host tests
before editing. This is a **real 4D component**, not a native 4D plug-in: its
bundled executable runs as a separate process. Keep generic execution separate
from the deliberate feature API.

Repository-wide Copilot instructions are intentionally short. The optional
task-specific skill is `.github/skills/4d-cli-component/SKILL.md`; its presence
does not prove that a particular agent session discovered or invoked it.

## 1. THINK / ASK: establish the contract before running

Resolve these inputs from the request and actual destination repository. Ask
only for missing decisions that affect identity, semantics, dependencies or
release scope; do not ask for imaginary license/signing prerequisites. In
non-interactive execution, document safe assumptions; stop rather than guess
the destination identity or the user's language.

| Decision | Required answer / check |
| --- | --- |
| Architecture | CLI-backed component using this template, or a separate native 4D plug-in installed in the host; no component-over-plug-in hybrid as a self-contained component solution |
| Destination | Exact GitHub `owner/name`, including basename **case**; inspect the actual remote, not the checkout/worktree directory |
| Language | One user-selected `go`, `rust` or `cpp`; never ship three implementations |
| Namespace | Independent, unique 4D identifier; syntax validation cannot prove uniqueness among a host's future components |
| CLI | Lowercase executable basename, not a path |
| Feature | API class/methods, input/output, versioned CLI protocol, errors, limits, timeout and concurrency semantics |
| Dependencies | Pins, lockfiles, upstream licenses and redistribution notices, including statically linked runtime/stdlib |
| Acceptance | Native platforms available now; real source/compiled host checks; local unsigned artifact versus approved publication |

### Architecture and deployment boundary

Choose **either** of these architectures before initialization:

| Architecture | Execution and deployment |
| --- | --- |
| CLI-backed 4D component (this template) | Host code calls component classes; the component launches its bundled native CLI as a separate process through `4D.SystemWorker`. Install the component through the Dependency manager or the host's `Components/` folder; the CLI ships in component `Resources/bin/`. |
| Native 4D plug-in (separate architecture) | Native code integrates through the 4D plug-in SDK. The plug-in must be installed in the host using 4D's supported plug-in installation mechanism; it is not privately loaded or deployed by a component. |

This template must not generate or propose a component abstraction over plug-in
commands as a self-contained component solution. If the feature requires native
4D SDK integration, choose a separate **host-installed plug-in** architecture
and explicitly document host installation, compatibility and dependencies.
Native libraries used by a standalone CLI are not thereby 4D plug-ins.

Calling or wrapping commands from an already host-installed plug-in does not
change that deployment boundary: the plug-in remains an explicit host dependency.
This rule does not make a blanket claim about which host code can call plug-in
commands. A component cannot privately load/deploy a 4D plug-in, and component
packaging cannot hide, eliminate or satisfy the host plug-in installation
requirement. Do not put a plug-in in component Resources or Libraries and describe
it as a private native backend.

### Identity is exact, namespace is independent

The destination basename MUST equal `template.json.repository`,
`package.json.name`, `component/<name>`, `Project/<name>.4DProject`, catalog
`<base name>`, packed `<name>.4DZ`, outer `<name>.4dbase` and release
`<name>.zip`. Preserve case even on case-insensitive filesystems. CLI identity
and feature class identity are separate from this equality.

`settings.4DSettings` is XML:
`general.component_classStore_name` controls the host namespace.
For example, repository `hello-tools`, namespace `AcmeHello` and class `Greeting`
produce `cs.AcmeHello.Greeting` in a host; component-internal code uses
`cs.Greeting`, **not** the host namespace. Do not invent an exported-class list:
the namespace shares component classes. Underscore names are internal
**by convention**, not access control.

### Component release tags: no `v` prefix

Component versions and new release tags must be identical prefix-free SemVer:
`0.1.0`, **not** `v0.1.0`. Build publishes stable `X.Y.Z`; package validation,
signing proofs and publication reject prefixed tags rather than stripping them.
This is the template's Dependency Manager release convention, not a rule for
upstream GitHub Actions/toolchain tags or historical external release URLs.
The resolver consumes the **tag**, not the GitHub release display title.
This is a component release rule, not a native 4D plug-in tag convention.

The official [Follow 4D version reference](https://blog.4d.com/follow-4d-version-a-smarter-way-to-manage-your-dependencies/)
specifies prefix-free, **host-version-aligned** tags: LTS `x.y.p`, e.g.
`20.2.3` for the 4D 20.2 line, and R releases `xRy.p`, e.g. `20R3.2`.
Ordinary component SemVer such as `0.1.0` does **not** activate or imply
Follow4D compatibility. Host-aligned distribution is a separate deliberate
versioning choice; this pipeline does not implement non-SemVer R-release tags
and rejects them. Do not select Follow 4D version for ordinary component
versions or infer compatibility from a tag alone. A custom display title does
not excuse an incompatible tag format.

Migration is read-only for published history: version planning considers the
highest numeric stable version across both `X.Y.Z` and legacy `vX.Y.Z` tags,
ignoring prerelease/build-metadata and unrelated tags. Bump version increments
the greater of the current source version and that stable history (or source
alone when no stable tag exists). Each successful Bump increments authoritative
source; it never reuses an earlier bump candidate. Only Build creates a new prefix-free
tag at the accepted dispatch SHA; do not rename, move, delete or automatically alias old
tags/releases, or reuse their acceptance/signing evidence. Existing consumers
pinned to old tags stay unchanged until explicitly migrated. Signing policy
entries remain exact prefix-free versions; the policy is not rewritten or
weakened during migration.

### Scope and stop rules

* If a requested design requires a host-installed 4D plug-in, stop CLI-component
  adoption and select the separate plug-in architecture; do not disguise that
  host dependency behind component classes or a component ZIP.
* Do not initialize `miyako/4d-component-template` itself, even when a worktree
  has a different local name. Template maintenance/documentation is not adoption.
* Never set `initialized` by hand, bypass initializer validation, overwrite a
  conflicting initialized destination or silently choose another language.
* A feature description is not an implementation. Renaming a class is not
  replacing its behavior. Do not declare completion while greetings remain
  in the feature contract, smoke tests or completion metadata.
* Inspect tool reports before installing anything. Missing selected toolchains
  are failures/blocked checks, not silently skipped successes.
* Stop on identity mismatch, unsafe archive paths, stale/mixed build artifacts,
  unavailable required runtime, compile errors or failed package-host loading.
  Return partial evidence and the precise blocker; do not weaken gates.
* Do not create tables, authentication/locale settings, setup actions or PDF
  algorithms merely to resemble a reference project.
* Do not publish, push tags, add signing/account settings or copy credentials
  unless the user authorized that scope. Local acceptance needs none of them.

## 2. RUN: inspect and initialize only the destination

Start with a read-only environment/configuration report:

```sh
python3 scripts/doctor.py --root .
python3 scripts/doctor.py --root . --tool4d /path/to/tool4d
```

`doctor.py` reports JSON configuration, Python minimum compatibility, selected
installed tools, host and supplied executable; it does not initialize,
download, build, repair permissions or claim runtime acceptance. `--tool4d` is
optional. Review the actual remote and script `--help` before invoking mutating
steps. Paths passed via `--root` must identify the intended repository.

For a **new destination** with `template.json.initialized:false`:

```sh
python3 scripts/initialize.py --root . --repository hello-tools \
  --namespace AcmeHello --cli hello-cli --language go \
  --feature "The requested feature"
```

Obtain the destination identity with `gh repo view --json nameWithOwner --jq
.nameWithOwner` (read-only), or inspect its GitHub remote. Never use the worktree
directory basename. An example **adopter prompt**, not a specialization of this
template, is:

> In this new GitHub repository named UuidTest, implement UUIDv7 using Go,
> namespace UuidTest, CLI uuid-test and public class UUIDv7. Follow AGENTS.md;
> initialize first, replace the greeting API/CLI/docs/contracts/host tests,
> define RFC 9562 timestamp/version/variant and entropy-error behavior, and
> deliver the actual compiled package. Do not promise monotonic ordering across
> fresh CLI processes or mathematical uniqueness from a finite sample. Report
> all untested native platforms, signing and dependency-manager installation.

The initializer validates/stages identity rewrites, renames the component root,
project/catalog and deterministic catalog UUID, XML namespace, CLI manifests,
package metadata, README/class examples and host fixtures. It retains only the
selected starter in `cli/`, removes `cli-starters/`, preserves binary icons and
marks initialization complete. Identical repetition is a no-op; conflicting
reconfiguration is rejected. It invokes **no toolchain** and records the feature
description only. You must implement the feature next. Unconfigured template CI
must neither publish nor install every language toolchain.
Do not subsequently copy original template fixtures over the configured
`tests/host/`: doing so restores the old namespace and can make the host's
feature constructor undefined. Preserve the initializer's rewritten files when
copying additional tests or tooling.

Current syntax limits: repository 1–80 ASCII letters/digits/underscore/hyphen,
starting with a letter/digit; namespace 1–31 identifier characters starting with
a letter; CLI 1–63 lowercase letters/digits/hyphens starting with a letter.
Reserved names and control characters are rejected by the initializer.

## 3. RUN: replace the greeting feature completely

Define the versioned CLI contract and error/status behavior first. For a new
class identity, the helper performs a bounded **identity rewrite**, not feature
implementation:

```sh
python3 scripts/rename_feature.py --root . --class UUIDv7
```

It rewrites the Greeting identity only in known files and records
`template.json.feature_class`;
do not use global search-and-replace across arbitrary user files. Inspect its
diff and then implement the methods/protocol. A class named `UUIDv7` that still
returns a greeting is unfinished.
In the exact known `.4dm` files it changes class-reference code outside Text
strings and `//` comments; known docs/README identity references are rewritten
separately. User literals/comments and arbitrary files are not a rename target.

### Feature replacement inventory

Update these surfaces together, preserving reusable infrastructure:

1. `cli/` implementation, selected-language tests, usage/version/error messages
   and dependency manifests/lockfiles. Exactly one language remains.
2. `Project/Sources/Classes/Greeting.4dm` (or renamed feature class): constructor,
   public methods, internal decode validation and feature-specific result schema.
3. `Documentation/Classes/<Feature>.md` and related helper contracts if changed.
4. `tests/host/Project/Sources/Methods/Smoke.4dm`: real namespaced feature calls,
   assertions, negative cases and `Is compiled mode` evidence. Update
   `tests/host/contract.json` alongside it; the Python runner consumes this
   schema-1 feature/execution contract rather than hardcoding greeting results.
5. `tests/test_cli.py`, `tests/cli-contract.json` vectors consumed by native
   build smoke tests in `scripts/build_cli.py`, Python host-report checks in
   `scripts/test_4d.py` and relevant regression tests. Do not leave a contract
   expecting `greet` after changing the executable.
6. README host examples/CLI contract, `template.json.feature` and any feature
   `template.json.feature_class` registry used by the rename helper. Keep
   version metadata and `package.json` aligned. This starter deliberately ties
   its bundled CLI version to the component version; an independently versioned
   third-party CLI need not share that version. Define and assert both contracts
   explicitly rather than blindly rewriting upstream versions.
7. Compiler-generated `Resources/en.lproj/syntaxEN.json`: regenerate through the
   actual compiler and verify the new class appears; never retain stale Greeting
   completion metadata.
8. Redistribution notices under `component/<name>/Resources/licenses/`, and icon
   source/generated icons only if the feature requires artwork changes.

Keep `_CLI`, `_Process` and `_CaptureError` generic. Feature validators and
algorithms belong in feature classes/CLI, not the process adapter. Add exact
vectors, malformed input, failure injection and bounded performance tests.
For randomized/clock-dependent features, document ordering/state/collision
limitations and distinguish empirical samples from guarantees.

### Host contract registry

`tests/host/contract.json` separates feature expectations from generic execution
checks. `feature.casesPath` is a JSON pointer (initially `/cases`), and
`feature.cases` declares exact expected `stdout`, `stderr`, `exitCode` and decoded
`value` fields. Replace the greeting expectations with the feature's real cases.
For nondeterministic output, add appropriate real host semantic checks and use
the registry's supported assertions rather than pretending random output is a
fixed vector; extend validation deliberately if the contract cannot express
the feature.
For that mode, omit exact `feature.cases`, set positive integer
`feature.caseCount`, and supply nonempty `feature.caseAssertions` applied to
every complete result. Do not specify both modes. A `matches` assertion performs
a full Text regex match, not a substring search; e.g. check the identifier's
version/variant grammar while separately asserting host-measured clock bounds,
count or other semantic facts. Both modes still require complete non-null
feature values, exact count, finished/mode flags and nonempty failure assertions.

Both `feature.assertions` and `execution.assertions` use JSON-pointer `path`
with `equals`, `matches`, `length`, nested `each`, or `absent:true`. An empty pointer addresses
the current value; nested `each` assertions are relative to each item.
Escape pointer tokens with `~1` for slash and `~0` for tilde. `equals` uses
strict JSON type/deep equality; `length` is an exact array count, `each` requires
a nonempty array, and `absent:true` must appear with only `path`. Both assertion
arrays must be nonempty.
`execution.successPaths` names successful process envelopes: these do not require
feature-decoded `value`. Preserve separate generic resource/launch/type/NUL/path
checks when replacing the feature cases. Never make the fixture self-approve
without runner-side validation.

The runner always requires fresh `success:true`, `finished:true` and exact
compiled mode (`false` for source, `true` for the unpacked compiled artifact).
Feature cases must be nonempty, successful and have nonempty Text stdout, Text
stderr, integer exitCode zero and non-null decoded value. Exit status,
diagnostics and feature output remain separately asserted.
Write `finished:true` only at the actual end of Smoke. Change feature cases,
negative assertions and feature-specific File/Folder round-trip invocations
together; preserve nine unsupported argument types, leading/middle/trailing NUL,
Null required inputs, missing resource, unsupported target and launch-failure
coverage. Do not edit the runner to hardcode a feature class, case count or messages.

### Native CLI contract vectors

`tests/cli-contract.json` contains `schema:1` and nonempty `cases`. Each case has
Text-array `args`, integer `exitCode`, and exact expected `stdout`/`stderr`.
Streams are either literal Text encoded as UTF-8 or JSON Objects serialized
compactly as UTF-8 plus LF; `$VERSION` in expected JSON is substituted from
configuration. Include at least one real feature-success vector and one
nonzero-status failure vector, not merely `--version`. These vectors replace
the old hardcoded greeting smoke expectations. Language/Python tests and real
4D host assertions remain independent required evidence.
For nondeterministic streams, use a nonempty `stdoutPattern` or `stderrPattern`
**instead of** that exact stream field. It must fully match strict UTF-8 output,
including expected framing/LF. A grammar match alone is not a timestamp,
entropy, ordering or collision guarantee; the feature's native tests and real
host semantic checks must verify those separately. This avoids rewriting the
generic build/host runner merely to accommodate random output.

## 4. Real 4D process and error rules

* `_CLI` resolves the component's `/RESOURCES/bin` only: no PATH fallback,
  runtime download or unchecked chmod. Expand virtual paths with `platformPath`
  and the correct `File(...; fk platform path)` / `Folder(...)` constructors.
  A Python-supplied macOS path in a JSON request is POSIX: construct it with
  `File(path; fk posix path)`; on Windows use `fk platform path`. This is not the
  same as a 4D object's `.platformPath`, which requires `fk platform path` on
  either OS. The real renamed-executable host test exercises this distinction.
* `4D.SystemWorker.new` takes **command-line Text**, not an argv Collection.
  The generic adapter may accept a Collection but must quote each literal into
  Text. SystemWorker does not implicitly invoke a shell. Never introduce
  `cmd /c`, `bash -c`, `eval` or unquoted user paths/arguments.
* Use the existing quote routine, not shell escaping. macOS and Windows CRT
  backslash/quote parsing need **real 4D** native round trips on both OSes.
* Guard `Value type` before `OB Instance of`: numeric, Boolean, Null, date/time
  and Collection values must be rejected before object-instance checks. Plain
  Objects also fail; only Text, File and Folder arguments are supported.
* Reject actual embedded NUL with **strict** `Position(Char(0); $argument; *)>0`.
  The `*` matters: default linguistic comparison is not a byte/character-exact
  NUL search. Test ordinary Unicode/spaces and an actual NUL separately.
* The real options are `dataType:"text"`, `encoding:"UTF-8"`, `hideWindow:true`,
  `timeout:30`, `currentDirectory:file.parent`. Close stdin with `.closeInput()`,
  then `.wait()`. Read `.response`, `.responseError`, `.exitCode` and `.errors`
  separately; do not invent setup actions or architecture properties.
* A nonempty stderr is not itself failure. Missing/undefined exitCode, launch
  failure, timeout/abnormal exit, system errors, nonzero status and malformed
  protocol are failures. Preserve available stdout/stderr/status and diagnostic
  details; prelaunch failures must not invent an exit code.
* Capture errors narrowly with `ON ERR CALL(...; ek local)`, restore
  `Method called on error(ek local)` immediately and retain `Last errors`.
  Never install a permanent host-global handler or use Null/empty success
  fallbacks. Feature JSON parsing must reject wrong type/version/fields.
  4D Boolean expressions do not safely short-circuit type-sensitive operations:
  validate `Value type(payload.protocol)` in a separate `If` before comparing
  its numeric protocol version. Do not combine the guard and comparison with OR.
* Native Windows target is explicitly `Windows-x64`; never infer CPU
  architecture from freeform processor names. Native Windows ARM64 is unsupported.
* This starter is synchronous, with a finite 30-second timeout. Async work needs
  `CALL WORKER`, a live worker process, isolated per-call state, cancellation
  queue clearing and context pruning. Do not retrofit a shared unsafe PID map.
  `New process` is not a substitute for the callback/worker lifetime requirement.
  Do not infer stdin input from every `-` argument: it may denote an output.
* Use UTF-8 explicitly. Binary protocols need a separate deliberate Blob mode.
  Never blindly write empty stdout to an output file.

Keep tokens in IDE-generated code; plain command names in this scaffold are
intentional and accepted by the compiler.

## 5. RUN: build and validate from the same source revision

Pin selected toolchains/dependencies; commit lockfiles where applicable. Review
upstream licenses before copying/bundling. No license activation or signing secret
is needed for **unsigned local tool4d component compilation**. This does not
waive redistribution notices or licensing for the IDE/Server/merged applications.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/generate_icons.py --check
python3 scripts/build_cli.py --root . --target macos-arm64
```

Choose the actual native target: `macos-x64`, `macos-arm64`, `windows-x64`.
`build_cli.py` defaults to native-only; requesting another target without an
explicit supported cross flag must fail. For Go on a native macOS host only,
`python3 scripts/build_cli.py --root . --target windows-x64 --cross` produces a
foreign artifact without claiming native execution. Rust/C++ cross mode fails
explicitly. Build all
three native artifacts from the **same commit/input revision** for release.
Do not combine tracked stale binaries or artifacts from different commits.
Configured CI tests only the selected language and fails on missing tools.
Each executable is accompanied by `build/<target>/build-manifest.json`, binding
CLI source/config/package inputs, Git commit and binary SHA256. Native CI uploads
the manifest with the executable. Assembly refuses missing, stale, modified or
mixed-source manifests; a plausible filename/header alone is not provenance.
Preserve `.gitattributes`: LF text checkout on macOS **and Windows** keeps those
content hashes identical; automatic CRLF conversion would create different
inputs despite an identical Git commit.

Resource assembly requires both macOS slices and Windows x64:

```sh
python3 scripts/ci_config.py assemble --root .
```

The genuine lipo verification order is:
`lipo <universal-file> -verify_arch x86_64 arm64`, **not**
`lipo -verify_arch x86_64 arm64 <file>`. Create with
`lipo -create <intel-file> <arm-file> -output <universal-file>`.
Check native dynamic dependencies and preserve executable ZIP modes.

### Optional local orchestration, not a release shortcut

```sh
python3 scripts/accept_local.py --root . --repository OWNER/REPOSITORY \
  --tool4d /path/to/tool4d
```

Without `--cross`, this builds/tests the native target and requires already
current matching artifacts **and manifests for all three targets** for assembly.
For Rust/C++, obtain them from native CI for the exact same commit and source
inputs, restoring each executable and its `build-manifest.json` to
`build/<target>/`. Do not attempt unsupported cross mode.

For **Go on native macOS**, optional local three-target artifact production:

```sh
python3 scripts/accept_local.py --root . --repository OWNER/REPOSITORY \
  --tool4d /path/to/tool4d --cross
```

The acceptance helper invokes existing builds, assembly, source host tests,
compilation, packing/unpacking and compiled host tests. Read its `--help` and
`build/acceptance.json`; do not assume missing tools/platforms were tested.
Add `--cross` **only for Go** to build nonnative CLI artifacts locally. Rust/C++
cross mode is unsupported and must be reported explicitly, not silently ignored.
Go cross-compilation is optional artifact production, not native execution or
Windows/Intel 4D evidence. Neither the helper nor class renaming implements the
requested feature automatically.

On native Apple Silicon, `accept_local.py --cross` builds all three Go targets,
tests the native CLI and may separately run Intel CLI vectors through Rosetta
when available. Rosetta evidence is **translated execution**, not native Intel
execution or Intel 4D loading. If unavailable, that check remains `not_run`;
Windows native execution remains unverified regardless of successful cross-build.

Evidence is written to `build/acceptance.json`; a successful pack produces
`dist/<repository>.zip`. A partially validated local package is **NOT release
ready**, even if its source/compiled Apple Silicon host checks pass. Missing
required artifacts/checks can prevent ZIP creation; do not manufacture substitutes.
The helper preserves `build/source-host-status.json`,
`build/compiled-host-status.json` and `build/compile-status.json` separately.
Verified local package completion reports `result:"partial"`, `finished:true`,
`release_ready:false`; failure saves evidence with `result:"failed"` and
`finished:false`. `cli_build_<target>` and `cli_test_<target>` are distinct checks,
and Rosetta is separate. macOS `otool -L` checks allowlisted system libraries;
Windows native DLL/runtime dependencies are explicitly **not inspected locally**
and require native review.
The verified run also writes `dist/<repository>.acceptance.json` beside the ZIP,
including its SHA256, timestamps, actual tool4d version/hash and embedded host
reports. Copy that pair to durable storage before disposing of a worktree.
`build/acceptance.json` records the latest attempt, including failures; it is not
proof that a pre-existing ZIP was produced by a failed attempt.

## 6. Free fixed tool4d and real compiled-package acceptance

This pipeline packages the CLI-backed component, not a host-installed plug-in.
Compiler-generated component `Libraries/` and bundled CLI resources are not a
private plug-in backend. Neither the component ZIP nor Dependency manager
installation satisfies a 4D plug-in's separate host installation requirement.

[tool4d](https://developer.4d.com/docs/20/Admin/cli#tool4d) is the official free
standalone headless tool. Do not bundle it in component Resources. This local
flow needs no serial, activation secret, signing identity or repository settings.
Use a fixed HTTPS archive and verify its SHA256 before extracting into `.tools/`:

```sh
python3 scripts/ci_config.py download-tool4d --root .
```

The command derives its fixed URL/hash from versioned `package.json.tool`.
Only for an explicitly approved override, pass the **complete** pair:

```sh
python3 scripts/ci_config.py download-tool4d --root . \
  --url https://resources-download.4d.com/release/20.x/20.7/101905/mac/tool4d_arm64.tar.xz \
  --sha256 40a5d177a4f73165f52abf6ec8000249d81411c41353ccf258cece8e74639261
```

This is **20.7 build 101905, macOS ARM64**, observed in the local case study.
It is not a native Intel/Windows tool or a future availability guarantee.
`latest` is mutable/discovery-only and must not be a pinned download input.
The approved default is recorded in `package.json.tool`. Paired explicit
`--url` / `--sha256` overrides take precedence over paired
`TOOL4D_URL` / `TOOL4D_SHA256` environment overrides, then the manifest default.
Supply both override values or neither; incomplete pairs fail. The explicit
fixed flags above make this local command independent of repository variables. Require
native-host compatibility and safe extraction: reject path traversal, escaping
symlink chains, unsupported entries and checksum mismatch. Never bypass checks.
The fixed download may redirect to the vendor's `builds2.4d.com` CDN; each hop
is checked before following, allowing only those two exact HTTPS hosts without
URL credentials or nonstandard ports. Signed CDN query strings are not compiler
pins and never replace the fixed URL or archive SHA256.

Run the actual stages (example version `0.1.0`, initialized destination only):

```sh
python3 scripts/test_4d.py --root . --tool4d .tools/tool4d.app/Contents/MacOS/tool4d
python3 scripts/compile_component.py --root . --tool4d .tools/tool4d.app/Contents/MacOS/tool4d
python3 scripts/package_component.py --root . --repository OWNER/REPOSITORY \
  --tag 0.1.0 --unpack-test
python3 scripts/test_4d.py --root . --tool4d .tools/tool4d.app/Contents/MacOS/tool4d \
  --component build/release-test/REPOSITORY.4dbase
```

1. Source host tests load an isolated component through a real host's
   `Components/`. The local dependency path names the package root, not the anchor.
   Source staging drops DerivedData to avoid interpreted tests loading stale
   compiled code. Isolated host/request/status paths include Unicode, spaces and
   both quote characters on POSIX (double quotes are invalid in Windows filenames;
   the Windows fixture deliberately uses Unicode and spaces without either quote);
   copies reject symlinks. A renamed copy of the actual native CLI also verifies
   executable-path handling, not merely argument quoting. These tests require actual
   runtime execution on each OS to establish native quoting behavior.
2. Run actual `Compile project` for `x86_64_generic` and `arm64_macOS_lib`.
   Require fresh successful JSON identifying the correct project/targets.
   A zero tool exit without that file is not compilation success.
3. Clear generated DerivedData before compiling and bind the compile marker to
   current inputs. Stale compiled state can be treated as sourceless by 4D.
   Require native Libraries and nonempty CompiledCode, not source-shaped stand-ins.
   `compile-status.json.input_sha256` binds the component inputs, and
   `output_sha256` also binds the generated DerivedData/Libraries. Packaging must
   reject altered/stale compiler outputs, not merely check their presence.
4. Pack deterministic ZIPs, strip all Classes/Methods `.4dm` source, retain
   compiler-generated completion metadata and external native Libraries.
   **Both ZIP levels need explicit nested directory records**: a generally valid
   ZIP omitting them caused an observed real compiled-component loader crash.
5. Test the **unpacked ZIP's** `.4dbase`, not the working source folder. The
   component must report `Is compiled mode=True`. A Python/CLI suite, successful
   compiler or archive structure check is not evidence of real host loading.
6. Recompile/repack/retest after any input or signing change. Never accept a
   stale `host-status.json` or result describing a different package.

The isolated host's `Host_error` method writes raw `Last errors`, the failing
phase, `success:false` and `finished:false` on an unexpected runtime abort.
It uses/restores a local handler; it is not a permanent host-global component
handler. Inspect `build/host-status.json` before guessing that compilation,
namespace sharing or quoting is broken.

**Every 4D project opened headlessly must already contain
`Project/Sources/dependencies.json` before its first open.** Otherwise 4D may
show a modal "import components" dialog that blocks a `--startup-method` run
indefinitely until a person dismisses it (observed with 4D 21.0 on Windows for
a compiler project lacking the file, miyako/DisplayScale#2). This applies to the
component, the host fixture, `tooling/compiler/` and any new tooling/test
project you add. Use `{"version":2100,"dependencies":{}}` for a project with no
components; the host fixture declares the component, e.g.
`{"version":2100,"dependencies":{"NAME":{}}}`. Commit the file with the project;
do not create it after the first open or dismiss the dialog manually. A hung
headless 4D run on a project lacking it is this dialog, not a compile failure.

For template maintainers, this opt-in regression creates a disposable initialized
`UuidTest` / `UuidTest` / `uuid-test` Go fixture, renames the class to `Identifier`,
then executes the same local pipeline:

```sh
TOOL4D_INTEGRATION=.tools/tool4d.app/Contents/MacOS/tool4d \
  TEST_CLI_LANGUAGE=none python3 -m unittest discover -s tests -p test_adoption.py -v
```

It preserves the initializer-renamed host fixture, exercises native and Go
cross-builds, real quoted/Unicode paths, source and final compiled host modes,
generated class metadata, stripped source, ZIP records/modes and artifact hash.
Evidence is saved in `build/adoption-evidence/` before fixture cleanup, including
failed status/phase reports. This is a starter identity/wiring regression,
**not** evidence that UUIDv7 or any other new feature was implemented.

`--tag` validates package/version identity; it does not create/push/publish a tag.
For approved hosted publication only, set Actions **variable**
`FOURD_ENABLED=true`; `TOOL4D_URL` / `TOOL4D_SHA256` are optional paired overrides
of the approved public `package.json.tool` pin, not required secrets. Use manual
Bump version to commit synchronized source metadata to an explicitly selected
branch, then separately authorize Build on main for that immutable dispatch SHA.
Build derives the version from source; it does not bump it. Jobs compile after
assembly and host-test the unpacked package before publishing `<repository>.zip`.
Only the source-version commit and publication jobs receive built-in
`GITHUB_TOKEN` write permission; no personal token is required. Branch rules
must permit the bot's non-force commit to the selected branch; rejection fails
closed rather than bypassing protection.

### CI and two manual release-facing actions

#### Enforced generated contract and bounded configuration

The checked-in `ci.yml` (**CI**), `bump-version.yml` (**Bump version**) and
`build.yml` (**Build**) are the three canonical workflows inherited by
destination repositories. There is no additional workflow generator.
Before initialization or local workflow tests:

```sh
python3 -m pip install -r tooling/requirements-workflow.txt
python3 scripts/workflow_contract.py --root .
```

Use a local virtual environment when appropriate. This pinned YAML parser is
development tooling, not a component runtime dependency. Validation never
dispatches, builds, publishes or accesses credentials. CI and both manual actions
enforce it before their work; initialization rejects an invalid inherited
contract before destination writes.

`workflow-contract.json` selects the sole supported `cli-universal-v1` profile:
native macOS Intel/ARM and Windows x64 CLI builds, universal resource assembly,
macOS ARM64 tool4d source/compiled-package checks, and explicit unexecuted
Intel/Windows 4D evidence. It does not add new platform support or make
mandatory gates editable. Keep destination identity/language in `template.json`,
compiler pins in `package.json.tool`, dependencies in selected-language
manifests/lockfiles, and signing in `release-policy.json`.

The optional `version_surfaces` array extends the bounded starter version
registry; default `[]` requires no configuration. Supported entries are:

```json
[
  {"kind":"json-pointer","path":"cli/metadata.json","pointer":"/own/version"},
  {"kind":"literal","path":"cli/version.hpp","prefix":"release = \"","suffix":"\";","count":1}
]
```

JSON pointers address Object properties, not array elements; escape `~` and `/`
with `~0` and `~1`. Literal delimiters select an exact positive occurrence count.
Every selected field must equal the current component version, including on a
retry. Declare extensions after creating their destination files; paths are
repository-relative, regular non-symlink files. Missing, ambiguous, stale,
conflicting or escaping surfaces fail before version writes. Never register
dependency/upstream versions or signing policy as component-version surfaces.
Configuration changes invalidate native/compiler input provenance and require
fresh acceptance.

Platform/dependency differences are explicit implementation contracts, not
freeform workflow hooks. This profile supports only the existing three targets.
A dependency adaptation must define pinned source/lockfiles, selected-language
build integration, license notices, native runtime inspection and same-revision
digest-bound evidence before it can become a supported adapter. No generic
third-party builder, arbitrary command hook or alternate platform profile is
implemented here; unknown configuration is rejected rather than silently skipped.

#### Release entry points, handoff and bounded waiting

| Intent | Canonical entry point |
| --- | --- |
| Inspect configuration/tools | `scripts/doctor.py`; `scripts/workflow_contract.py` |
| Local unsigned acceptance | `scripts/accept_local.py` |
| Nonpublishing hosted inspection | Actions **CI**, with hosted 4D opt-in |
| Optional credential setup | User-owned setup guide/helper below; never agent-executed |
| Source-only version update | Actions **Bump version**, explicitly selected branch, patch/minor/major |
| Authorized publication | Actions **Build**, main, optional `require_apple_signing` only |
| Internal source-version stage | `release_source.py bump`; synchronized source metadata commit only |
| Internal build/release stages | `release_source.py` preflight → reusable CI → `accept_hosted.py` / `sign_release.py` → `release_assets.py` / `release_ref.py` |

Do not replace these stages with hand-assembled per-project checks. Before
authorized signed publication, hand the user the existing setup guide and
six required names; inspect names/timestamps only after their setup. Missing
credentials stop the signed path, never select unsigned or authorize repair.

Use a compact release handoff from actual helper evidence: repository/version,
accepted SHA, workflow run/phase, effective signing policy, artifact/evidence
paths and SHA256, required checks (`passed` / `failed` / `not_run`), actual
platform/tool scope, and one precise blocker or required user action.
Preserve `result`, `finished` and `release_ready` as recorded; green native CLI
jobs, successful compilation, or a file's presence cannot self-approve a ZIP.
Tool4d host evidence does not establish normal IDE/Server loading or Dependency
Manager installation.

Advance on workflow/agent completion notifications. Read the identified run
once when relevant completion arrives; inspect the failed phase's preserved
reports rather than re-running successful phases speculatively. If no
notification mechanism is available, make one bounded status check and return
the pending run/phase instead of installing polling automation or repeatedly
sleeping/reading. Keep existing finite subprocess/notary waits and diagnostic
retention. A timeout is a stopped/failed check, not success. Retries, redispatch,
credential changes and publication require their own authorization; never
force/delete a tag or overwrite a release to recover.

After the dispatch-capable workflow is merged to the **default branch**, open
**Actions → CI → Run workflow** and select a branch for ordinary validation.
`FOURD_ENABLED` still controls optional hosted 4D steps; CLI-only green is not
compiled-host green.
Initialized branch/PR/manual CI with `FOURD_ENABLED=true` retains
**compiled-component** for 30 days: the accepted `dist/<repository>.zip` and
adjacent `.acceptance.json` bind the ZIP hash/size, revision, native manifests,
tool4d identity and source/compiler/final compiled-host evidence. Download it
from the run's **Artifacts** without publishing a release. Separate
**component-acceptance-diagnostics** preserves completed reports on failure.
`scripts/accept_hosted.py --repository OWNER/REPOSITORY --tool4d PATH` consumes
all three same-revision native artifacts/manifests (each `execution:"passed"`),
reassembles and runs the actual source/compile/package/final-host pipeline.
It never publishes or marks unexecuted Intel/Windows 4D as passed. Its default
inspection path is unsigned; release signing uses the explicit
`--require-apple-signing` path documented below.

Keep exactly `.github/workflows/ci.yml` (**CI**), `bump-version.yml`
(**Bump version**) and `build.yml` (**Build**). CI remains nonpublishing.
**Actions → Bump version → Run workflow** accepts **mode** patch/minor/major,
default patch. Explicitly select the branch to receive the source-only version
commit; it is not restricted to main. `scripts/release_source.py bump` validates
the immutable dispatch SHA, clean checkout and current synchronized version
surfaces before writes. The selected branch's current remote HEAD must equal
the dispatch SHA exactly; if it moved, Bump fails rather than rebasing or
switching revisions. It stages bounded surfaces, commits only synchronized
source metadata and non-force pushes only that selected branch. It creates no
tag, build, release or workflow dispatch, and never starts Build automatically.
Its `next_version` call bumps the greater of the current authoritative source
version and the highest stable `X.Y.Z`/legacy `vX.Y.Z` history, ignoring
prereleases and build metadata. With no stable tag, it bumps source alone
(initial `0.1.0` becomes `0.1.1` with patch). Every successful Bump increments
source; there is no old retry-candidate reuse. The bounded version plan updates
only validated configured source surfaces: package/template,
selected-language version declarations, current CLI/class docs and version
contracts. It must not rewrite dependencies, history or arbitrary feature data.
Feature adaptations adding version fields must extend this bounded registry.

**Actions → Build → Run workflow** requires **main** and has only the optional
**require_apple_signing** checkbox. There is no version, tag, bump or mode input.
It checks out the immutable full `github.sha` selected at dispatch, not a later
branch HEAD, and derives stable prefix-free `X.Y.Z` from synchronized source
metadata. Before expensive reusable CI, `release_source.py` preflight requires
a main dispatch, checkout HEAD exactly equal to `github.sha`, and clean/exact
source. It validates every version surface with `bump_release.plan` at the
same source version, requires that source version to exceed stable published
`X.Y.Z`/legacy `vX.Y.Z` tag history, and checks remote tag/release collisions
and main ancestry. Preflight refreshes remote-tracking refs but mutates no source
or release. Main may advance later:
the dispatch SHA must remain in main's ancestry, but Build never switches SHA
to follow the newer main HEAD.
Build never commits version changes. Its full dispatch SHA is passed unchanged
to reusable CI, acceptance and every assembly/compiler/signing/publication
checkout; all existing package/compiler/runtime/provenance/signing gates remain.
CI handles branch pushes, PRs and dispatch, never tags; the bot's `GITHUB_TOKEN`
source-version commit does not recursively trigger CI. Build explicitly calls reusable CI
with `release_call:true` to avoid a second optional compiled inspection.
The same input commit must bind all native manifests and acceptance evidence.
Signing policy is read at that exact dispatch SHA. Manual
`require_apple_signing` can escalate an unsigned version but cannot downgrade
a policy-required signed version.
Only after compilation and exact final-host success does `release_assets.py`
verify downloaded ZIP/DMG/proof bytes, accepted hashes/sizes, revision, native
manifests and full source/final-host contracts. It then verifies main ancestry,
checks remote tag/release collisions again, atomically creates a new
prefix-free `X.Y.Z` tag at the accepted SHA and invokes `gh release create --verify-tag`
with a literal validated asset list. GitHub's create-ref API rejects collisions
even at the same SHA; no force/update/delete operation or release clobber is used.
No automatic tag-push release trigger exists.
Failed builds leave source metadata unchanged and create no tag/release before
final asset acceptance. An authorized retry of Build can use the same source
version when no remote collision exists; it does not require another bump.
A failure after tag creation retains the tag and requires explicit inspection;
never delete/force a tag, overwrite a release or pretend a failed stage passed.
Do not manually dispatch publication or create a tag without user permission.
The new workflow is not available in the default template before its PR merges.

## 7. Report evidence, not assumptions

Use a per-check status matrix. `passed` means **executed successfully for the
identified revision/artifact/platform**. `not_run` means no execution evidence;
it never means passed, waived or release ready. Report `failed` for an executed
failure and attach the command/reason. Preserve blocked/unsupported explanations
without converting them into a success.
The helper's JSON statuses are strictly `passed` / `failed` / `not_run`.

| Check | Evidence required for `passed` | Typical local limitation |
| --- | --- | --- |
| Python / icon checks | Exact command and result | Does not prove 4D loading |
| Native CLI per target | Execution on that OS/architecture | Cross-built targets remain `not_run` for native execution |
| Source 4D host | Fresh host report and actual namespaced calls | Only the observed native host |
| 4D compilation | Fresh success, targets/project and input digest | Not host/package acceptance |
| ZIP/package integrity | Names, source stripping, modes, explicit directories, libraries | Not runtime loading |
| Compiled 4D host | Unpacked artifact, fresh report, compiled mode true | Intel/Windows 4D remain separate checks |
| Dependency-manager install | Actual published asset download/load | Manual local install is not this check |
| Signing/notarization | Final signed artifact checks, Accepted notarization when enabled | Optional; normally `not_run`, unsigned stated clearly |

Summarize revision/input digest, language, tool versions/platform, exact commands,
artifact/report paths and unvalidated checks. Never describe an Apple Silicon
local package as fully cross-platform accepted. Partial acceptance is **NOT
release ready**; publication requires all mandatory gates. Optional unsigned
signing status alone is not a blocker for this unsigned pipeline.
Report the **actual** compiler used: Go **1.25.1** was available in the local
November 1 observation, whereas **1.26.10** is the CI pin and the source minimum
is 1.23. Do not relabel a local 1.25.1 build as a 1.26.10 build.

### UUID adoption case study — November 1, 2026

[miyako/UuidTest](https://github.com/miyako/UuidTest) is an actual destination
created from this template, not a rename of the original template repository.
Its exact repository/component/project/catalog/package case is `UuidTest`;
namespace also happens to be `UuidTest`, but that is a choice, **not an equality
requirement**. CLI `uuid-test` and feature class `UUIDv7` are independent.
See its [documented local acceptance](https://github.com/miyako/UuidTest#build-and-local-acceptance),
[feature class](https://github.com/miyako/UuidTest/blob/main/component/UuidTest/Documentation/Classes/UUIDv7.md)
and [RFC 9562 §5.7](https://www.rfc-editor.org/rfc/rfc9562.html#section-5.7).
Exact evidence: [miyako/UuidTest#1](https://github.com/miyako/UuidTest/pull/1),
[hosted CLI run](https://github.com/miyako/UuidTest/actions/runs/41263891932),
and [template scalar/lipo fixes #2](https://github.com/miyako/4d-component-template/pull/2).

The example replaced greetings with Go stdlib-only UUIDv7 generation and updated
the API, CLI tests, native smoke tests and real source/compiled host fixture.
It exercised free tool4d 20.7/101905 on Apple Silicon, same-source Go cross
artifacts, universal assembly and source-stripped package loading. Lessons:
initializer text is description-only; rename does not implement UUIDs; scalar
guards and strict NUL search matter in real 4D; lipo argument order and explicit
ZIP directories matter; Go runtime notices still need redistribution.
Fresh subprocess randomness is not monotonic across calls, and a collision
sample is not a uniqueness proof. Its reported local success does not prove
Windows 4D, native Intel 4D, dependency-manager downloads or signing. The cited
hosted run separately passed native macOS Intel/ARM and Windows CLI jobs with
Go 1.26.10; local Rosetta CLI execution is a different observation. A 10,000-item
same-millisecond no-duplicate sample was empirical evidence, not a mathematical
guarantee. These links describe a dated observation, not a substitute for
rerunning the destination's acceptance or a promise about future repository state.

### Definition of done and final evidence

For a requested local implementation, finish the feature, replace every
greeting-specific surface, run exact feature/error tests, validate licenses and
resources, compile fresh, and load the **exact final ZIP's** unpacked component.
Report unsupported/unavailable checks as `not_run`; local success remains
`release_ready:false`. Approved publication additionally requires a main-only
Build dispatch of synchronized source metadata at an immutable full SHA,
all required native artifact/tests, hosted 4D opt-in and the final
package-host gate. Signing is optional by default; a listed version or explicit signed dispatch
requires every signing/notarization gate to pass before tag creation/publication.

The final handoff must identify the repository/namespace/class/CLI/language,
revision and input provenance, exact commands/results, tool versions, stable ZIP
path plus SHA256, adjacent evidence JSON and a per-platform status matrix.
Use the helper's actual `steps`, `artifact`, `finished`, `result` and
`release_ready` fields rather than inventing a success summary:

```json
{
  "result": "partial",
  "finished": true,
  "release_ready": false,
  "artifact": {"path": "dist/NAME.zip", "sha256": "<actual SHA256>"},
  "steps": {
    "source_host": {"status": "passed"},
    "compiled_host": {"status": "passed"},
    "windows_4d": {"status": "not_run", "reason": "runtime unavailable"}
  }
}
```

This is an abbreviated shape; replace `NAME` and hash with observed values,
retain the helper's actual positive byte count and all real rows. Never label a missing runtime, finite sample,
cross-build or optional skipped workflow as passed.

| Symptom | Deterministic next check / stop criterion |
| --- | --- |
| Undefined namespaced constructor / Object expected | Compare actual XML namespace, class filename and host `cs.<namespace>.<class>`; ensure original fixtures were not copied over initialized files. Read phase/raw host errors. |
| Permission denied / Not a directory at launch | Distinguish expected non-executable negative probe from a real failure. Verify executable bit and File constructor path kind; Python macOS paths are POSIX, not `.platformPath`. Never fall back to PATH or a shell. |
| Compile exits zero but no success JSON | Stop: inspect fresh `build/compile-status.json` and compiler diagnostics; exit code alone is insufficient. |
| Stale input/output SHA256 | Rebuild all affected CLI targets, assemble, clear DerivedData through the compiler helper, recompile and retest. Never edit the marker to match. |
| Compiled loader crash / interpreted package | Verify explicit nested ZIP directory records, external native Libraries, source stripping and exact `Is compiled mode`; keep the established packer. |
| Tool download/checksum/config failure | Check `package.json.tool` or complete overrides, official fixed URL and independently approved SHA256; do not fall back to `latest`, bypass the hash or redistribute vendor tools. |
| Final host unfinished/failed | Stop and preserve status/phase/errors. A previous ZIP, successful compile or six completed cases cannot approve this run. |

## 8. Icons, licensing and optional signing

Edit original `assets/icon-source.svg` within the supported rectangle/polygon
renderer; regenerate **both** Resources icons. `logo.png` is real RGBA PNG and
`logo.svg` embeds its byte-identical PNG data URI: **PNG-in-SVG**, not the reverse.
For arbitrary artwork use a pinned real SVG rasterizer. Never rename SVG to PNG.

The scaffold is MIT; retain its copyright/license. Review all bundled tools,
static libraries and language runtimes separately and include required notices
in `Resources/licenses/`. Vendor tool4d is separately licensed and not bundled.
No third-party feature algorithm/artwork should be copied without license review.
The initializer copies the selected Go BSD / Rust MIT baseline notice from
`cli-starters/<language>/licenses/` to component `Resources/licenses/`; the
packer requires it. The Go notice was checked against Go 1.25.1 and the CI pin
1.26.10; the Rust MIT option against Rust 1.99.1. These are **not** blanket
licenses for every dependency/runtime exception. Review the Rust distribution's
`COPYRIGHT-library.html` and include applicable third-party notices; review
Microsoft static-CRT redistribution terms for Windows C++. Additional DLLs,
dylibs, statically linked dependencies and copied code need their own notices.
Never claim this deterministic file-presence check is a legal audit.

Signing is not a prerequisite for unsigned development/package acceptance.
Gatekeeper/quarantine may still block unsigned downloads; do not add a runtime
trust bypass. The implemented signing path stores credentials in **secrets only**,
uses hardened runtime/timestamp verification, fails closed, requires notarization
`Accepted`, cleans temporary keychains/certificates and owned mounts even on
failure, and tests the exact final signed ZIP's unpacked compiled component.
Bare CLI executables are not stapled: the DMG is the notarized/stapled container.
The ZIP is repacked from its actual final mounted component, preserving the
existing `.4dbase` layout without introducing an application `Contents/` tree.

### Version policy and Apple secrets

`release-policy.json` is independent of template identity and is preserved by
initialization. It defaults to
`{"schema":1,"apple_notarized_versions":[]}`. List exact component versions
without `v` to require signed releases; commit the policy before running Build
for that next version. A missing policy or unlisted version means unsigned, malformed
policy fails closed. Manual release `require_apple_signing` and the helper's
`--require-apple-signing` can only escalate, never downgrade policy.
`scripts/sign_release.py policy --root .` emits `apple_signing` without accessing
secrets; the workflow passes credentials only to the policy-true stage.
Merely registering secrets does not change policy, and no secret below is
required by the free local compiler, unsigned CI inspection or unsigned release.

The signed release runs the same verified native assembly, source-host,
compilation and deterministic unsigned packaging pipeline, then tests the
unsigned compiled ZIP. `sign_release.py sign --root . --require-apple-signing`
requires the checkout HEAD to match candidate `RELEASE_SHA`/`RELEASE_TAG`,
validates compiler input/output provenance and reproduces the fresh unsigned
ZIP before signing an isolated copy. It signs the universal CLI and native
Mach-O Libraries, verifies Developer ID/team/runtime/timestamp, signs a DMG,
requires actual notarization JSON `Accepted`, staples and validates it, and
rebuilds the final ZIP from that mounted final DMG. Original compiler outputs
and markers are not edited. The source-host gate is enforced by the orchestrator;
the helper does not pretend a source-host filename is its input contract.

`accept_hosted.py --require-apple-signing` reruns actual host assertions against
the final ZIP after signing. It revalidates original compiler provenance and
binds all final asset hashes, refusing changes during host testing. Stable
outputs are `dist/<repository>.zip`, `.dmg`, `-signing.json` and
`.acceptance.json`; the latter contains distinct source/compiler/unsigned-host/
signing/final-host evidence. Signing timestamps and notarization are not
bit-for-bit reproducibility promises. Windows Authenticode is not implemented.
Never claim a template fixture was Apple-signed using another destination's
credentials or that a successful CLI/notary check proves native Intel/Windows
4D loading or Dependency manager installation.
The signing implementation and its mocked-tool tests originate from
[miyako/UuidTest 7e0cfab](https://github.com/miyako/UuidTest/tree/7e0cfab983a582994e12c79c09aa47a205ea4bfc)
after its [actual release run](https://github.com/miyako/UuidTest/actions/runs/41270374443)
and public-download signing/stapling/final compiled-host verification succeeded.
Its [public proof](https://github.com/miyako/UuidTest/releases/download/v0.1.0/UuidTest-signing.json)
keeps `hostValidation:"required-after-signing"`; the separate final host report
fulfills that requirement. Do not rewrite the helper's proof to pretend it ran
the caller's host stage.

For approved signed releases, register private values in the **destination**
repository under **Settings → Secrets and variables → Actions → Secrets → New
repository secret**. Template creation does not inherit repository secrets or
variables. Never place certificates/private keys/passwords in source, workflow
YAML, logs, package metadata or a PR.

| Repository Actions secret | Exact value/type |
| --- | --- |
| `APPLE_DEVELOPER_ID_CERTIFICATE` | Base64 of an exported **Developer ID Application `.p12` including its private key**. Export identity and private key together from Keychain Access; a public `.cer`, PEM certificate or filename alone is insufficient. |
| `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD` | The password chosen for that `.p12` export; not an Apple account or temporary keychain password. |
| `KEYCHAIN_PASSWORD` | An arbitrary strong randomly generated password for a temporary workflow keychain, independent of account passwords. |
| `NOTARYTOOL_APPLE_ID` | The Apple account **email address** authorized to notarize for the Developer team. |
| `NOTARYTOOL_TEAM_ID` | The Apple Developer **Team ID** for the signing identity and notarization account. |
| `NOTARYTOOL_PASSWORD` | An Apple **app-specific password** for notarization, **not the normal Apple account login password**. |
| `CODESIGN_APPLE_ID` | **Optional.** Not needed: the signing identity is read from the temporary keychain that holds the imported `.p12`, which must contain exactly one Developer ID Application identity whose team is `NOTARYTOOL_TEAM_ID`. If set, it pins that identity and the release fails when they differ. Value: the full identity, such as `Developer ID Application: Organization (TEAMID)`, or its SHA-1 fingerprint. **Not an email address.** |

Keep public compiler pins/hosted opt-in under package metadata and Actions
**Variables**, not Secrets. GitHub supplies the restricted publish job's
`GITHUB_TOKEN`; no additional personal-token secret is needed.

### User-owned credential setup and reuse

Inspect the **actual destination workflow** before recommending secrets.
This template's [Build workflow](.github/workflows/build.yml) passes the
seven names above only to its `apple_signing == 'true'` step (six required, the
identity pin optional); its
[CI workflow](.github/workflows/ci.yml),
[Bump version workflow](.github/workflows/bump-version.yml) and unsigned releases need none.
Adapted unsigned or Windows-only workflows may likewise need no Apple secrets.
Do not add signing requirements or triggers merely to use a helper.

The **user owns all secret operations**. Agents must never execute
[scripts/set-release-secrets.sh](scripts/set-release-secrets.sh),
`gh secret set`, or real Keychain credential commands, read credential values,
choose certificates, ask for secrets in chat, or log/commit values.
Agents may inspect only names and timestamps before and after user setup:

```sh
gh secret list --repo OWNER/REPOSITORY
```

For user-approved signed-release setup, the user runs the following in their
own macOS terminal, from the destination repository root. Prerequisites are
zsh, the macOS `security` CLI, OpenSSL, base64, tr, mktemp, rm and authenticated
GitHub CLI (`gh auth login`). No installed personal Copilot skill is required:

```sh
zsh scripts/set-release-secrets.sh OWNER/REPOSITORY
```

The helper reuses the macOS login Keychain service `4d-plugin-release`;
the historical service name does not imply a plug-in architecture. A new
repository does **not** require a new certificate. It sets exactly the six
required secrets above. The signed workflow infers the signing identity from
the imported certificate, so `CODESIGN_APPLE_ID` is not needed; a user who wants
to pin the identity may set it separately. It is not a notarization email.

For first-time setup when no certificate is stored, or deliberate replacement,
the **user selects** a Developer ID Application `.p12` exported with its private
key and supplies its path. Multiple repositories can share the stored values:

```sh
CERT_P12=/path/to/DeveloperID.p12 zsh scripts/set-release-secrets.sh OWNER/REPOSITORY OWNER/ANOTHER
```

`CERT_P12` replaces the stored certificate; it does not replace an already
stored password. Missing other values are entered using hidden Keychain input.
Only a missing-item Keychain status prompts for a new value; other lookup errors
stop with a name/status diagnostic rather than overwriting inaccessible items.
`KEYCHAIN_PASSWORD` must be an independent strong temporary-CI-keychain password.
The helper checks that the stored certificate can open with the stored password,
displays its subject and expiry, and asks for user confirmation before uploads.
It temporarily decodes the certificate under `umask 077` and removes that file
on exit. It does **not** explicitly verify private-key presence, enforce
Developer ID Application identity, or reject expiry: the user must check those
properties; the existing release signing gates remain authoritative.
Although values are not printed, `security` CLI writes pass values as process
arguments; run only in a trusted local session, not under tracing or command
logging. The helper is not a promise of protection against local process inspection.

To replace a stored value, the user deletes its item by **service and account**,
not its display name, then reruns the helper:

```sh
security delete-generic-password -s 4d-plugin-release -a SECRET_NAME
```

For `SecKeychainItemImport: Unable to decode`, first compare exact workflow
secret names and timestamps; missing/misnamed secrets are not source failures.
An incorrect import passphrase can mean the stored `.p12` and password mismatch:
the user replaces the relevant item or supplies their chosen `CERT_P12` and,
if needed, replaces `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD`. A missing-item
message can also reflect denied Keychain access. OpenSSL 3 may reject legacy
RC2/3DES `.p12` encryption; the helper retries with `-legacy`, which LibreSSL may
not support. Both failed attempts stop before uploads.

Uploads are sequential, not transactional: an error can leave earlier secrets
or repositories updated. After user completion, inspect names/timestamps again
(the six required names; `CODESIGN_APPLE_ID` only if the user pinned one); never
inspect their values.
Setup alone changes neither signing policy nor publication authorization.
Separate user permission is required for main-only **Build**, whose only input
is optional `require_apple_signing`; version comes from synchronized source at
the immutable dispatch SHA. **Bump version** is a separately authorized,
source-only patch/minor/major action on the explicitly selected branch.
Never dispatch Build as a setup check, invent version/tag/bump inputs or a tag-push trigger,
or prefix component SemVer tags with `v`.

## Official convention references

Verified November 1, 2026:
[Copilot repository instructions](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/add-custom-instructions/add-repository-instructions),
[agent skills](https://docs.github.com/en/copilot/concepts/customizations/agent-skills),
[adding skills](https://docs.github.com/en/copilot/how-tos/copilot-on-github/customize-copilot/customize-cloud-agent/add-skills),
[CLI skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills).
Supported repository convention is `.github/skills/<lowercase-hyphen-name>/SKILL.md`
with required YAML `name` and descriptive `description`; the agent selects
relevant skills. Surface/version support and actual session discovery vary.
Repository instructions point here so the guide remains usable without skill
loading. Do not invent a skill registration action or claim automatic invocation.

4D references:
[component/dependency naming](https://developer.4d.com/docs/Project/components),
[SystemWorker](https://developer.4d.com/docs/API/SystemWorkerClass),
[Position](https://developer.4d.com/docs/commands/position),
[Compile project](https://developer.4d.com/docs/commands/compile-project),
[error handling](https://developer.4d.com/docs/20/Concepts/error-handling).
