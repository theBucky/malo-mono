## engineering

- prefer the simplest end-to-end solution for current requirements. extract shared logic only for real reuse or a shared invariant.
- preserve runtime behavior during formatting, lint, typing, and test-structure changes.

## boundaries

- treat `refs/` as read-only reference material; do not edit or import from that directory.
- remove obsolete paths directly; do not add backward-compatibility layers, fallbacks, or migrations.
- keep public pull requests, commits, generated files, and documentation free of private names, internal context, customer-derived data, and ai attribution.
