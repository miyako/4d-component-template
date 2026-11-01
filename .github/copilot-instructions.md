Read and follow `AGENTS.md` and `README.md` before editing this repository.
If `template.json.initialized` is false, initialize the exact destination
repository name, user-selected Go/Rust/C++ language, unique namespace, CLI name
and feature using `scripts/initialize.py` before implementing the feature.
Do not ship all three source implementations or publish the unconfigured template.
Preserve 4D repository/component/project/catalog/package/release-name equality.
Keep the generic execution layer separate from feature classes and update class
documentation and real host tests with every API change.
Use actual 4D APIs and tool4d; do not invent setup actions, architecture properties,
argv-array SystemWorker overloads or success fallbacks. Follow the validation,
licensing, signing and compiled-package acceptance requirements in `AGENTS.md`.
