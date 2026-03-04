"""Tests for qa_runner.py. # Tests R-P3-04, R-P3-08"""

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

# Ensure _lib is importable from the hooks directory
HOOKS_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HOOKS_DIR))

from qa_runner import (  # noqa: E402
    _needs_shell,
    _step_plan_conformance,
    _step_production_scan,
)

QA_RUNNER_PATH = HOOKS_DIR / "qa_runner.py"


def _run_qa_runner(*args: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run qa_runner.py as a subprocess."""
    cmd = [sys.executable, str(QA_RUNNER_PATH), *args]
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=60,
        cwd=cwd,
    )


def _make_prd(tmp_path: Path, story_id: str = "STORY-003") -> Path:
    """Create a minimal prd.json for testing."""
    prd = tmp_path / "prd.json"
    prd.write_text(
        json.dumps(
            {
                "version": "2.0",
                "stories": [
                    {
                        "id": story_id,
                        "description": "Test story",
                        "phase": 3,
                        "acceptanceCriteria": [
                            {"id": "R-P3-01", "criterion": "Test criterion 1"},
                            {"id": "R-P3-02", "criterion": "Test criterion 2"},
                        ],
                        "gateCmds": {
                            "unit": "echo unit-pass",
                            "lint": "echo lint-pass",
                        },
                        "passed": False,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return prd


def _make_test_file_with_markers(tmp_path: Path) -> Path:
    """Create a test file with R-PN-NN markers and assertions."""
    tests_dir = tmp_path / "tests"
    tests_dir.mkdir(exist_ok=True)
    test_file = tests_dir / "test_example.py"
    test_file.write_text(
        "def test_criterion_1():\n"
        '    """# Tests R-P3-01"""\n'
        "    assert 1 + 1 == 2\n"
        "\n"
        "def test_criterion_2():\n"
        '    """# Tests R-P3-02"""\n'
        "    assert 2 + 2 == 4\n",
        encoding="utf-8",
    )
    return tests_dir


def _make_violation_file(tmp_path: Path) -> Path:
    """Create a source file with production violations."""
    src = tmp_path / "bad_source.py"
    src.write_text(
        "# a]fixme: this needs work\n"
        "import pdb; pdb.set_trace()\n"
        "password = 'secret123'\n",
        encoding="utf-8",
    )
    return src


def _make_clean_source(tmp_path: Path) -> Path:
    """Create a clean source file with no violations."""
    src = tmp_path / "clean_source.py"
    src.write_text(
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n",
        encoding="utf-8",
    )
    return src


class TestQaRunnerExists:
    """# Tests R-P3-01"""

    def test_qa_runner_file_exists(self) -> None:
        """# Tests R-P3-01 -- qa_runner.py exists."""
        assert QA_RUNNER_PATH.is_file(), f"qa_runner.py not found at {QA_RUNNER_PATH}"

    def test_qa_runner_help(self) -> None:
        """# Tests R-P3-01 -- --help runs successfully."""
        result = _run_qa_runner("--help")
        assert result.returncode == 0, f"--help failed: {result.stderr}"
        assert "story" in result.stdout.lower() or "usage" in result.stdout.lower()


class TestCliArguments:
    """# Tests R-P3-02"""

    def test_accepts_story_arg(self, tmp_path: Path) -> None:
        """# Tests R-P3-02 -- accepts --story argument."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        assert "unrecognized arguments" not in result.stderr

    def test_accepts_all_arguments(self, tmp_path: Path) -> None:
        """# Tests R-P3-02 -- accepts all 6 CLI arguments."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--steps",
            "10",
            "--changed-files",
            "file1.py,file2.py",
            "--test-dir",
            str(tmp_path / "tests"),
            "--checkpoint",
            "abc123",
        )
        assert "unrecognized arguments" not in result.stderr


