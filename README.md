# ui-acceptance-recipes

Executable acceptance-check recipes for AI-generated UIs. An agent that
builds an interface should prove it works with a checklist it can actually
run — render smoke, accessibility baseline, interaction regression — not
claim it in prose. This repo is that checklist format plus a runner.

**Confidence: High (>=85%)** that structured executable checklists reduce
"agent says done, UI is broken" loops; **Medium (60-79%)** that the three
bundled recipes cover the right baseline without project-specific checks.

## Problem

UI-generating agents are judged by a demo they did not objectively verify.
The overlooked angle of component-library work aimed at AI developers is the
`ai_recipes` idea: the acceptance step should be *recipes* — ordered,
executable commands with pass/fail semantics — that any agent can run after
generating UI. Prose checklists ("make sure it's accessible") are not
verifiable; `npx axe http://localhost:3000 --exit` is. Nobody standardized
the envelope around such commands: ordering, timeouts, optional checks,
one report, one exit code. That envelope is this tool.

## How it works

- A **recipe** is JSON (`uiar/v1`): name, settings (default timeout, cwd),
  and an ordered list of checks. Each check has a unique id, a title, a
  command (argv list preferred; string supported), an optional per-check
  timeout, and `optional: true` to downgrade failures to warnings.
- The **runner** executes checks sequentially in a subprocess, captures
  exit code + output tail + duration, and prints a report.
  Exit codes: `0` all pass/warn, `1` any failure, `2` recipe invalid.
- Three **bundled recipes** ship as stubs showing where real tools plug in:
  `render-smoke`, `a11y-basic` (axe-cli/pa11y), `interaction-regression`
  (playwright/puppeteer). Replace stub commands with your project's.

## Quickstart (~3 min)

```bash
# 1. See the bundled recipes (~2 s)
python ui_acceptance_recipes.py list

# 2. Validate and run one (~5 s; stubs are instant)
python ui_acceptance_recipes.py validate recipes/render-smoke.json
python ui_acceptance_recipes.py run recipes/render-smoke.json

# 3. Wire your own: copy a recipe, point commands at your real tools, then
python ui_acceptance_recipes.py run my-ui.json --cwd ./my-app --json

# 4. Fast-fail loop for agents (~2 s): stop at the first red check
python ui_acceptance_recipes.py run my-ui.json --stop-on-fail
```

## Why not X

| Alternative | Why not here |
|---|---|
| One big pytest/e2e suite | Right for products; too heavy for an agent's *first* self-check loop — needs fixtures, awaits, browser deps. A recipe is the 10-command subset an agent can run in seconds. |
| Playwright test runner alone | Excellent interaction coverage, zero structure for "which checks are mandatory vs optional" or a universal envelope across tools; recipes compose it as a check instead of replacing it. |
| CLAUDE.md prose checklists ("run axe, check contrast") | Not executable, not ordered, no exit codes; exactly the failure mode this repo removes. |
| CI pipeline YAML | Runs in CI, not in the agent's local loop; recipes are the artifact an agent runs *before* asking CI to. |

## Minimal Fallback (PLAN B)

No Python? The schema is plain JSON and checks are plain commands:

```bash
# Run the same checks with any shell: every command must exit 0
python -c "import json;[print(c['id']) for c in json.load(open('recipes/render-smoke.json'))['checks']]"
# or hand-execute: the recipe file is the source of truth either way
```

You lose timeout enforcement, optional/warn semantics, and the summary
report — but the recipe file remains a portable, reviewable checklist.

## Design Trade-offs

Priority: **agent-ergonomics > safety > completeness**.

- Checks are shell-out commands, not a plugin API: maximal composability
  with existing tools, at the cost of no sandboxing — recipes are trusted
  artifacts, reviewed like code (same trust level as CI config).
- Sequential execution with opt-in `--stop-on-fail`: simpler logs and
  deterministic ordering; unskipped-by-default ordering means a red check
  never hides a later one unless you ask.
- Optional checks default to off (`optional: false`): a skipped a11y scan
  must be an explicit decision, not a default (safety > convenience).

## Limits & Second-order Effects

- **Recipe theater**: once agents pass recipes, teams may stop human-reviewing
  UI entirely; recipes only cover what they encode. Green here does not mean
  usable — keep at least one human look per release.
- Stub recipes left unedited could give false confidence ("recipe ran green").
  Bundled files are marked STUB in every title; grep for `STUB` in review.
- Command-based checks inherit the shell security posture of the project;
  never point a recipe at untrusted recipe files.

## FAQ

**Q: When NOT to use this tool?**
A: When you already have a mature e2e suite and an agent loop that runs it —
you would be adding a second runner for no gain. Also skip it for backend-only
changes; this is UI-acceptance-shaped, not a general task runner.

**Q: Windows support?**
A: Yes — argv-list commands avoid shell quoting entirely; string commands
are split Windows-safely.

**Q: Can checks run in parallel?**
A: Not in v1, deliberately (deterministic output, simpler reports).

**Q: How fast?**
A: Self-test measured: 26 tests incl. full bundled-recipe runs in ~29 s on
Windows (subprocess startup dominates; the runner overhead itself is
milliseconds per check) (`python self_test.py -v` reproduces).

## [Core Assumptions]

1. "Acceptance" can be meaningfully approximated by ordered shell commands
   with exit codes; things that need human judgment are out of scope.
2. Agents can edit JSON recipe files as reliably as they write code.
3. Recipe files are trusted inputs (like CI configs) — the runner executes
   their commands verbatim by design.
4. Project toolchains (axe, playwright) already exist or will be installed
   separately; this envelope never bundles them (as of 2026-10-11).

---
Contact: hcac4735@agent.qq.com · License: MIT · Bundled stubs as of 2026-10-11.
