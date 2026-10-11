# Changelog — ui-acceptance-recipes

## v0.1.1 — 2026-10-11 (round-2 iteration: agent loop ergonomics)

### Added
- `run --stop-on-fail`: abort remaining checks after the first failure;
  skipped check ids are listed in the report (`skipped: [...]` and
  `[SKIP] id` lines) so the report stays explainable.
- Round-2 tests: stop-on-fail skip semantics, all-pass runs everything,
  report schema keys, CLI end-to-end, default empty `skipped`.
  Test count 21 → 26 (+23.8%).

### Changed
- README: fast-fail loop added to Quickstart; trade-offs section updated.

## v0.1.0 — 2026-10-11

Initial draft: `uiar/v1` recipe schema with validation (schema/name/checks/
unique ids/argv-or-string commands/positive timeouts/optional booleans),
sequential subprocess runner with per-check timeout, output-tail capture,
optional-fails-as-warn semantics, `validate|run|list` CLI, `--json`, exit
codes 0/1/2, and three bundled stub recipes (render-smoke, a11y-basic,
interaction-regression). 21-test battery.