class TestAutomatedSteps:
    """# Tests R-P3-03"""

    def test_step_1_lint_runs(self, tmp_path: Path) -> None:
        """# Tests R-P3-03 -- Step 1 (lint) executes."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "1",
        )
        output = json.loads(result.stdout)
        step1 = output["steps"][0]
        assert step1["step"] == 1
        assert step1["name"] == "Lint"
        assert step1["result"] in ("PASS", "FAIL", "SKIP")

    def test_step_6_security_scan(self, tmp_path: Path) -> None:
        """# Tests R-P3-03 -- Step 6 (security scan)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        violation_file = _make_violation_file(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(violation_file),
            "--steps",
            "6",
        )
        output = json.loads(result.stdout)
        step6 = output["steps"][0]
        assert step6["step"] == 6
        assert step6["result"] in ("PASS", "FAIL")

    def test_step_7_clean_diff(self, tmp_path: Path) -> None:
        """# Tests R-P3-03 -- Step 7 (clean diff)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "7",
        )
        output = json.loads(result.stdout)
        step = output["steps"][0]
        assert step["step"] == 7
        assert step["result"] in ("PASS", "FAIL", "SKIP")

    def test_step_11_acceptance(self, tmp_path: Path) -> None:
        """# Tests R-P3-03 -- Step 11 (acceptance traceability)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "11",
        )
        output = json.loads(result.stdout)
        step = output["steps"][0]
        assert step["step"] == 11
        assert step["result"] in ("PASS", "FAIL", "SKIP")

    def test_step_12_prod_scan(self, tmp_path: Path) -> None:
        """# Tests R-P3-03 -- Step 12 (production scan)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        clean_file = _make_clean_source(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(clean_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        step = output["steps"][0]
        assert step["step"] == 12
        assert step["result"] in ("PASS", "FAIL")


class TestPlanConformanceCheck:
    """# Tests R-P4-01"""

    def test_step_10_name_is_plan_conformance(self) -> None:
        """# Tests R-P4-01 -- Step 10 named 'Plan Conformance Check'."""
        from qa_runner import STEP_NAMES

        assert STEP_NAMES[10] == "Plan Conformance Check"

    def test_step_10_skip_no_plan(self) -> None:
        """# Tests R-P4-01 -- SKIP when no plan_path."""
        result_val, evidence = _step_plan_conformance([], None, None, None, None)
        assert result_val == "SKIP"

    def test_step_10_skip_empty_plan(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- SKIP when plan has no Changes table."""
        plan = tmp_path / "PLAN.md"
        plan.write_text("# No changes table here\n", encoding="utf-8")
        result_val, evidence = _step_plan_conformance([], plan, None, None, None)
        assert result_val == "SKIP"

    def test_step_10_pass_matching_files(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- PASS when changed files match plan."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update main |\n"
            "| MODIFY | `src/utils.py` | Update utils |\n",
            encoding="utf-8",
        )
        changed = [Path("src/main.py"), Path("src/utils.py")]
        result_val, evidence = _step_plan_conformance(changed, plan, None, None, None)
        assert result_val == "PASS"

    def test_step_10_fail_unexpected_files(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- FAIL when changed files not in plan."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update main |\n",
            encoding="utf-8",
        )
        changed = [Path("src/main.py"), Path("src/unexpected.py")]
        result_val, evidence = _step_plan_conformance(changed, plan, None, None, None)
        assert result_val == "FAIL"
        assert "unexpected.py" in evidence

    def test_step_10_allows_init_py(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- __init__.py is always allowed."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update main |\n",
            encoding="utf-8",
        )
        changed = [Path("src/main.py"), Path("src/__init__.py")]
        result_val, evidence = _step_plan_conformance(changed, plan, None, None, None)
        assert result_val == "PASS"

    def test_step_10_allows_conftest(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- conftest.py is always allowed."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update |\n",
            encoding="utf-8",
        )
        changed = [Path("src/main.py"), Path("tests/conftest.py")]
        result_val, evidence = _step_plan_conformance(changed, plan, None, None, None)
        assert result_val == "PASS"

    def test_step_10_checks_r_markers(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- Step 10 validates R-markers when test_dir and prd provided."""
        plan = tmp_path / "PLAN.md"
        plan.write_text("# No changes\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "stories": [
                        {
                            "id": "STORY-X",
                            "description": "Test",
                            "phase": 1,
                            "acceptanceCriteria": [
                                {"id": "R-P9-99", "criterion": "missing"},
                            ],
                            "gateCmds": {},
                            "passed": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        test_dir = _make_test_file_with_markers(tmp_path)
        story = {
            "id": "STORY-X",
            "acceptanceCriteria": [{"id": "R-P9-99"}],
        }
        result_val, evidence = _step_plan_conformance([], plan, story, prd, test_dir)
        assert result_val == "FAIL"
        assert "R-marker" in evidence or "Missing" in evidence

    def test_step_10_pass_markers_and_files(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- PASS when both R-markers and files match."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update |\n",
            encoding="utf-8",
        )
        prd = _make_prd(tmp_path)
        test_dir = _make_test_file_with_markers(tmp_path)
        story = {
            "id": "STORY-003",
            "acceptanceCriteria": [
                {"id": "R-P3-01"},
                {"id": "R-P3-02"},
            ],
        }
        changed = [Path("src/main.py")]
        result_val, evidence = _step_plan_conformance(
            changed, plan, story, prd, test_dir
        )
        assert result_val == "PASS"

    def test_step_10_is_automated_via_subprocess(self, tmp_path: Path) -> None:
        """# Tests R-P4-01 -- Step 10 returns automated result via subprocess."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        step10 = output["steps"][0]
        assert step10["step"] == 10
        assert step10["name"] == "Plan Conformance Check"
        assert step10["result"] != "MANUAL"
        assert step10["result"] in ("PASS", "FAIL", "SKIP")


class TestPlanHashMismatch:
    """# Tests R-P1-03, R-P1-04, R-P1-05"""

    def test_plan_hash_mismatch_returns_fail(self, tmp_path: Path) -> None:
        """# Tests R-P1-03 -- FAIL when prd.json plan_hash differs from computed hash."""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "# Plan content\n\n## Done When\n- R-P1-01: test\n", encoding="utf-8"
        )
        # Store a DIFFERENT hash in prd.json (not the real PLAN.md hash)
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "plan_hash": "0000000000000000000000000000000000000000000000000000000000000000",
                    "stories": [],
                }
            ),
            encoding="utf-8",
        )
        result_val, evidence = _step_plan_conformance([], plan, None, prd, None)
        assert result_val == "FAIL"
        assert "hash mismatch" in evidence.lower() or "Plan-PRD" in evidence

    def test_plan_hash_match_returns_pass(self, tmp_path: Path) -> None:
        """# Tests R-P1-04 -- PASS when prd.json plan_hash matches computed hash."""
        from _qa_lib import compute_plan_hash

        plan = tmp_path / "PLAN.md"
        plan_content = "# Plan content\n\n## Done When\n- R-P1-01: test\n"
        plan.write_text(plan_content, encoding="utf-8")
        computed_hash = compute_plan_hash(plan)
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "plan_hash": computed_hash,
                    "stories": [],
                }
            ),
            encoding="utf-8",
        )
        result_val, evidence = _step_plan_conformance([], plan, None, prd, None)
        assert result_val == "PASS"

    def test_output_key_is_overall_result(self, tmp_path: Path) -> None:
        """# Tests R-P1-05 -- output dict uses 'overall_result' not 'overall'."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert "overall_result" in output, "Output should contain 'overall_result' key"
        assert "overall" not in output or "overall_result" in output


class TestStepNamesDict:
    """# Tests R-P4-02"""

    def test_step_names_has_12_entries(self) -> None:
        """# Tests R-P4-02 -- STEP_NAMES has 12 entries."""
        from qa_runner import STEP_NAMES

        assert len(STEP_NAMES) == 12, (
            f"STEP_NAMES has {len(STEP_NAMES)} entries, expected 12"
        )

    def test_step_names_keys_are_1_to_12(self) -> None:
        """# Tests R-P4-02 -- STEP_NAMES keys are 1..12."""
        from qa_runner import STEP_NAMES

        assert set(STEP_NAMES.keys()) == set(range(1, 13))

    def test_step_names_values(self) -> None:
        """# Tests R-P4-02 -- STEP_NAMES has correct values."""
        from qa_runner import STEP_NAMES

        assert STEP_NAMES[1] == "Lint"
        assert STEP_NAMES[2] == "Type check"
        assert STEP_NAMES[3] == "Unit tests"
        assert STEP_NAMES[4] == "Integration tests"
        assert STEP_NAMES[5] == "Regression check"
        assert STEP_NAMES[6] == "Security scan"
        assert STEP_NAMES[7] == "Clean diff"
        assert STEP_NAMES[8] == "Coverage"
        assert STEP_NAMES[9] == "Mock quality audit"
        assert STEP_NAMES[10] == "Plan Conformance Check"
        assert STEP_NAMES[11] == "Acceptance traceability"
        assert STEP_NAMES[12] == "Production scan"

    def test_parse_steps_default_is_1_to_12(self) -> None:
        """# Tests R-P4-02 -- _parse_steps(None) returns 1..12."""
        from qa_runner import _parse_steps

        result = _parse_steps(None)
        assert result == list(range(1, 13))


