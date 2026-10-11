#!/usr/bin/env python3
"""ui-acceptance-recipes: executable acceptance-check recipes for AI-built UIs.

An agent that generates UI should also *prove* it works. This tool defines a
small recipe schema (JSON) for ordered, per-check shell commands — render
smoke, accessibility, interaction regression — and a runner that executes
them, captures exit codes and durations, and emits a pass/fail report with a
CI-friendly exit code.

Schema (uiar/v1):
{
  "schema": "uiar/v1",
  "name": "my-recipe",
  "description": "optional",
  "settings": {"timeout_seconds": 30, "cwd": "."},
  "checks": [
    {"id": "unique-id", "title": "human label",
     "command": ["python", "-c", "..."],   # argv list (preferred) or string
     "timeout_seconds": 10,                 # optional override
     "optional": false}                     # optional failures -> warn
  ]
}

Exit codes: 0 all pass/warn, 1 any check failed, 2 recipe invalid/missing.
Pure standard library.
"""
from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

SCHEMA = "uiar/v1"
DEFAULT_TIMEOUT = 30.0
MAX_OUTPUT_TAIL = 800  # characters of stderr/stdout kept per check


class RecipeError(Exception):
    """Recipe is missing/invalid (exit code 2)."""


def load_recipe(path) -> dict:
    p = Path(path)
    if not p.is_file():
        raise RecipeError(f"recipe file not found: {p}")
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise RecipeError(f"recipe is not valid JSON: {exc}") from exc
    validate_recipe(data, source=str(p))
    return data


def validate_recipe(data, source: str = "<recipe>") -> None:
    if not isinstance(data, dict):
        raise RecipeError(f"{source}: recipe must be a JSON object")
    if data.get("schema") != SCHEMA:
        raise RecipeError(f"{source}: schema must be {SCHEMA!r}, got {data.get('schema')!r}")
    if not isinstance(data.get("name"), str) or not data["name"].strip():
        raise RecipeError(f"{source}: 'name' must be a non-empty string")
    checks = data.get("checks")
    if not isinstance(checks, list) or not checks:
        raise RecipeError(f"{source}: 'checks' must be a non-empty list")
    seen = set()
    for i, chk in enumerate(checks):
        where = f"{source}: checks[{i}]"
        if not isinstance(chk, dict):
            raise RecipeError(f"{where} must be an object")
        cid = chk.get("id")
        if not isinstance(cid, str) or not cid.strip():
            raise RecipeError(f"{where} missing non-empty 'id'")
        if cid in seen:
            raise RecipeError(f"{where}: duplicate check id {cid!r}")
        seen.add(cid)
        cmd = chk.get("command")
        if isinstance(cmd, str):
            if not cmd.strip():
                raise RecipeError(f"{where}: 'command' string is empty")
        elif isinstance(cmd, list):
            if not cmd or not all(isinstance(x, str) for x in cmd):
                raise RecipeError(f"{where}: 'command' list must be non-empty strings")
        else:
            raise RecipeError(f"{where}: 'command' must be an argv list or string")
        t = chk.get("timeout_seconds", DEFAULT_TIMEOUT)
        if not isinstance(t, (int, float)) or t <= 0:
            raise RecipeError(f"{where}: 'timeout_seconds' must be a positive number")
        if not isinstance(chk.get("optional", False), bool):
            raise RecipeError(f"{where}: 'optional' must be a boolean")


def _argv_of(chk: dict):
    cmd = chk["command"]
    if isinstance(cmd, str):
        # posix=False keeps Windows path backslashes intact; strip residual
        # quotes that posix=False leaves in tokens.
        tokens = shlex.split(cmd, posix=False)
        return [t[1:-1] if len(t) >= 2 and t[0] == t[-1] and t[0] in "\"'" else t
                for t in tokens]
    return list(cmd)


