# Implementing a component from this template

This is a real 4D component scaffold, not a native 4D plug-in. Its executable is a
separate process shipped in component Resources. Start with the destination
repository's exact basename, the user's source language (`go`, `rust`, `cpp`),
a unique 4D namespace, a CLI basename and the requested feature.

## Onboarding

Read `README.md`, `template.json`, this file and class documentation before editing.
Determine the destination name from the actual GitHub repository, not the local
worktree directory. Run:

```sh
python3 scripts/initialize.py --repository hello-tools --namespace AcmeHello \
  --cli hello-cli --language rust --feature "The user's requested feature"
```

The initializer validates and renames the component root/project/catalog,
namespace, CLI manifest/name, package metadata, host fixture and documentation.
It keeps only the selected starter in `cli/`, deletes the other starters, changes
the catalog UUID deterministically, and marks initialization complete. Identical
repeated initialization is a no-op; conflicting reconfiguration is rejected.
It does NOT implement the described feature: that is your next task.
Do not bypass its checks, set `initialized` manually or run it in the original
template repository. On a fresh template, unconfigured CI must not publish or
install all language toolchains. A namespace must be unique across the host's
components; syntax validation cannot discover all future host collisions.

Example user prompt:

> Implement a 4D component in this new repository that [FEATURE]. Use [Go/Rust/C++],
> namespace [UNIQUE_NAMESPACE], CLI name [NAME], and these constraints: [LIMITS,
> DEPENDENCIES, LICENSING, ERROR/PERFORMANCE REQUIREMENTS]. Initialize the template,
> replace the greeting example and its host tests with the feature, document the
> exposed API, and build/test/package the actual compiled component. Report any
> platform or 4D runtime you could not validate.

## 4D rules

The destination basename MUST equal `template.json.repository`, `package.json.name`,
`component/<name>`, `Project/<name>.4DProject`, catalog `<base name>`, the packed
`<name>.4DZ` and release asset `<name>.zip`. Namespace is INDEPENDENT:
`settings.4DSettings` is XML, `general.component_classStore_name` controls
`cs.Namespace.Greeting`. Internal code uses `cs.Greeting`, NOT the host namespace.
Do not invent an exported-class list: namespace shares component classes.
Underscore names are internal-by-convention, NOT access control. Keep deliberate
feature API in non-underscore classes; do not expose generic helpers as the primary API.

`_CLI` resolves the component's `/RESOURCES/bin` only, with no PATH fallback.
Expand virtual File/Folder paths via `platformPath` and the correct File/Folder
constructor before launching. `4D.SystemWorker` accepts a command-line Text,
not an argv Collection, and does not implicitly invoke a shell. Never introduce
`cmd /c`, `bash -c`, `eval`, or concatenate unquoted user paths/arguments.
Use the existing quote routine and test real argument round trips on BOTH OSes.
Windows target must be explicitly `Windows-x64`; don't guess CPU architecture
from a freeform processor name. Native Windows ARM64 is not provided.

Keep stdout, stderr, exitCode and system errors separate. stderr is not by itself
failure. Close stdin; check missing resources, launch failure, timeout/abnormal exit,
protocol and nonzero status. Narrow 4D error capture restores the previous local
handler and returns diagnostic details; do not install a permanent host-global
handler. Avoid Null/empty success fallbacks. Use UTF-8 explicitly. This starter
is synchronous (30s process timeout); if adding async, use CALL WORKER and keep
the worker process alive, isolate per-call state, clear queues on cancellation
and prune contexts. Never blindly write empty stdout to an output file.

Keep command tokens if editing IDE-generated code; plain command names in this
scaffold are intentional and accepted by the compiler. Do not create tables or
authentication/locale settings just to imitate a PDF reference.

## Implementation workflow and acceptance

1. Initialize. Define the feature's versioned CLI contract and error/status behavior
   before replacing `Greeting` and the selected CLI. Keep reusable execution
   code separate. Update all class docs and the host fixture together.
2. Pin dependencies/toolchains, commit lockfiles when applicable, review upstream
   licenses before copying, and put redistribution notices under
   `component/<name>/Resources/licenses/`. Keep manifest, CLI and API versions
   aligned when changing `template.json.version`.
3. Run `python3 -m unittest discover -s tests -v` and
   `python3 scripts/generate_icons.py --check`. Add exact feature tests, malformed
   inputs, Unicode/space/quote paths and stdout/stderr/exitCode assertions.
   Configured CI tests only the selected language; do not silently skip its missing tools.
4. Build native macOS Intel + Apple Silicon and Windows x64. macOS executable
   must contain both slices; preserve executable ZIP permissions and check dynamic
   dependencies. Never mix binaries from different commits or rely on tracked stale binaries.
5. Configure the documented free tool4d download URL + SHA256 and FOURD_ENABLED.
   Run source host tests, the real compiler, deterministic source-stripped packing,
   and host tests against the UNPACKED RELEASE `.4dbase`. A green Python/CLI suite
   is not evidence that a 4D host loaded the component.
6. Release only a matching `v<version>` tag. CI must fail rather than publish if
   uninitialized, misnamed, missing a binary/library, compilation failed, or the
   packaged host test failed. Report actual observed validation separately from
   untested hosted platforms, dependency-manager downloads and optional signing.

The icon convention is SVG embeds PNG, not the reverse. Edit the original
`assets/icon-source.svg` within the supported rectangle/polygon renderer, then
regenerate BOTH Resources icons. For arbitrary SVG artwork replace the renderer
with a pinned real SVG rasterizer and preserve the byte-identical PNG data URI.
Do not rename an SVG to PNG.

Signing is not a prerequisite for unsigned development builds. Do not add
certificates to source or use broad entitlements copied from references. Opt-in
signing must fail closed, require notarization Accepted, clean temporary keychains,
and test the final signed compiled package.
