Read `AGENTS.md` (canonical THINK/ASK → RUN playbook), `README.md`,
`template.json`, class documentation and relevant scripts/tests before editing.
For component adoption, also read `.github/skills/4d-cli-component/SKILL.md` if
the client did not load it; its presence does not prove invocation.
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
the exact version-commit SHA and downloaded accepted asset hashes before
creating the version tag and release. Keep exactly CI and manual main-only
Publish workflows; Publish bumps patch/minor/major and commits synchronized
metadata before building. Never initialize or publish the original template.
Unsigned local acceptance needs no license activation or signing secrets.