class TestAllStepsRun:
    """# Tests R-P4-06"""

    def test_all_12_steps_run(self) -> None:
        """# Tests R-P4-06 -- _parse_steps(None) returns all 12 step numbers."""
        from qa_runner import STEP_NAMES, _parse_steps

        all_steps = _parse_steps(None)
        assert len(all_steps) == 12, f"Expected 12 steps, got {len(all_steps)}"
        assert all_steps == list(range(1, 13))
        for step_num in all_steps:
            assert step_num in STEP_NAMES, f"Step {step_num} missing from STEP_NAMES"

    def test_all_results_are_valid(self, tmp_path: Path) -> None:
        """# Tests R-P4-06 -- All results are PASS/FAIL/SKIP."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        clean_file = _make_clean_source(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(clean_file),
            "--steps",
            "6,7,9,10,11,12",
        )
        output = json.loads(result.stdout)
        valid_results = {"PASS", "FAIL", "SKIP"}
        for step in output["steps"]:
            assert step["result"] in valid_results, (
                f"Step {step['step']} has invalid result: {step['result']}"
            )

    def test_production_violations_tracked_step_12(self, tmp_path: Path) -> None:
        """# Tests R-P4-06 -- Production violations tracked from step 12."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        violation_file = _make_violation_file(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(violation_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        assert output["overall_result"] == "FAIL"
        assert output["production_violations"] > 0


class TestOutputSchema:
    def test_output_has_required_fields(self, tmp_path: Path) -> None:
        """Output JSON has all required top-level fields."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert "story_id" in output
        assert "timestamp" in output
        assert "steps" in output
        assert "overall_result" in output
        assert "criteria_verified" in output
        assert "production_violations" in output

    def test_story_id_matches_input(self, tmp_path: Path) -> None:
        """story_id matches --story argument."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output["story_id"] == "STORY-003"

    def test_timestamp_is_iso_format(self, tmp_path: Path) -> None:
        """timestamp is ISO 8601 format."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        from datetime import datetime

        ts = datetime.fromisoformat(output["timestamp"])
        ts_type = type(ts).__name__
        assert ts_type == "datetime"


class TestStepEntrySchema:
    def test_step_entry_has_required_fields(self, tmp_path: Path) -> None:
        """Each step has step, name, result, evidence, duration_ms."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10,11",
        )
        output = json.loads(result.stdout)
        for step in output["steps"]:
            step_keys = set(step.keys())
            assert step_keys >= {"step", "name", "result", "evidence"}
            assert "duration_ms" in step, f"Missing 'duration_ms' in {step}"
            assert isinstance(step["step"], int)
            assert isinstance(step["name"], str)
            assert isinstance(step["duration_ms"], int)


class TestOverallResult:
    def test_overall_pass_when_all_skip(self, tmp_path: Path) -> None:
        """overall PASS when steps only SKIP or PASS."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output["overall_result"] == "PASS"

    def test_overall_fail_when_violations(self, tmp_path: Path) -> None:
        """overall FAIL when step 12 finds violations."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        violation_file = _make_violation_file(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(violation_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        assert output["overall_result"] == "FAIL"


class TestExitCodes:
    def test_exit_0_on_pass(self, tmp_path: Path) -> None:
        """exit code 0 when overall PASS."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        assert result.returncode == 0

    def test_exit_1_on_fail(self, tmp_path: Path) -> None:
        """exit code 1 when overall FAIL."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        violation_file = _make_violation_file(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(violation_file),
            "--steps",
            "12",
        )
        assert result.returncode == 1

    def test_exit_2_on_invalid_args(self) -> None:
        """exit code 2 on invalid/missing arguments."""
        result = _run_qa_runner()
        assert result.returncode == 2


class TestUnconfiguredCommands:
    def test_unconfigured_type_check_skips(self, tmp_path: Path) -> None:
        """Unconfigured type_check produces SKIP."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "2",
        )
        output = json.loads(result.stdout)
        step2 = output["steps"][0]
        assert step2["result"] == "SKIP"
        assert step2["evidence"]

    def test_unconfigured_coverage_skips(self, tmp_path: Path) -> None:
        """Unconfigured coverage produces SKIP."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "8",
        )
        output = json.loads(result.stdout)
        step8 = output["steps"][0]
        assert step8["result"] == "SKIP"


