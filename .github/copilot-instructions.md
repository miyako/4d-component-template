Read `AGENTS.md` (canonical THINK/ASK → RUN playbook), `README.md`,
`template.json`, class documentation and relevant scripts/tests before editing.
For component adoption, also read `.github/skills/4d-cli-component/SKILL.md` if
the client did not load it; its presence does not prove invocation.
Choose either this CLI-backed component architecture or a separate native 4D
plug-in installed in the host. Never generate or propose a component-over-plug-in
hybrid as a self-contained component solution. A component cannot privately
load/deploy a plug-in; component packaging cannot hide, eliminate or satisfy
host plug-in installation. If native 4D SDK integration is required, choose the
separate plug-in architecture and document the host dependency explicitly.
This is a deployment boundary, not a blanket claim about host code calling
commands from an installed plug-in.
Never initialize the original `miyako/4d-component-template` repository.
In an uninitialized destination, use `scripts/initialize.py` with the exact
case-sensitive GitHub basename, user-selected Go/Rust/C++ language, independent
unique namespace, CLI basename and feature description. Initialization and
`rename_feature.py` do not implement the feature: replace its API/CLI/docs/tests.
Keep repository/component/project/catalog/package/release names equal; retain
only the selected language and keep generic execution separate from feature code.
Use real 4D APIs, scalar argument guards and strict NUL Position comparison;
never invent SystemWorker argv overloads, setup actions or success fallbacks.
Require same-revision binaries, actual source host tests, real compilation and
host tests against the unpacked source-stripped compiled ZIP. Report `not_run`
separately from `passed`; partial local acceptance is NOT release ready.
Follow AGENTS.md for fixed free tool4d, licensing, packaging and optional signing.
Version signing policy defaults to unsigned; signed opt-in uses the implemented
isolated signing/notarized-DMG path and must retest the exact final ZIP.
Manual CI retains compiled ZIP/evidence without publication; releases verify
the immutable dispatch `github.sha` and downloaded accepted asset hashes before
creating the version tag and release. Keep CI plus two manual release-facing
actions: **Bump version** (`bump-version.yml`) validates current version surfaces
and commits only synchronized source metadata for patch/minor/major to the
explicitly selected dispatch branch; no tags/builds/releases/workflow dispatch.
`release_source.py bump` requires clean checkout at immutable dispatch SHA and
selected branch remote HEAD exactly equal to it (fails if moved); it bumps
max(current source, stable X.Y.Z/legacy v history), never reuses old candidates,
stages bounded surfaces and non-force pushes only that branch.
**Build** (`build.yml`) remains main-only, accepts only optional
`require_apple_signing` (no version/tag/bump input), derives stable `X.Y.Z` from
synchronized source metadata at that exact SHA, preflights clean/exact source,
collisions and main ancestry before expensive CI. Nonmutating preflight requires
main dispatch/HEAD exactly equal to `github.sha`, validates all version surfaces
with `bump_release.plan` at that same version and requires source version to
exceed stable published tag history. Main may advance, but Build never switches
from dispatch SHA to newer main HEAD. It passes the same full SHA
through reusable CI, acceptance and final publication. Preserve all package,
compiler, runtime, provenance and signing gates; tag/release only after final
asset acceptance, never clobber or tag-push publication.
Never initialize or publish the original template.
Component release tags must equal the prefix-free SemVer version (`0.1.0`,
never `v0.1.0`); this is not a plug-in tag rule.
Legacy prefixed tags are read-only migration baselines.
Follow4D host-aligned LTS/R tags are a distinct convention, not implied by
ordinary component SemVer; see AGENTS.md and its official reference.
Unsigned local acceptance needs no license activation or signing secrets.