def run_recipe(recipe: dict, cwd: str = None, stop_on_fail: bool = False) -> dict:
    """Execute checks sequentially. Never raises for check failures.

    stop_on_fail: abort remaining checks after the first failure (report
    includes skipped ids).
    """
    settings = recipe.get("settings", {})
    base_timeout = settings.get("timeout_seconds", DEFAULT_TIMEOUT)
    base_cwd = cwd or settings.get("cwd") or "."
    results = []
    skipped = []
    for chk in recipe["checks"]:
        if stop_on_fail and any(r["status"] == "fail" for r in results):
            skipped.append(chk["id"])
            continue
        entry = {"id": chk["id"], "title": chk.get("title", chk["id"]),
                 "status": "pass", "exit_code": 0, "duration_ms": 0,
                 "output_tail": ""}
        argv = _argv_of(chk)
        timeout = float(chk.get("timeout_seconds", base_timeout))
        t0 = time.perf_counter()
        try:
            proc = subprocess.run(argv, cwd=base_cwd, capture_output=True,
                                  text=True, timeout=timeout)
            entry["exit_code"] = proc.returncode
            tail = (proc.stderr or proc.stdout or "").strip()
            entry["output_tail"] = tail[-MAX_OUTPUT_TAIL:]
            if proc.returncode != 0:
                entry["status"] = "warn" if chk.get("optional") else "fail"
        except subprocess.TimeoutExpired:
            entry["exit_code"] = None
            entry["status"] = "fail" if not chk.get("optional") else "warn"
            entry["output_tail"] = f"timed out after {timeout}s"
        except (OSError, ValueError) as exc:
            entry["exit_code"] = None
            entry["status"] = "fail" if not chk.get("optional") else "warn"
            entry["output_tail"] = f"could not execute: {exc}"
        entry["duration_ms"] = round((time.perf_counter() - t0) * 1000, 1)
        results.append(entry)
    failed = [r for r in results if r["status"] == "fail"]
    status = "fail" if failed else "pass"
    return {"recipe": recipe["name"], "schema": SCHEMA, "status": status,
            "results": results, "skipped": skipped,
            "summary": {"total": len(results),
                        "pass": sum(1 for r in results if r["status"] == "pass"),
                        "warn": sum(1 for r in results if r["status"] == "warn"),
                        "fail": len(failed)}}


def render_report(report: dict) -> str:
    lines = [f"recipe: {report['recipe']} -> {report['status'].upper()}"]
    for r in report["results"]:
        mark = {"pass": "PASS", "warn": "WARN", "fail": "FAIL"}[r["status"]]
        lines.append(f"  [{mark}] {r['id']} ({r['duration_ms']} ms) {r['title']}")
        if r["output_tail"]:
            lines.append(f"        {r['output_tail'][:200]}")
    for sid in report.get("skipped", []):
        lines.append(f"  [SKIP] {sid} (not run: --stop-on-fail)")
    s = report["summary"]
    lines.append(f"summary: {s['pass']} pass / {s['warn']} warn / {s['fail']} fail "
                 f"of {s['total']}")
    return "\n".join(lines)


def bundled_recipes_dir() -> Path:
    return Path(__file__).parent / "recipes"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(
        prog="ui-acceptance-recipes",
        description="Run executable acceptance-check recipes for AI-generated UIs.")
    sub = ap.add_subparsers(dest="cmd", required=True)

    ap_list = sub.add_parser("list", help="list bundled recipes")
    ap_val = sub.add_parser("validate", help="validate a recipe file")
    ap_val.add_argument("file")
    ap_run = sub.add_parser("run", help="execute a recipe")
    ap_run.add_argument("file")
    ap_run.add_argument("--cwd", default=None, help="working directory for checks")
    ap_run.add_argument("--stop-on-fail", action="store_true",
                        help="abort remaining checks after the first failure")
    ap_run.add_argument("--json", action="store_true")

    args = ap.parse_args(argv)

    if args.cmd == "list":
        rdir = bundled_recipes_dir()
        for p in sorted(rdir.glob("*.json")):
            try:
                r = json.loads(p.read_text(encoding="utf-8"))
                print(f"{p.name}: {r.get('description', r.get('name', '?'))}")
            except (json.JSONDecodeError, OSError) as exc:
                print(f"{p.name}: UNREADABLE ({exc})", file=sys.stderr)
                return 2
        return 0

    try:
        recipe = load_recipe(args.file)
    except RecipeError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.cmd == "validate":
        print(f"recipe valid: {recipe['name']} ({len(recipe['checks'])} checks)")
        return 0

    report = run_recipe(recipe, cwd=args.cwd, stop_on_fail=args.stop_on_fail)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_report(report))
    return 0 if report["status"] == "pass" else 1


if __name__ == "__main__":
    sys.exit(main())