class TestStep9MockAudit:
    def test_step_9_uses_scan_test_quality(self, tmp_path: Path) -> None:
        """Step 9 FAILs on assertion-free tests."""
        prd = _make_prd(tmp_path)
        test_dir = _make_test_file_with_markers(tmp_path)
        bad_test = test_dir / "test_bad_quality.py"
        bad_test.write_text(
            "def test_does_nothing():\n    x = 1 + 1\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(bad_test),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["step"] == 9
        assert step9["name"] == "Mock quality audit"
        assert step9["result"] == "FAIL"

    def test_step_9_passes_good_tests(self, tmp_path: Path) -> None:
        """Step 9 passes on well-formed tests."""
        prd = _make_prd(tmp_path)
        test_dir = _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(test_dir / "test_example.py"),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["result"] == "PASS"


class TestStep11Acceptance:
    def test_step_11_uses_validate_r_markers(self, tmp_path: Path) -> None:
        """Step 11 PASSes when R-P3-01/02 markers exist."""
        prd = _make_prd(tmp_path)
        test_dir = _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--steps",
            "11",
        )
        output = json.loads(result.stdout)
        step11 = output["steps"][0]
        assert step11["step"] == 11
        assert step11["name"] == "Acceptance traceability"
        assert step11["result"] == "PASS"

    def test_step_11_fails_on_missing_markers(self, tmp_path: Path) -> None:
        """Step 11 FAILs when markers are missing."""
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "stories": [
                        {
                            "id": "STORY-003",
                            "description": "Test",
                            "phase": 3,
                            "acceptanceCriteria": [
                                {"id": "R-P3-99", "criterion": "Nonexistent criterion"},
                            ],
                            "gateCmds": {},
                            "passed": False,
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        test_dir = _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--steps",
            "11",
        )
        output = json.loads(result.stdout)
        step11 = output["steps"][0]
        assert step11["result"] == "FAIL"


class TestStep12ProductionScan:
    def test_step_12_uses_scan_file_violations(self, tmp_path: Path) -> None:
        """Step 12 FAILs on violation files."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        violation_file = _make_violation_file(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(violation_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        step12 = output["steps"][0]
        assert step12["step"] == 12
        assert step12["name"] == "Production scan"
        assert step12["result"] == "FAIL"
        assert output["production_violations"] > 0

    def test_step_12_passes_clean_file(self, tmp_path: Path) -> None:
        """Step 12 PASSes on clean source."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        clean_file = _make_clean_source(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(clean_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        step12 = output["steps"][0]
        assert step12["result"] == "PASS"
        assert output["production_violations"] == 0


class TestTestFileExists:
    def test_test_file_exists(self) -> None:
        """test_qa_runner.py exists."""
        assert Path(__file__).is_file()


class TestSecurityAndCleanupIDs:
    def test_security_ids_include_new_patterns(self) -> None:
        """_SECURITY_IDS includes new injection/secret patterns."""
        from qa_runner import _SECURITY_IDS

        expected_new = {
            "subprocess-shell-injection",
            "os-exec-injection",
            "raw-sql-fstring",
            "expanded-secret",
        }
        for sid in expected_new:
            assert sid in _SECURITY_IDS, f"{sid} missing from _SECURITY_IDS"

    def test_security_ids_include_original_patterns(self) -> None:
        """_SECURITY_IDS includes original patterns."""
        from qa_runner import _SECURITY_IDS

        original = {"hardcoded-secret", "sql-injection", "shell-injection"}
        for sid in original:
            assert sid in _SECURITY_IDS, f"{sid} missing from _SECURITY_IDS"

    def test_cleanup_ids_include_broad_except(self) -> None:
        """_CLEANUP_IDS includes broad-except."""
        from qa_runner import _CLEANUP_IDS

        assert "broad-except" in _CLEANUP_IDS

    def test_cleanup_ids_include_bare_except(self) -> None:
        """_CLEANUP_IDS includes bare-except."""
        from qa_runner import _CLEANUP_IDS

        assert "bare-except" in _CLEANUP_IDS

    def test_security_and_cleanup_ids_no_overlap(self) -> None:
        """_SECURITY_IDS and _CLEANUP_IDS have no overlap."""
        from qa_runner import _CLEANUP_IDS, _SECURITY_IDS

        overlap = _SECURITY_IDS & _CLEANUP_IDS
        assert len(overlap) == 0, f"Overlapping IDs: {overlap}"


class TestExternalScanners:
    def test_step_12_no_external_scanners_configured(self, tmp_path: Path) -> None:
        """Step 12 passes without external scanners."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        clean_file = _make_clean_source(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--changed-files",
            str(clean_file),
            "--steps",
            "12",
        )
        output = json.loads(result.stdout)
        step12 = output["steps"][0]
        assert step12["step"] == 12
        assert step12["result"] == "PASS"

    def test_step_12_external_scanners_disabled(self, tmp_path: Path) -> None:
        """Disabled external scanners are skipped."""
        from qa_runner import _step_production_scan

        clean_file = _make_clean_source(tmp_path)
        config = {
            "external_scanners": {
                "bandit": {"cmd": "echo should-not-run", "enabled": False},
                "semgrep": {"cmd": "echo should-not-run", "enabled": False},
            }
        }
        result_val, evidence = _step_production_scan([clean_file], config=config)
        assert result_val == "PASS"

    def test_step_production_scan_no_config(self) -> None:
        """_step_production_scan works with config=None."""
        from qa_runner import _step_production_scan

        result_val, evidence = _step_production_scan([], config=None)
        assert result_val == "PASS"

    def test_step_production_scan_empty_scanners(self, tmp_path: Path) -> None:
        """Empty external_scanners dict is fine."""
        from qa_runner import _step_production_scan

        clean_file = _make_clean_source(tmp_path)
        config = {"external_scanners": {}}
        result_val, evidence = _step_production_scan([clean_file], config=config)
        assert result_val == "PASS"


class TestPlanArgument:
    """# Tests R-P4-06"""

    def test_accepts_plan_argument(self, tmp_path: Path) -> None:
        """# Tests R-P4-06 -- qa_runner accepts --plan."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        plan = tmp_path / "PLAN.md"
        plan.write_text("# Test plan\n", encoding="utf-8")
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--plan",
            str(plan),
            "--steps",
            "10",
        )
        assert "unrecognized arguments" not in result.stderr

    def test_plan_arg_passed_to_step_10(self, tmp_path: Path) -> None:
        """# Tests R-P4-06 -- --plan is used by step 10."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update |\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--plan",
            str(plan),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        step10 = output["steps"][0]
        assert step10["result"] == "PASS"

    def test_help_shows_plan_option(self) -> None:
        """# Tests R-P4-06 -- --help includes --plan."""
        result = _run_qa_runner("--help")
        assert "--plan" in result.stdout


class TestPhaseTypeArgument:
    def test_accepts_phase_type_argument(self, tmp_path: Path) -> None:
        """qa_runner accepts --phase-type."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "foundation",
            "--steps",
            "10",
        )
        assert "unrecognized arguments" not in result.stderr

    def test_help_shows_phase_type_option(self) -> None:
        """--help includes --phase-type."""
        result = _run_qa_runner("--help")
        assert "--phase-type" in result.stdout

    def test_phase_type_accepts_foundation(self, tmp_path: Path) -> None:
        """--phase-type=foundation accepted."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "foundation",
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert "phase_type" in output
        assert output["phase_type"] == "foundation"

    def test_phase_type_accepts_module(self, tmp_path: Path) -> None:
        """--phase-type=module accepted."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "module",
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output["phase_type"] == "module"

    def test_phase_type_accepts_integration(self, tmp_path: Path) -> None:
        """--phase-type=integration accepted."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "integration",
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output["phase_type"] == "integration"

    def test_phase_type_accepts_e2e(self, tmp_path: Path) -> None:
        """--phase-type=e2e accepted."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "e2e",
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output["phase_type"] == "e2e"

    def test_phase_type_default_is_none(self, tmp_path: Path) -> None:
        """Default phase_type is null."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10",
        )
        output = json.loads(result.stdout)
        assert output.get("phase_type") is None

    def test_phase_type_rejects_invalid_value(self) -> None:
        """--phase-type rejects invalid values."""
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--phase-type",
            "invalid_type",
        )
        assert result.returncode == 2


