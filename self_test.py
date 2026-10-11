#!/usr/bin/env python3
"""self_test battery for ui-acceptance-recipes (functional / errors / edges).

Run:  python self_test.py -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import ui_acceptance_recipes as uiar  # noqa: E402

HERE = Path(__file__).parent
PY = sys.executable or "python"

OK = [PY, "-c", "import sys; sys.exit(0)"]
FAIL = [PY, "-c", "import sys; print('boom'); sys.exit(3)"]
SLEEP = [PY, "-c", "import time; time.sleep(5)"]


def recipe(checks, name="t", schema="uiar/v1", settings=None):
    r = {"schema": schema, "name": name, "checks": checks}
    if settings is not None:
        r["settings"] = settings
    return r


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = Path(self.tmp.name)
        self.addCleanup(self.tmp.cleanup)

    def write(self, data, name="r.json") -> Path:
        p = self.d / name
        p.write_text(json.dumps(data) if not isinstance(data, str) else data,
                     encoding="utf-8")
        return p


# ------------------------------------------------------------- functional

class Functional(TempCase):
    def test_validate_ok(self):
        uiar.validate_recipe(recipe([{"id": "a", "command": OK}]))

    def test_run_all_pass(self):
        r = recipe([{"id": "a", "command": OK}, {"id": "b", "command": OK}])
        rep = uiar.run_recipe(r)
        self.assertEqual(rep["status"], "pass")
        self.assertEqual(rep["summary"], {"total": 2, "pass": 2, "warn": 0, "fail": 0})

    def test_run_detects_failure(self):
        rep = uiar.run_recipe(recipe([{"id": "a", "command": FAIL}]))
        self.assertEqual(rep["status"], "fail")
        self.assertIn("boom", rep["results"][0]["output_tail"])

    def test_optional_failure_is_warn_and_passes(self):
        rep = uiar.run_recipe(recipe([{"id": "opt", "command": FAIL, "optional": True}]))
        self.assertEqual(rep["status"], "pass")
        self.assertEqual(rep["results"][0]["status"], "warn")

    def test_string_command_supported(self):
        rep = uiar.run_recipe(recipe([{"id": "s", "command": f'{PY} -c "import sys; sys.exit(0)"'}]))
        self.assertEqual(rep["status"], "pass")

    def test_bundled_recipes_valid_and_green(self):
        rdir = uiar.bundled_recipes_dir()
        files = sorted(rdir.glob("*.json"))
        self.assertGreaterEqual(len(files), 3)
        for p in files:
            r = uiar.load_recipe(p)
            rep = uiar.run_recipe(r, cwd=str(rdir))
            self.assertEqual(rep["status"], "pass", msg=f"{p.name}: {rep}")

    def test_cli_run_and_json(self):
        p = self.write(recipe([{"id": "a", "command": OK}]))
        r = subprocess.run([PY, str(HERE / "ui_acceptance_recipes.py"), "run", str(p), "--json"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertEqual(json.loads(r.stdout)["status"], "pass")
        p2 = self.write(recipe([{"id": "a", "command": FAIL}]), "f.json")
        r2 = subprocess.run([PY, str(HERE / "ui_acceptance_recipes.py"), "run", str(p2)],
                            capture_output=True, text=True)
        self.assertEqual(r2.returncode, 1)
        self.assertIn("[FAIL] a", r2.stdout)

    def test_cli_validate(self):
        p = self.write(recipe([{"id": "a", "command": OK}]))
        r = subprocess.run([PY, str(HERE / "ui_acceptance_recipes.py"), "validate", str(p)],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertIn("recipe valid", r.stdout)


# ------------------------------------------------------------ error paths

class ErrorPaths(TempCase):
    def test_missing_file(self):
        with self.assertRaises(uiar.RecipeError):
            uiar.load_recipe(self.d / "nope.json")

    def test_malformed_json(self):
        p = self.d / "bad.json"
        p.write_text("{oops", encoding="utf-8")
        with self.assertRaises(uiar.RecipeError):
            uiar.load_recipe(p)

    def test_wrong_schema_field(self):
        with self.assertRaises(uiar.RecipeError):
            uiar.validate_recipe(recipe([{"id": "a", "command": OK}], schema="uiar/v9"))

    def test_missing_checks(self):
        with self.assertRaises(uiar.RecipeError):
            uiar.validate_recipe({"schema": "uiar/v1", "name": "x", "checks": []})

    def test_duplicate_check_ids(self):
        dup = [{"id": "a", "command": OK}, {"id": "a", "command": OK}]
        with self.assertRaises(uiar.RecipeError):
            uiar.validate_recipe(recipe(dup))

    def test_bad_command_type(self):
        with self.assertRaises(uiar.RecipeError):
            uiar.validate_recipe(recipe([{"id": "a", "command": 42}]))

    def test_nonexistent_binary_reports_cleanly(self):
        rep = uiar.run_recipe(recipe([{"id": "x", "command": ["definitely-not-a-cmd-xyz"]}],
                                     settings={"timeout_seconds": 2}))
        self.assertEqual(rep["status"], "fail")
        self.assertIn("could not execute", rep["results"][0]["output_tail"])


# ----------------------------------------------------------- extreme edges

class ExtremeEdges(TempCase):
    def test_timeout_is_enforced(self):
        rep = uiar.run_recipe(recipe(
            [{"id": "slow", "command": SLEEP, "timeout_seconds": 0.5}]))
        self.assertEqual(rep["status"], "fail")
        self.assertIn("timed out", rep["results"][0]["output_tail"])
        self.assertLess(rep["results"][0]["duration_ms"], 5000)

    def test_huge_output_truncated_to_tail(self):
        cmd = [PY, "-c", "print('x' * 200)"]
        rep = uiar.run_recipe(recipe([{"id": "loud", "command": cmd}]))
        self.assertLessEqual(len(rep["results"][0]["output_tail"]), uiar.MAX_OUTPUT_TAIL)

    def test_unicode_recipe(self):
        rep = uiar.run_recipe(recipe([{"id": "ünïcode-✓", "title": "中文标题",
                                        "command": OK}]))
        self.assertEqual(rep["status"], "pass")

    def test_many_checks(self):
        checks = [{"id": f"c{i}", "command": OK} for i in range(50)]
        rep = uiar.run_recipe(recipe(checks, settings={"timeout_seconds": 10}))
        self.assertEqual(rep["summary"]["pass"], 50)

    def test_cwd_is_honored(self):
        marker = self.d / "marker.txt"
        marker.write_text("hi", encoding="utf-8")
        code = "import pathlib,sys; sys.exit(0 if pathlib.Path('marker.txt').exists() else 1)"
        rep = uiar.run_recipe(recipe([{"id": "cwd", "command": [PY, "-c", code]}]),
                              cwd=str(self.d))
        self.assertEqual(rep["status"], "pass")

    def test_cli_list_reports_bundled(self):
        r = subprocess.run([PY, str(HERE / "ui_acceptance_recipes.py"), "list"],
                           capture_output=True, text=True)
        self.assertEqual(r.returncode, 0)
        self.assertGreaterEqual(r.stdout.count(".json"), 3)


# ------------------------------------------------------- round-2 additions

class RoundTwo(TempCase):
    def test_stop_on_fail_skips_rest(self):
        r = recipe([{"id": "first", "command": FAIL},
                    {"id": "second", "command": OK},
                    {"id": "third", "command": OK}])
        rep = uiar.run_recipe(r, stop_on_fail=True)
        self.assertEqual(rep["status"], "fail")
        self.assertEqual([x["id"] for x in rep["results"]], ["first"])
        self.assertEqual(rep["skipped"], ["second", "third"])

    def test_stop_on_fail_all_pass_runs_everything(self):
        r = recipe([{"id": "a", "command": OK}, {"id": "b", "command": OK}])
        rep = uiar.run_recipe(r, stop_on_fail=True)
        self.assertEqual(rep["status"], "pass")
        self.assertEqual(rep["skipped"], [])
        self.assertEqual(rep["summary"]["total"], 2)

    def test_report_contains_duration_and_skipped_keys(self):
        rep = uiar.run_recipe(recipe([{"id": "a", "command": OK}]))
        self.assertIn("duration_ms", rep["results"][0])
        self.assertIn("skipped", rep)

    def test_cli_stop_on_fail(self):
        p = self.write(recipe([{"id": "f", "command": FAIL},
                               {"id": "never", "command": SLEEP}],
                              settings={"timeout_seconds": 3}))
        r = subprocess.run([PY, str(HERE / "ui_acceptance_recipes.py"), "run",
                            str(p), "--stop-on-fail"], capture_output=True, text=True)
        self.assertEqual(r.returncode, 1)
        self.assertIn("[FAIL] f", r.stdout)
        self.assertIn("[SKIP] never", r.stdout)  # skipped, not executed

    def test_default_report_has_empty_skipped(self):
        rep = uiar.run_recipe(recipe([{"id": "a", "command": OK}]))
        self.assertEqual(rep["skipped"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
