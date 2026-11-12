# 4D CLI component template

An agent-ready **real 4D component project** wrapping a native CLI on macOS and
Windows. Choose **Go, Rust or C++**; initialization keeps only that starter.
The working greeting example uses the same deterministic UTF-8 JSON protocol in
each language. Replace the example with your feature, not the generic adapter.

## Start here: THINK / ASK → RUN

Read [AGENTS.md](AGENTS.md), the canonical detailed implementation/acceptance
playbook. Resolve exact GitHub identity/case, one language, an independent unique
namespace, CLI basename and feature semantics **before** initialization.
Do not initialize the original template repository; check its actual remote
using the playbook's identity rules.

For Copilot, the short [.github/copilot-instructions.md](.github/copilot-instructions.md)
points to that guide; the task-specific
[4d-cli-component skill](.github/skills/4d-cli-component/SKILL.md) uses the
[official project skill convention](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills).
Supported clients select relevant skills, but file presence does not guarantee
session discovery/invocation. In Copilot CLI, `/skills reload` and
`/skills info 4d-cli-component` inspect discovery; these are slash commands, not
shell commands. Read the playbook directly if the client does not load the skill.

The playbook includes a [November 1, 2026 UUIDv7 adoption case study](AGENTS.md#uuid-adoption-case-study--november-1-2026)
with real source/compiled host validation and explicit limitations.

## Use this template

Click **Use this template → Create a new repository**, then prompt your agent:

> Implement a 4D component in this repository that [FEATURE]. Use [Go/Rust/C++],
> unique class namespace [NAMESPACE], CLI basename [CLI_NAME], and these
> constraints: [DEPENDENCIES, LICENSE, LIMITS, ERROR BEHAVIOR]. Follow AGENTS.md,
> initialize the exact destination repository name, implement the feature and
> its host API/docs/tests, and deliver a compiled component release. Report
> unvalidated platforms and required setup honestly.

For a local package rather than publication, say so explicitly. Unsigned local
free tool4d acceptance needs no signing secret, license activation, tag/release
or repository settings. Partial local validation is **NOT release ready**.

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

After initialization, optional `scripts/rename_feature.py --root . --class NAME`
rewrites only the known Greeting identity/configuration registry. It does **not**
implement the new API or protocol. Follow the playbook's full replacement
inventory, including build smoke tests, host assertions and completion metadata.

The uninitialized template is **not releasable** and normal template CI does not
install three unrelated language toolchains.

Before initialization or workflow tests, install the pinned development parser
(preferably in a virtual environment) and validate the inherited contract:

```sh
python3 -m pip install -r tooling/requirements-workflow.txt
python3 scripts/workflow_contract.py --root .
```

See [the enforced `workflow-contract.json` configuration](AGENTS.md#enforced-generated-contract-and-bounded-configuration)
and [release entry points and handoff rules](AGENTS.md#release-entry-points-handoff-and-bounded-waiting).

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

### Choose the architecture, not a hybrid

| Choice | Execution and installation |
| --- | --- |
| **CLI-backed component: this template** | Host code calls component classes, which launch a bundled native CLI in a separate process through `4D.SystemWorker`. Install the component via the Dependency manager or `Components/`; its executable ships in `Resources/bin/`. |
| **Native 4D plug-in: separate architecture** | Native code integrates through the 4D plug-in SDK. Install the plug-in in the host using 4D's supported plug-in installation mechanism, not inside a component. |

If native 4D SDK integration is required, choose the separate host-installed
plug-in architecture and make its host installation and compatibility requirements
explicit. Do not generate or recommend a component-over-plug-in hybrid as a
self-contained component solution. A component cannot privately load or deploy
a 4D plug-in; wrapping plug-in commands cannot hide, eliminate or satisfy the
host plug-in installation requirement. This is a deployment boundary, not a
blanket restriction on host code calling commands from an installed plug-in:
such a plug-in remains an explicit host dependency.
See the canonical [architecture-selection rules](AGENTS.md#architecture-and-deployment-boundary).

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
tests/host/contract.json              feature/execution host assertion registry
tests/cli-contract.json               configurable native CLI smoke vectors
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
| `component-cli greet --name "4D"` | 0 / `{"protocol":1,"message":"Hello, 4D!"}` + LF / empty |
| `component-cli --version` | 0 / `{"protocol":1,"version":"0.1.0"}` + LF / empty |
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

These instructions install the **CLI-backed component and its bundled executable**,
not a native 4D plug-in. Component packaging and Dependency manager installation
do not install a plug-in in the host or satisfy that separate requirement.

In the host's Dependency manager add **GitHub** dependency `OWNER/REPOSITORY`
and choose the released tag/version. The asset must be exactly `REPOSITORY.zip`.
Alternatively declare in the host's `Project/Sources/dependencies.json`:

```json
{
  "version": 2100,
  "dependencies": {
    "hello-tools": {"github": "OWNER/hello-tools", "tag": "0.1.0"}
  }
}
```

Reload the host and use your namespace. Manual installation: unzip and copy
`REPOSITORY.4dbase` into the host's `Components/` folder.
Local source dependencies point at the component package root, not the anchor.
`tests/host/environment4d.json` documents this mapping; automated runtime checks
install an isolated copy under `Components/` to test actual component loading.

### Release versions and Dependency Manager tags

Use **prefix-free component versions and tags**: `0.1.0`, not `v0.1.0`.
The version in `template.json`/`package.json`, new release tag and signing proof
must agree exactly. Build publishes stable `X.Y.Z` tags; a GitHub release
display title cannot repair a prefixed or otherwise incompatible tag.
This component release rule is not a native 4D plug-in tag convention.

The official [Follow 4D version guide](https://blog.4d.com/follow-4d-version-a-smarter-way-to-manage-your-dependencies/)
describes a separate **host-version-aligned** rule: LTS tags `x.y.p` (e.g.
`20.2.3` for 4D 20.2) and R-release tags `xRy.p` (e.g. `20R3.2`).
An ordinary component release `0.1.0` does **not** imply Follow4D matching or
host compatibility; select an ordinary tag/version rule instead.
This SemVer pipeline does not implement R-release tag publication and rejects
`20R3.2`. Host-aligned distribution requires an explicit versioning/compatibility
contract, not just removing `v` or changing the release title.

Existing published `vX.Y.Z` tags/releases are left intact. The planner reads
legacy stable tags alongside prefix-free stable tags to avoid version
downgrades, but emits only prefix-free new tags for newly accepted builds.
There is no automatic aliasing, retagging or reuse of old acceptance/signing
proofs. Consumers pinned to old tags must be migrated explicitly. Upstream
Actions versions and historical external release links are unchanged.

## Build, validate and release

For read-only JSON configuration/platform/tool inspection and local orchestration:

```sh
python3 scripts/doctor.py --root .
python3 scripts/doctor.py --root . --tool4d /path/to/tool4d
python3 scripts/accept_local.py --root . --repository OWNER/REPOSITORY \
  --tool4d /path/to/tool4d
```

Read the scripts' `--help` and [AGENTS.md](AGENTS.md) for prerequisites/stages.
`accept_local.py` invokes existing builds/assembly/source-host/compile/pack and
compiled-host checks, records `build/acceptance.json` and, when packing succeeds,
produces `dist/REPOSITORY.zip`. Optional `--cross` produces nonnative **Go-only**
artifacts; Rust/C++ cross mode is explicitly unsupported. Cross-building is not
native execution evidence. Report `not_run` separately from `passed`: even a
successful Apple Silicon compiled-host run is not full release readiness.
With `--cross` on Apple Silicon, Intel CLI vectors may also run through available
Rosetta, recorded separately from native execution. Report the actual local
toolchain (Go 1.25.1 observed), not the CI pin (Go 1.26.10).

For **Go on native macOS**, the explicit three-target artifact example is:

```sh
python3 scripts/accept_local.py --root . --repository OWNER/REPOSITORY \
  --tool4d /path/to/tool4d --cross
```

Without `--cross`, assembly still needs current artifacts and
`build-manifest.json` files for **all three targets**. For Rust/C++, restore
executables/manifests from same-commit native CI into `build/<target>/`; unsupported
cross mode is not a substitute. Manifests bind source/config/package inputs,
Git commit and binary hash; assembly rejects missing/stale/mixed artifacts.
Acceptance uses strict `passed` / `failed` / `not_run` statuses and separate
CLI build, native CLI test and Rosetta steps. Source/compiled host evidence is
preserved in `build/source-host-status.json` and `build/compiled-host-status.json`,
alongside `build/compile-status.json` and `build/acceptance.json`.
Successful local completion still reports `result:"partial"`,
`finished:true`, `release_ready:false`; failures save unfinished failed evidence.
macOS system-library checks do not inspect Windows native DLL/runtime dependencies.
The stable final pair is `dist/REPOSITORY.zip` and
`dist/REPOSITORY.acceptance.json` (ZIP SHA256, actual tool versions and embedded
host evidence). Copy both before disposing of a temporary worktree. The latest
attempt, including failures, remains in `build/acceptance.json`.

```sh
python3 -m unittest discover -s tests -v
python3 scripts/generate_icons.py --check
python3 scripts/build_cli.py --target macos-arm64
```

Use your native target: `macos-x64`, `macos-arm64`, `windows-x64`.
CI builds/tests only the selected language in native hosted jobs, uploads
same-commit binaries and combines macOS slices using `lipo`.
CI executable artifacts are **not compiled component releases**.
The correct architecture verification order is
`lipo <universal-file> -verify_arch x86_64 arm64`; do not put the filename after
the architecture list or mix resources from different source revisions.

### Real 4D tooling and configuration

[tool4d](https://developer.4d.com/docs/20/Admin/cli#tool4d) is the official **free
standalone headless tool** used by the reference component pipelines. This flow
does not require a license/serial secret. Full IDE, Server and merged applications
have separate vendor licensing. Never bundle tool4d into the MIT component.

Hosted configuration belongs in the **generated repository** under
**Settings → Secrets and variables → Actions → Variables → New repository variable**,
separate from the private secrets documented below. Template creation
does not inherit these variables. Only the hosted 4D opt-in is required; the
approved public compiler pin is already in `package.json.tool`.

| Variable | Value |
| --- | --- |
| `FOURD_ENABLED` | `true` to enable vendor tool download/use; mandatory for release |
| `TOOL4D_URL` | Optional paired override: `https://resources-download.4d.com/release/20.x/20.7/101905/mac/tool4d_arm64.tar.xz` (observed macOS ARM64 build) |
| `TOOL4D_SHA256` | Optional paired override: `40a5d177a4f73165f52abf6ec8000249d81411c41353ccf258cece8e74639261`; verify the approved archive hash out of band |

Supply URL/hash overrides together or neither; incomplete pairs fail.
GitHub automatically supplies `GITHUB_TOKEN`; only Bump version's source commit
and Build's publication jobs receive `contents: write`. Do not register it or a
personal token as another secret. Repository rules must permit the workflow bot's
non-force version commit to the explicitly selected branch; a protected-branch
rejection stops Bump version without bypassing those rules.
None of these variables or the automatic token enables signing.

Reference URL form:
`https://resources-download.4d.com/release/20.x/20.7/BUILD/mac/tool4d_arm64.tar.xz`.
`latest` is discovery-only/mutable and rejected by the downloader; checksum
mismatch fails. The fixed **20.7 build 101905** archive was downloaded and used
locally, SHA256
`40a5d177a4f73165f52abf6ec8000249d81411c41353ccf258cece8e74639261`.
The pin is public versioned metadata in `package.json.tool`, not a credential.
This archive is macOS ARM64 only, not a native Intel/Windows runtime.
Local download checks native host compatibility plus safe extraction:
The fixed vendor URL currently redirects to the official `builds2.4d.com`
CDN. Every redirect is checked before following: only the exact vendor hosts
over HTTPS/default TLS port, without URL credentials, are permitted. Expiring
CDN query parameters are transport details, not user-configurable compiler pins;
the archive must still match the approved SHA256 before extraction.

```sh
python3 scripts/ci_config.py download-tool4d
```

No URL/hash variables are needed for that default. A complete explicit CLI pair
overrides a complete environment-variable pair, which overrides the manifest.
For an approved alternate pin only:

```sh
python3 scripts/ci_config.py download-tool4d --root . \
  --url https://resources-download.4d.com/release/20.x/20.7/101905/mac/tool4d_arm64.tar.xz \
  --sha256 40a5d177a4f73165f52abf6ec8000249d81411c41353ccf258cece8e74639261
```

No imagined setup action or unpinned external compiler is used.

```sh
python3 scripts/test_4d.py --tool4d /path/to/tool4d
python3 scripts/compile_component.py --tool4d /path/to/tool4d
python3 scripts/package_component.py --repository OWNER/REPOSITORY \
  --tag 0.1.0 --unpack-test
python3 scripts/test_4d.py --tool4d /path/to/tool4d \
  --component build/release-test/REPOSITORY.4dbase
```

The driver runs real `Compile project` for `x86_64_generic` and
`arm64_macOS_lib`, requiring a **fresh successful JSON result**. Errors or absent
results fail even when tool4d exits zero. It cleans generated DerivedData before
recompile (stale compiled projects can otherwise be treated as sourceless).
Native Libraries and CompiledCode are required, not source-shaped substitutes.
The compile marker binds inputs with `input_sha256` and generated
DerivedData/Libraries with `output_sha256`, rejecting changed outputs at packaging.

Bump version synchronizes source version metadata in a separate source-only
commit. Build derives the stable version from synchronized source metadata at
the immutable dispatch `github.sha` on main and builds all CLI targets from that
exact full SHA. It never bumps the version or commits source. It compiles after
Resources assembly, packs `REPOSITORY.zip`,
and **loads the unpacked compiled package in a real 4D host before publishing**.
Uninitialized/misnamed projects, missing tool/binary/library, failed compile or
failed host test fail closed. Only after downloaded assets pass verification
does it create the prefix-free `<version>` tag and the GitHub release. Built-in `GITHUB_TOKEN`
performs the separately authorized source commit and final tag/release operations;
no personal token is needed.

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
`Libraries/` here contains compiler-generated component support, not a private
4D plug-in backend. Bundling CLI dependencies does not authorize component-private
plug-in loading or replace host plug-in installation.

### Run workflows manually

After this workflow version is merged to the **default branch**, open
**Actions → CI → Run workflow** and choose a branch for validation.
Hosted 4D remains opt-in through `FOURD_ENABLED`; a CLI-only green run does not
prove compilation or host loading.
When `FOURD_ENABLED=true`, an initialized branch/PR/manual CI run also builds
the actual compiled component and tests its unpacked ZIP. Download
**Artifacts → compiled-component** from the completed run: it contains
`REPOSITORY.zip` and adjacent `REPOSITORY.acceptance.json`, retained for 30 days.
The evidence binds the ZIP SHA256/size, source revision, all three native build
manifests, actual tool4d identity and source/compiler/final compiled-host reports.
**component-acceptance-diagnostics** retains completed stages or failure details;
failed acceptance does not upload an accepted component. This inspection path
creates neither a tag nor a GitHub release and uses no Apple credentials.
Intel/Windows **4D**, installed-release downloads and signing remain separate
checks; hosted native CLI execution is not native 4D execution.

The same non-publishing stage can be invoked after restoring same-revision
native binaries and `build-manifest.json` files under `build/<target>/`:

```sh
python3 scripts/accept_hosted.py --root . --repository OWNER/REPOSITORY \
  --tool4d .tools/tool4d.app/Contents/MacOS/tool4d
```

It requires `execution:"passed"` in each verified native manifest, reassembles
resources, source-tests, compiles, packs and compiled-host-tests before saving
stable evidence. Cross-only manifests are not hosted native evidence.

There are three workflows: nonpublishing **CI** (`ci.yml`) and two manual
release-facing actions, **Bump version** (`bump-version.yml`) and **Build**
(`build.yml`). They deliberately separate source version changes from publication.

Open **Actions → Bump version → Run workflow**, explicitly select the branch
to receive the commit, and choose **mode**: **patch** (default), **minor** or
**major**. Bump version is not main-only. `scripts/release_source.py bump`
validates immutable dispatch SHA, clean checkout and all current version
surfaces before writes. The selected branch's current remote HEAD must exactly
equal that dispatch SHA; if it moved, Bump fails rather than switching revisions.
It stages bounded surfaces, commits only synchronized source metadata and
non-force pushes only the selected dispatch branch. It creates no tags, builds,
releases or workflow dispatch and does not automatically start Build.
Its `next_version` call uses the greater of current authoritative source version
and the highest stable `X.Y.Z`/legacy `vX.Y.Z` history as its base (not tag dates;
prerelease and build-metadata tags are ignored). With no stable tag, it bumps
source alone: for `0.1.0`, patch gives `0.1.1`, minor `0.2.0`, major `1.0.0`.
Every successful Bump increments source; it never reuses an old retry candidate.
Malformed/inconsistent metadata or a proposed downgrade fails before committing.
The generic version helper updates package/template metadata, selected-language
version declarations, version contracts and current CLI/class documentation
without rewriting unrelated dependency or historical versions.

After that source version is on main, separately authorize
**Actions → Build → Run workflow** on **main**. Its only input is the optional
**require_apple_signing** checkbox: there is no version, tag, bump or mode input.
Build checks out the immutable full `github.sha` selected at dispatch, not a
later branch HEAD, and derives stable prefix-free `X.Y.Z` from synchronized
source metadata. Before expensive reusable CI, `release_source.py` preflight
requires a main dispatch and checkout HEAD exactly equal to `github.sha`,
validates clean/exact source and all version surfaces using `bump_release.plan`
at that same version, requires source version to exceed stable published
`X.Y.Z`/legacy `vX.Y.Z` history, and checks tag/release collisions and main
ancestry. Preflight refreshes remote-tracking refs but mutates no source or release.
Main may advance afterward, but Build's
source SHA remains the dispatch SHA, never the newer main HEAD; that SHA must
remain in main's history. Build retains main-only publication and passes the same full SHA to
reusable CI, acceptance and every assembly/compiler/signing/publication checkout.
All existing package, compiler, runtime, provenance and signing checks remain
mandatory; source version derivation never substitutes for artifact acceptance.
CI runs on branch pushes, PRs and manual requests, not tag pushes; the bot's
`GITHUB_TOKEN` source-version commit does not trigger a recursive CI run. Build calls CI
explicitly and performs mandatory 4D acceptance separately, without duplicating
CI's optional compiled-package inspection.
Signing policy is read from that immutable dispatch SHA. The optional
**require_apple_signing** checkbox escalates an unsigned version to signed;
leaving it unchecked never downgrades a policy-required signed version.
Do not dispatch publication or create tags without approval. Merely opening
this PR does not make the new **Run workflow** button available in the default
template; the workflow file must first merge.

### Optional signing/notarization

**Unsigned is the default; signing is implemented and opt-in.**
`release-policy.json` has `schema:1` and an initially empty
`apple_notarized_versions` array. To require signing for a component release,
commit its exact intended version (without `v`) before running Build:

```json
{"schema":1,"apple_notarized_versions":["0.1.0"]}
```

The policy is independent of repository, namespace, CLI and selected language.
Initialization preserves it. A missing policy or an unlisted version is
unsigned; malformed policy fails closed. Alternatively, check
**require_apple_signing** for a manual release dispatch. That flag can only
escalate, never downgrade the version policy. The policy gate accesses no
secrets and emits `apple_signing`; only its signed branch receives the
credentials below. Unsigned CI/local acceptance and unsigned publication need
none of them. Registering credentials alone does not change the policy.

Follow the canonical [user-owned credential setup and reuse guide](AGENTS.md#user-owned-credential-setup-and-reuse)
before configuring signed releases. It includes the bundled
[user-run helper](scripts/set-release-secrets.sh), reuse of the existing macOS
login Keychain service, first-time setup/replacement and troubleshooting.
The helper uploads the six required secrets; the signing identity is read
from the imported certificate, so `CODESIGN_APPLE_ID` is optional. Agents never execute the helper
or read/set credential values. Secret setup does not authorize publication.

In the **newly generated repository**, register private credentials under
**Settings → Secrets and variables → Actions → Secrets → New repository secret**.
GitHub's **Use this template does not inherit secrets or repository variables**.
Never put credentials, exported certificates, private keys or account passwords
in source, `package.json`, workflow YAML, logs or a pull request.

| Repository Actions secret | Exact value/type |
| --- | --- |
| `APPLE_DEVELOPER_ID_CERTIFICATE` | Base64 encoding of an exported **Developer ID Application `.p12` containing the private key**, not just a public `.cer`, PEM certificate or its filename. Export the signing identity and private key together from Keychain Access. |
| `APPLE_DEVELOPER_ID_CERTIFICATE_PASSWORD` | The password chosen when exporting that `.p12`; not the Apple Account password or temporary keychain password. |
| `KEYCHAIN_PASSWORD` | An arbitrary strong, randomly generated password for the workflow's temporary keychain. It need not match any account password. |
| `NOTARYTOOL_APPLE_ID` | The Apple Account **email address** authorized to notarize for the Developer team. |
| `NOTARYTOOL_TEAM_ID` | The Apple Developer **Team ID** associated with the signing identity and notarization account. |
| `NOTARYTOOL_PASSWORD` | An Apple **app-specific password** generated for notarization; **not** the ordinary Apple Account login password. |
| `CODESIGN_APPLE_ID` | **Optional.** Not needed: the signing identity is read from the temporary keychain that holds the imported `.p12`, which must contain exactly one Developer ID Application identity whose team is `NOTARYTOOL_TEAM_ID`. If set, it pins that identity and the release fails when they differ. Value: the full identity, such as `Developer ID Application: Organization (TEAMID)`, or its SHA-1 fingerprint. **Not an email address.** |

Keep public build configuration separate under **Actions → Variables**:
`FOURD_ENABLED=true` is the intentional hosted 4D opt-in. The approved public
tool4d build and archive SHA256 are already pinned in `package.json.tool`;
`TOOL4D_URL` and `TOOL4D_SHA256` are **optional paired overrides**, not required
secrets. Supply both or neither; incomplete/invalid overrides fail.
GitHub supplies `GITHUB_TOKEN` automatically; only Bump version's source commit
and Build's publication jobs grant it `contents: write`. Do not register a
personal token for these workflows.

The implemented `scripts/sign_release.py` validates all credentials before
signing and requires the checkout to equal the resolved release SHA. It
reproduces the current unsigned ZIP from verified compilation inputs, then
signs an **isolated distribution copy** of the universal CLI and native Mach-O
Libraries with Developer ID, hardened runtime and timestamp verification.
It never edits the compiler marker or signs the original compiler outputs.
The helper signs a DMG, requires notarization JSON **Accepted**, staples and
validates that DMG, mounts the final container and repacks the dependency-manager
ZIP from its actual contents. Temporary keychain, certificate and owned mounts
are cleaned on success or failure. Windows Authenticode is not implemented.

The release stage source-tests, compiles, packages and tests the unsigned
component before signing, then unpacks the **final ZIP** and requires actual
compiled-host acceptance again. Both ZIP levels retain explicit nested
directories, executable modes, source stripping and external Libraries;
the `.4dbase` does not gain an application `Contents/` layout. The DMG is the
notarized/stapled container; bare executables and the ZIP itself are not stapled.
Signing timestamps/notarization are not bit-for-bit reproducibility promises.

Accepted release artifacts contain `REPOSITORY.zip`,
`REPOSITORY.acceptance.json`, and in signed mode `REPOSITORY.dmg` plus
`REPOSITORY-signing.json`. The acceptance report binds all asset hashes/sizes,
source revision, native manifests, compiler provenance, unsigned host and exact
final compiled-host results. Publication verifies the downloaded artifact set
again and refuses missing, modified, mixed-revision or unvalidated assets.
Download the ZIP for Dependency manager/manual `.4dbase` installation, or mount
the signed DMG for the same component payload. Preserve both evidence JSON files
with the artifacts. Native Intel/Windows 4D, installed-release downloads and
signing validation on other destinations remain separate observations.
Gatekeeper/quarantine can block unsigned downloads; no runtime trust bypass or
silent unsigned fallback is supplied.

The signing implementation and its mocked vendor-tool regressions originate from
MIT-licensed [miyako/UuidTest commit 7e0cfab](https://github.com/miyako/UuidTest/tree/7e0cfab983a582994e12c79c09aa47a205ea4bfc).
Its [actual v0.1.0 release run](https://github.com/miyako/UuidTest/actions/runs/41270374443)
executed signing, notarization, stapling and exact final ZIP host acceptance.
The [public signing proof](https://github.com/miyako/UuidTest/releases/download/v0.1.0/UuidTest-signing.json)
records `Accepted`; its original writer also verified public download hashes,
strict signatures/stapling and actual downloaded ZIP host loading. This is
evidence for that helper/revision/destination, not a claim that this uninitialized
template or every adopter was signed or validated on every native platform.

### Lifecycle checklist

Create the destination with **Use this template**, initialize its exact name and
one selected language, then replace the feature/API/docs/CLI and host contracts.
Commit the feature, notices and pinned dependencies. Set the generated
repository's **FOURD_ENABLED=true** variable; choose unsigned policy or commit
a signed version and register its six secrets. Run **CI → Run workflow** to
inspect the compiled ZIP/evidence without publication. After approval, run
**Bump version → Run workflow**, explicitly selecting the destination branch
and patch/minor/major. It validates and commits synchronized source metadata
only; merge that commit to main if needed. Separately authorize
**Build → Run workflow** on **main**, with only optional signing escalation.
Build derives the version from synchronized source at immutable dispatch
`github.sha`, preflights source/collisions/main ancestry, and builds/tests that
same full SHA through CI, acceptance and publication. It creates the tag/release
only after final asset acceptance and all required gates pass. Download
the exact-name ZIP and evidence from the accepted GitHub release. Workflow
buttons require the workflow to exist on the default branch. The uninitialized
template itself remains nonreleasable.

If Build fails, source metadata remains unchanged and no tag or release is
created before final asset acceptance. An authorized Build retry can use the
same source version if no remote collision exists; it needs no further bump
and never fabricates build success or rolls back user commits.
If publication fails *after* creating the accepted tag, it is retained:
the workflow never deletes/replaces tags, clobbers an existing release or relies
on tag-push publication.
Inspect the retained evidence and resolve that publication failure explicitly.
Main may advance during builds, but the accepted commit must still be in main's
history before a new tag is created atomically through GitHub's refs API
(including rejection of an identical-SHA collision). Downloaded assets are rechecked
against accepted hashes/sizes, revision, native manifests, signing policy and
full host contracts before any tag creation; `gh release create --verify-tag`
then publishes only the literal validated asset list.

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
Initialization copies the selected Go BSD or Rust MIT runtime notice from
`cli-starters/<language>/licenses/` into packaged `Resources/licenses/`;
packing rejects a missing baseline notice. This does **not** audit added
dependencies or all runtime exceptions. Review Rust's release
`COPYRIGHT-library.html` for applicable standard-library third-party notices,
and Microsoft static-CRT redistribution terms for Windows C++ builds.
System dylibs are not bundled by default. Recheck notices when changing
toolchains, dependencies or linked runtime code.

Conventions were verified from
[pdfdistill-pdfcpu](https://github.com/miyako/pdfdistill-pdfcpu),
[pdfdistill-qpdf](https://github.com/miyako/pdfdistill-qpdf),
[pdfdistill-lopdf](https://github.com/miyako/pdfdistill-lopdf)
(MIT, 2026 Keisuke Miyako), and
[4d-class-compiler](https://github.com/miyako/4d-class-compiler)
(MIT, 2022 Keisuke Miyako). No feature algorithms, binaries or artwork were copied.
[4d-plugin-tutorial](https://github.com/miyako/4d-plugin-tutorial) inspired the
agent-driven tutorial UX; this is a component/standalone CLI, not its native
plug-in SDK/code. That tutorial is a separate host-installed plug-in architecture,
not guidance for adding a private plug-in backend to this component.
Official references:
[dependency naming](https://developer.4d.com/docs/Project/components),
[Compile project](https://developer.4d.com/docs/commands/compile-project),
[SystemWorker](https://developer.4d.com/docs/API/SystemWorkerClass) and
[error handling](https://developer.4d.com/docs/20/Concepts/error-handling).