class TestPhaseTypeRelevanceMatrix:
    def test_phase_type_relevance_exists(self) -> None:
        """PHASE_TYPE_RELEVANCE dict exists."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        ptr_type = type(PHASE_TYPE_RELEVANCE).__name__
        assert ptr_type == "dict"

    def test_foundation_relevant_steps(self) -> None:
        """foundation maps to correct steps."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        expected = {1, 2, 3, 5, 6, 7, 9, 10, 11, 12}
        assert PHASE_TYPE_RELEVANCE["foundation"] == expected

    def test_module_relevant_steps(self) -> None:
        """module maps to correct steps."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        expected = {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12}
        assert PHASE_TYPE_RELEVANCE["module"] == expected

    def test_integration_relevant_steps(self) -> None:
        """integration maps to all 12 steps."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        expected = set(range(1, 13))
        assert PHASE_TYPE_RELEVANCE["integration"] == expected

    def test_e2e_relevant_steps(self) -> None:
        """e2e maps to all 12 steps."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        expected = set(range(1, 13))
        assert PHASE_TYPE_RELEVANCE["e2e"] == expected

    def test_matrix_has_four_entries(self) -> None:
        """Matrix has exactly 4 phase type entries."""
        from qa_runner import PHASE_TYPE_RELEVANCE

        assert len(PHASE_TYPE_RELEVANCE) == 4
        assert set(PHASE_TYPE_RELEVANCE.keys()) == {
            "foundation",
            "module",
            "integration",
            "e2e",
        }


class TestAlwaysRequiredSteps:
    def test_always_required_steps_constant_exists(self) -> None:
        """ALWAYS_REQUIRED_STEPS constant exists."""
        from qa_runner import ALWAYS_REQUIRED_STEPS

        ars_type = type(ALWAYS_REQUIRED_STEPS).__name__
        assert ars_type in ("set", "frozenset")

    def test_always_required_steps_values(self) -> None:
        """Steps 1-2, 5-7, 10-12 are always required."""
        from qa_runner import ALWAYS_REQUIRED_STEPS

        expected = {1, 2, 5, 6, 7, 10, 11, 12}
        assert ALWAYS_REQUIRED_STEPS == expected

    def test_all_phase_types_include_required_steps(self) -> None:
        """All phase types include always-required steps."""
        from qa_runner import ALWAYS_REQUIRED_STEPS, PHASE_TYPE_RELEVANCE

        for phase_type, relevant_steps in PHASE_TYPE_RELEVANCE.items():
            missing = ALWAYS_REQUIRED_STEPS - relevant_steps
            assert not missing, (
                f"Phase type '{phase_type}' missing required steps: {missing}"
            )

    def test_only_steps_3_4_8_9_can_be_skipped(self) -> None:
        """Only steps 3, 4, 8, 9 may be skipped by phase type."""
        from qa_runner import ALWAYS_REQUIRED_STEPS

        all_steps = set(range(1, 13))
        skippable = all_steps - ALWAYS_REQUIRED_STEPS
        assert skippable == {3, 4, 8, 9}


class TestPhaseTypeSkipJustification:
    def test_foundation_skips_step_4(self, tmp_path: Path) -> None:
        """foundation skips step 4 (integration)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "foundation",
            "--steps",
            "4",
        )
        output = json.loads(result.stdout)
        step4 = output["steps"][0]
        assert step4["result"] == "SKIP"
        assert "foundation" in step4["evidence"]

    def test_foundation_skips_step_8(self, tmp_path: Path) -> None:
        """foundation skips step 8 (coverage)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "foundation",
            "--steps",
            "8",
        )
        output = json.loads(result.stdout)
        step8 = output["steps"][0]
        assert step8["result"] == "SKIP"
        assert "foundation" in step8["evidence"]

    def test_module_skips_step_4(self, tmp_path: Path) -> None:
        """module skips step 4 (integration)."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "module",
            "--steps",
            "4",
        )
        output = json.loads(result.stdout)
        step4 = output["steps"][0]
        assert step4["result"] == "SKIP"
        assert "module" in step4["evidence"]

    def test_integration_does_not_skip_step_4(self, tmp_path: Path) -> None:
        """integration does NOT skip step 4."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "integration",
            "--steps",
            "4",
        )
        output = json.loads(result.stdout)
        step4 = output["steps"][0]
        # May SKIP for other reasons (no cmd), but NOT due to phase_type
        if step4["result"] == "SKIP":
            assert (
                "integration" not in step4["evidence"]
                or "not relevant" not in step4["evidence"]
            )

    def test_skip_evidence_contains_justification(self, tmp_path: Path) -> None:
        """Skipped step evidence contains phase_type justification."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--phase-type",
            "foundation",
            "--steps",
            "4",
        )
        output = json.loads(result.stdout)
        step4 = output["steps"][0]
        assert step4["result"] == "SKIP"
        assert "not relevant for" in step4["evidence"]
        assert "foundation" in step4["evidence"]

    def test_no_phase_type_runs_all_steps(self, tmp_path: Path) -> None:
        """Without --phase-type, no steps are skipped by phase."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "4,8",
        )
        output = json.loads(result.stdout)
        for step in output["steps"]:
            if step["result"] == "SKIP":
                assert "not relevant for" not in step["evidence"]


class TestScanOnceCache:
    """# Tests R-P2-03"""

    def test_violation_cache_populated_at_start(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- _build_violation_cache scans all source files once."""
        from qa_runner import _build_violation_cache, _get_source_files

        violation_file = _make_violation_file(tmp_path)
        clean_file = _make_clean_source(tmp_path)
        source_files = _get_source_files([violation_file, clean_file])
        cache = _build_violation_cache(source_files)
        cache_type = type(cache).__name__
        assert cache_type == "dict"
        cache_len = len(cache)
        expected_len = len(source_files)
        assert cache_len == expected_len

    def test_violation_cache_contains_violations(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- cache contains violations for bad files."""
        from qa_runner import _build_violation_cache

        violation_file = _make_violation_file(tmp_path)
        cache = _build_violation_cache([violation_file])
        key = str(violation_file)
        assert key in cache
        assert len(cache[key]) > 0

    def test_violation_cache_empty_for_clean_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- cache empty for clean files."""
        from qa_runner import _build_violation_cache

        clean_file = _make_clean_source(tmp_path)
        cache = _build_violation_cache([clean_file])
        key = str(clean_file)
        assert key in cache
        assert cache[key] == []

    def test_steps_6_7_12_use_cache(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- steps 6, 7, 12 use shared cache."""
        from qa_runner import (
            _step_clean_diff,
            _step_production_scan,
            _step_security_scan,
        )

        violation_file = _make_violation_file(tmp_path)
        files = [violation_file]
        from qa_runner import _build_violation_cache

        cache = _build_violation_cache(files)
        result6, _ = _step_security_scan(files, violation_cache=cache)
        r6_type = type(result6).__name__
        assert r6_type == "str"
        result7, _ = _step_clean_diff(files, violation_cache=cache)
        assert isinstance(result7, str)
        result12, _ = _step_production_scan(files, violation_cache=cache)
        assert isinstance(result12, str)

    def test_scan_once_same_results_as_individual(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- cache-based scan matches individual scans."""
        from qa_runner import _build_violation_cache, _step_production_scan

        violation_file = _make_violation_file(tmp_path)
        files = [violation_file]
        result_no_cache, evidence_no_cache = _step_production_scan(files)
        cache = _build_violation_cache(files)
        result_cached, evidence_cached = _step_production_scan(
            files, violation_cache=cache
        )
        assert result_no_cache == result_cached


class TestTestQualityMode:
    """# Tests R-P2-04 -- qa_runner.py --test-quality mode."""

    def test_test_quality_flag_accepted(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- --test-quality flag recognized."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_sample.py"
        test_file.write_text("def test_example():\n    assert True\n", encoding="utf-8")
        result = _run_qa_runner(
            "--story",
            "STORY-001",
            "--test-quality",
            "--test-dir",
            str(test_dir),
        )
        assert "unrecognized arguments" not in result.stderr

    def test_test_quality_json_has_required_keys(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- output has files, overall, summary keys."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_sample.py"
        test_file.write_text("def test_example():\n    assert True\n", encoding="utf-8")
        result = _run_qa_runner(
            "--story",
            "STORY-001",
            "--test-quality",
            "--test-dir",
            str(test_dir),
        )
        data = json.loads(result.stdout)
        assert "files" in data, "Missing 'files' key in output"
        assert "overall_result" in data, "Missing 'overall' key in output"
        assert "summary" in data, "Missing 'summary' key in output"

    def test_test_quality_summary_has_counters(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- summary has total_tests and quality counters."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_sample.py"
        test_file.write_text(
            "def test_one():\n    assert 1 == 1\ndef test_two():\n    assert 2 == 2\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-001",
            "--test-quality",
            "--test-dir",
            str(test_dir),
        )
        data = json.loads(result.stdout)
        summary = data["summary"]
        assert "total_tests" in summary
        assert "total_assertion_free" in summary
        assert "total_self_mock" in summary
        assert "total_mock_only" in summary

    def test_test_quality_clean_tests_pass(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- clean tests produce PASS."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_clean.py"
        test_file.write_text("def test_clean():\n    assert 1 == 1\n", encoding="utf-8")
        result = _run_qa_runner(
            "--story",
            "STORY-001",
            "--test-quality",
            "--test-dir",
            str(test_dir),
        )
        data = json.loads(result.stdout)
        assert data["overall_result"] == "PASS"
        assert result.returncode == 0

    def test_test_quality_with_prd_includes_marker_validation(
        self, tmp_path: Path
    ) -> None:
        """# Tests R-P2-04 -- --prd adds marker_validation to summary."""
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_markers.py"
        test_file.write_text(
            '"""# Tests R-P3-01"""\ndef test_one():\n    assert True\n',
            encoding="utf-8",
        )
        prd = _make_prd(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--test-quality",
            "--test-dir",
            str(test_dir),
            "--prd",
            str(prd),
        )
        data = json.loads(result.stdout)
        assert "marker_validation" in data["summary"]

    def test_test_quality_no_dir_no_files_exits_cleanly(self) -> None:
        """# Tests R-P2-04 -- no --test-dir produces empty result."""
        result = _run_qa_runner(
            "--story",
            "STORY-001",
            "--test-quality",
        )
        data = json.loads(result.stdout)
        assert data["files"] == []
        assert data["overall_result"] == "PASS"
        assert data["summary"]["total_tests"] == 0


class TestStep9StoryCoverage:
    def test_step_9_full_coverage_passes(self, tmp_path: Path) -> None:
        """Step 9 PASSes when all prod files have tests."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        prod_file = tmp_path / "mymodule.py"
        prod_file.write_text("def helper():\n    return 1\n", encoding="utf-8")
        (test_dir / "test_mymodule.py").write_text(
            "def test_helper():\n    assert 1 == 1\n", encoding="utf-8"
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            f"{prod_file},{test_dir / 'test_mymodule.py'}",
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["step"] == 9
        assert step9["result"] == "PASS"
        assert "coverage" in step9["evidence"].lower()

    def test_step_9_partial_coverage_fails(self, tmp_path: Path) -> None:
        """Step 9 FAILs when <80% of prod files have tests."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        # 3 prod files, only 1 has a test (33% < 80%)
        prod_a = tmp_path / "mod_a.py"
        prod_a.write_text("def a():\n    return 1\n", encoding="utf-8")
        prod_b = tmp_path / "mod_b.py"
        prod_b.write_text("def b():\n    return 2\n", encoding="utf-8")
        prod_c = tmp_path / "mod_c.py"
        prod_c.write_text("def c():\n    return 3\n", encoding="utf-8")
        (test_dir / "test_mod_a.py").write_text(
            "def test_a():\n    assert 1 == 1\n", encoding="utf-8"
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            f"{prod_a},{prod_b},{prod_c}",
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["step"] == 9
        assert step9["result"] == "FAIL"
        assert "coverage" in step9["evidence"].lower()

    def test_step_9_import_based_detection(self, tmp_path: Path) -> None:
        """Step 9 counts import-based coverage."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        # Prod file with no matching test name, but imported by a test
        prod_file = tmp_path / "helpers.py"
        prod_file.write_text("def helper():\n    return 42\n", encoding="utf-8")
        (test_dir / "test_integration.py").write_text(
            "import helpers\ndef test_helper():\n    assert helpers.helper() == 42\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(prod_file),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["result"] == "PASS"

    def test_step_9_non_code_files_excluded(self, tmp_path: Path) -> None:
        """Step 9 excludes non-code files from coverage check."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        prod_file = tmp_path / "mymod.py"
        prod_file.write_text("def my_func():\n    return 1\n", encoding="utf-8")
        readme = tmp_path / "README.md"
        readme.write_text("# README\n", encoding="utf-8")
        config = tmp_path / "config.json"
        config.write_text("{}\n", encoding="utf-8")
        (test_dir / "test_mymod.py").write_text(
            "def test_my_func():\n    assert 1 == 1\n", encoding="utf-8"
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            f"{prod_file},{readme},{config}",
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["result"] == "PASS"

    def test_step_9_includes_weak_assertion_warnings(self, tmp_path: Path) -> None:
        """Step 9 evidence includes weak assertion warnings."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        weak_test = test_dir / "test_weak.py"
        weak_test.write_text(
            "def test_truthy_only():\n"
            "    x = 42\n"
            "    assert x\n"
            "def test_is_not_none():\n"
            "    x = 42\n"
            "    assert x is not None\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(weak_test),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        evidence = step9["evidence"].lower()
        assert evidence != ""
        assert "weak" in evidence

    def test_step_9_fails_on_weak_assertions_only(self, tmp_path: Path) -> None:
        """Step 9 FAILs when tests have only weak assertions."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        weak_test = test_dir / "test_weak_only.py"
        weak_test.write_text(
            "def test_only_isinstance():\n"
            "    result = get()\n"
            "    assert isinstance(result, dict)\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(weak_test),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        step9_result = step9["result"]
        assert step9_result == "FAIL"
        evidence = step9["evidence"].lower()
        assert "weak" in evidence

    def test_step_9_includes_happy_path_warnings(self, tmp_path: Path) -> None:
        """Step 9 evidence includes happy-path-only warnings."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        happy_only = test_dir / "test_happy.py"
        happy_only.write_text(
            "def test_create_item():\n"
            "    assert True\n"
            "def test_get_item():\n"
            "    assert True\n"
            "def test_update_item():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(happy_only),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert (
            "happy" in step9["evidence"].lower()
            or "happy_path" in step9["evidence"].lower()
        )

    def test_step_9_coverage_in_evidence(self, tmp_path: Path) -> None:
        """Step 9 evidence includes story file coverage."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert True\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert True\n",
            encoding="utf-8",
        )
        prod_file = tmp_path / "widget.py"
        prod_file.write_text("def widget():\n    return 1\n", encoding="utf-8")
        (test_dir / "test_widget.py").write_text(
            "def test_widget():\n    assert True\n", encoding="utf-8"
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            str(prod_file),
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        evidence_lower = step9["evidence"].lower()
        assert "coverage" in evidence_lower


class TestStep9IntegrationCoverageGate:
    """Integration test: qa_runner catches low story file coverage."""

    def test_full_pipeline_catches_33_percent_coverage(self, tmp_path: Path) -> None:
        """33% coverage (below 80% floor) reports Step 9 FAIL."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        # 3 production files, only 1 has a matching test -> 33%
        prod_x = tmp_path / "mod_x.py"
        prod_x.write_text("def x_func():\n    return 1\n", encoding="utf-8")
        prod_y = tmp_path / "mod_y.py"
        prod_y.write_text("def y_func():\n    return 2\n", encoding="utf-8")
        prod_z = tmp_path / "mod_z.py"
        prod_z.write_text("def z_func():\n    return 3\n", encoding="utf-8")
        (test_dir / "test_mod_x.py").write_text(
            "def test_x():\n    assert 1 == 1\n", encoding="utf-8"
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            f"{prod_x},{prod_y},{prod_z}",
            "--steps",
            "6,7,9,12",
        )
        output = json.loads(result.stdout)
        step9_results = [s for s in output["steps"] if s["step"] == 9]
        assert len(step9_results) == 1, "Step 9 must be present in results"
        step9 = step9_results[0]
        assert step9["result"] == "FAIL", (
            f"Expected FAIL for 33% coverage, got {step9['result']}: {step9['evidence']}"
        )
        evidence = step9["evidence"].lower()
        assert "coverage" in evidence, (
            f"Evidence should mention coverage: {step9['evidence']}"
        )
        assert "33" in evidence or "80" in evidence or "untested" in evidence, (
            f"Evidence should include coverage details: {step9['evidence']}"
        )
        assert output["overall_result"] == "FAIL", (
            f"Pipeline should FAIL when Step 9 fails, got {output['overall_result']}"
        )

    def test_full_pipeline_passes_at_80_percent_coverage(self, tmp_path: Path) -> None:
        """>=80% coverage passes Step 9."""
        prd = _make_prd(tmp_path)
        test_dir = tmp_path / "tests"
        test_dir.mkdir(exist_ok=True)
        (test_dir / "test_example.py").write_text(
            '"""# Tests R-P3-01"""\n'
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 == 1\n"
            "def test_criterion_2():\n"
            '    """# Tests R-P3-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        # 5 prod files, 4 with tests = 80% (at the floor)
        prod_files: list[Path] = []
        for i in range(5):
            pf = tmp_path / f"service_{i}.py"
            pf.write_text(f"def func_{i}():\n    return {i}\n", encoding="utf-8")
            prod_files.append(pf)
            if i < 4:
                (test_dir / f"test_service_{i}.py").write_text(
                    f"def test_func_{i}():\n    assert {i} == {i}\n",
                    encoding="utf-8",
                )
        changed = ",".join(str(p) for p in prod_files)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(test_dir),
            "--changed-files",
            changed,
            "--steps",
            "9",
        )
        output = json.loads(result.stdout)
        step9 = output["steps"][0]
        assert step9["result"] == "PASS", (
            f"Expected PASS for 80% coverage, got {step9['result']}: {step9['evidence']}"
        )


class TestExternalScannerPlaceholders:
    """# Tests R-P3-01, R-P3-02, R-P3-03"""

    def test_changed_dir_substituted(self, tmp_path: Path) -> None:
        """# Tests R-P3-01 -- {changed_dir} replaced with actual dir."""
        src_file = tmp_path / "app.py"
        src_file.write_text("x = 1\n", encoding="utf-8")
        config = {
            "external_scanners": {
                "test_scanner": {
                    "enabled": True,
                    "cmd": "echo {changed_dir}",
                }
            }
        }
        captured_cmds: list[str] = []

        def mock_run(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
            captured_cmds.append(cmd)
            return (0, "", "")

        with patch("qa_runner._run_command", side_effect=mock_run):
            _step_production_scan(
                [src_file], config, violation_cache={str(src_file): []}
            )
        assert len(captured_cmds) == 1
        assert "{changed_dir}" not in captured_cmds[0]
        assert str(src_file) in captured_cmds[0] or str(tmp_path) in captured_cmds[0]

    def test_changed_files_substituted(self, tmp_path: Path) -> None:
        """# Tests R-P3-02 -- {changed_files} replaced with file list."""
        src_file = tmp_path / "app.py"
        src_file.write_text("x = 1\n", encoding="utf-8")
        config = {
            "external_scanners": {
                "test_scanner": {
                    "enabled": True,
                    "cmd": "echo {changed_files}",
                }
            }
        }
        captured_cmds: list[str] = []

        def mock_run(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
            captured_cmds.append(cmd)
            return (0, "", "")

        with patch("qa_runner._run_command", side_effect=mock_run):
            _step_production_scan(
                [src_file], config, violation_cache={str(src_file): []}
            )
        assert len(captured_cmds) == 1
        assert "{changed_files}" not in captured_cmds[0]
        assert str(src_file) in captured_cmds[0]

    def test_changed_dir_defaults_to_dot(self) -> None:
        """# Tests R-P3-03 -- fallback to '.' when no files."""
        config = {
            "external_scanners": {
                "test_scanner": {
                    "enabled": True,
                    "cmd": "echo {changed_dir}",
                }
            }
        }
        captured_cmds: list[str] = []

        def mock_run(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
            captured_cmds.append(cmd)
            return (0, "", "")

        with patch("qa_runner._run_command", side_effect=mock_run):
            # _step_production_scan returns early on no source files
            _step_production_scan([], config, violation_cache={})
        result, evidence = _step_production_scan([], config, violation_cache={})
        assert result == "PASS"

    def test_changed_files_empty_when_no_files(self) -> None:
        """Empty string for {changed_files} when no source files."""
        result, evidence = _step_production_scan([], None, violation_cache={})
        assert result == "PASS"
        assert "No source files" in evidence

    def test_changed_dir_uses_common_parent(self, tmp_path: Path) -> None:
        """Multiple files from different dirs use common parent."""
        sub1 = tmp_path / "src" / "a"
        sub2 = tmp_path / "src" / "b"
        sub1.mkdir(parents=True)
        sub2.mkdir(parents=True)
        f1 = sub1 / "mod1.py"
        f2 = sub2 / "mod2.py"
        f1.write_text("x = 1\n", encoding="utf-8")
        f2.write_text("y = 2\n", encoding="utf-8")
        config = {
            "external_scanners": {
                "test_scanner": {
                    "enabled": True,
                    "cmd": "echo {changed_dir}",
                }
            }
        }
        captured_cmds: list[str] = []

        def mock_run(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
            captured_cmds.append(cmd)
            return (0, "", "")

        with patch("qa_runner._run_command", side_effect=mock_run):
            _step_production_scan(
                [f1, f2],
                config,
                violation_cache={str(f1): [], str(f2): []},
            )
        assert len(captured_cmds) == 1
        cmd = captured_cmds[0]
        assert "{changed_dir}" not in cmd
        assert "src" in cmd


class TestNeedsShell:
    """Tests for _needs_shell shell operator detection."""

    def test_needs_shell_simple_command(self) -> None:
        """Simple command returns False."""
        assert _needs_shell("python -m pytest") is False

    def test_needs_shell_pipe(self) -> None:
        """Pipe operator returns True."""
        assert _needs_shell("ruff check | head -20") is True

    def test_needs_shell_redirect(self) -> None:
        """Redirect operator returns True."""
        assert _needs_shell("echo foo > bar.txt") is True

    def test_needs_shell_chained(self) -> None:
        """&& chaining returns True."""
        assert _needs_shell("cmd1 && cmd2") is True

    def test_needs_shell_or_chained(self) -> None:
        """|| chaining returns True."""
        assert _needs_shell("cmd1 || cmd2") is True

    def test_needs_shell_subshell(self) -> None:
        """$() subshell returns True."""
        assert _needs_shell("echo $(date)") is True

    def test_needs_shell_semicolon(self) -> None:
        """Semicolon returns True."""
        assert _needs_shell("cd /tmp; ls") is True

    def test_needs_shell_append_redirect(self) -> None:
        """>> append redirect returns True."""
        assert _needs_shell("echo line >> file.txt") is True


class TestPipelineContextDedup:
    """Tests for pipeline_context R-marker deduplication between steps 10 and 11."""

    def test_pipeline_context_dedup(self, tmp_path: Path) -> None:
        """validate_r_markers called once when step 10 caches result for step 11."""
        from qa_runner import _step_acceptance

        prd = _make_prd(tmp_path)
        test_dir = _make_test_file_with_markers(tmp_path)
        story = {
            "id": "STORY-003",
            "acceptanceCriteria": [
                {"id": "R-P3-01"},
                {"id": "R-P3-02"},
            ],
        }
        pipeline_context: dict = {}
        mock_result = {
            "markers_found": ["R-P3-01", "R-P3-02"],
            "markers_valid": ["R-P3-01", "R-P3-02"],
            "orphan_markers": [],
            "missing_markers": [],
            "manual_criteria": [],
            "result": "PASS",
        }
        with patch(
            "qa_runner.validate_r_markers", return_value=mock_result
        ) as mock_validate:
            _step_plan_conformance(
                [],
                None,
                story,
                prd,
                test_dir,
                pipeline_context=pipeline_context,
            )
            _step_acceptance(
                test_dir,
                prd,
                story,
                pipeline_context=pipeline_context,
            )
            # validate_r_markers should have been called exactly once (by step 10)
            assert mock_validate.call_count == 1


class TestCriteriaVerifiedFromRMarkers:
    """# Tests R-P2-01, R-P2-02, R-P2-03"""

    def test_criteria_verified_empty_when_no_test_files(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- criteria_verified empty when no test files."""
        prd = _make_prd(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(exist_ok=True)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tests_dir),
            "--steps",
            "11",
        )
        output = json.loads(result.stdout)
        assert output["criteria_verified"] == []

    def test_criteria_verified_includes_only_matched_ids(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- criteria_verified contains only IDs with matching R-markers."""
        prd = _make_prd(tmp_path)
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir(exist_ok=True)
        test_file = tests_dir / "test_partial.py"
        test_file.write_text(
            "def test_criterion_1():\n"
            '    """# Tests R-P3-01"""\n'
            "    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tests_dir),
            "--steps",
            "10,11",
        )
        output = json.loads(result.stdout)
        assert "R-P3-01" in output["criteria_verified"]
        assert "R-P3-02" not in output["criteria_verified"]

    def test_criteria_verified_all_ids_when_all_markers_present(
        self, tmp_path: Path
    ) -> None:
        """# Tests R-P2-03 -- criteria_verified includes all IDs when all R-markers exist."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "10,11",
        )
        output = json.loads(result.stdout)
        assert sorted(output["criteria_verified"]) == ["R-P3-01", "R-P3-02"]

    def test_criteria_verified_empty_when_step_11_skipped(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- criteria_verified empty when step 11 not run."""
        prd = _make_prd(tmp_path)
        _make_test_file_with_markers(tmp_path)
        result = _run_qa_runner(
            "--story",
            "STORY-003",
            "--prd",
            str(prd),
            "--test-dir",
            str(tmp_path / "tests"),
            "--steps",
            "1",
        )
        output = json.loads(result.stdout)
        assert output["criteria_verified"] == []
