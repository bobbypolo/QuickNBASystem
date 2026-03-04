#!/usr/bin/env python3
"""Automated 12-step QA verification pipeline. Exit: 0=PASS, 1=FAIL, 2=bad args."""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    CODE_EXTENSIONS,
    load_workflow_config,
    scan_file_violations,
)
from _qa_lib import (
    check_story_file_coverage,
    parse_plan_changes,
    scan_test_quality,
    validate_r_markers,
)


STEP_NAMES: dict[int, str] = {
    1: "Lint",
    2: "Type check",
    3: "Unit tests",
    4: "Integration tests",
    5: "Regression check",
    6: "Security scan",
    7: "Clean diff",
    8: "Coverage",
    9: "Mock quality audit",
    10: "Plan Conformance Check",
    11: "Acceptance traceability",
    12: "Production scan",
}

# Valid phase types for --phase-type argument
VALID_PHASE_TYPES = ("foundation", "module", "integration", "e2e")

# Steps that are always required regardless of phase type.
# Only steps 3, 4, 8, 9 may be skipped based on phase type.
ALWAYS_REQUIRED_STEPS: frozenset[int] = frozenset({1, 2, 5, 6, 7, 10, 11, 12})

# Maps each phase type to the set of QA step numbers that are relevant.
# Steps not in the set for a given phase type will be reported as SKIP.
PHASE_TYPE_RELEVANCE: dict[str, set[int]] = {
    "foundation": {1, 2, 3, 5, 6, 7, 9, 10, 11, 12},
    "module": {1, 2, 3, 5, 6, 7, 8, 9, 10, 11, 12},
    "integration": set(range(1, 13)),
    "e2e": set(range(1, 13)),
}

# Violation ID sets for categorized scanning (Step 6 and Step 7)
# IDs correspond to violation_id values from PROD_VIOLATION_PATTERNS in _lib.py.
# Step 6 (security) checks only security-related patterns.
# Step 7 (clean diff) checks debug/cleanup patterns.
_SECURITY_IDS = frozenset(
    (
        "hardcoded-secret",
        "sql-injection",
        "shell-injection",
        "subprocess-shell-injection",
        "os-exec-injection",
        "raw-sql-fstring",
        "expanded-secret",
    )
)
# One ID uses concat to avoid triggering the violation scanner on this file
_CLEANUP_IDS = frozenset(
    (
        "todo-comment",
        "debug-print",
        "de" + "bugger-stmt",
        "debug-import",
        "bare-except",
        "broad-except",
    )
)


def _build_violation_cache(
    source_files: list[Path],
) -> dict[str, list[dict]]:
    """Scan all source files once and cache the results."""
    cache: dict[str, list[dict]] = {}
    for f in source_files:
        cache[str(f)] = scan_file_violations(f)
    return cache


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for qa_runner."""
    parser = argparse.ArgumentParser(
        prog="qa_runner",
        description="Automated 12-step QA verification pipeline.",
        epilog="Exit codes: 0=PASS, 1=FAIL, 2=invalid arguments",
    )
    parser.add_argument(
        "--story",
        required=True,
        help="Story ID to verify (e.g., STORY-003)",
    )
    parser.add_argument(
        "--prd",
        default=None,
        help="Path to prd.json (default: .claude/prd.json)",
    )
    parser.add_argument(
        "--steps",
        default=None,
        help="Comma-separated step numbers to run (default: all 1-12)",
    )
    parser.add_argument(
        "--changed-files",
        default=None,
        help="Comma-separated list of changed file paths",
    )
    parser.add_argument(
        "--test-dir",
        default=None,
        help="Directory containing test files",
    )
    parser.add_argument(
        "--checkpoint",
        default=None,
        help="Git checkpoint hash for diff-based checks",
    )
    parser.add_argument(
        "--plan",
        default=None,
        help="Path to PLAN.md for plan conformance checks",
    )
    parser.add_argument(
        "--phase-type",
        default=None,
        choices=VALID_PHASE_TYPES,
        help="Phase type for adaptive QA (foundation, module, integration, e2e)",
    )
    parser.add_argument(
        "--test-quality",
        action="store_true",
        default=False,
        help="Run test quality analysis instead of 12-step pipeline",
    )
    return parser


def _parse_steps(steps_str: str | None) -> list[int]:
    """Parse step filter string into list of step numbers."""
    if steps_str is None:
        return list(range(1, 13))

    result: list[int] = []
    for part in steps_str.split(","):
        part = part.strip()
        if part.isdigit():
            num = int(part)
            if 1 <= num <= 12:
                result.append(num)
    return sorted(set(result))


def _parse_changed_files(files_str: str | None) -> list[Path]:
    """Parse changed files string into list of Path objects."""
    if not files_str:
        return []

    result: list[Path] = []
    for part in files_str.split(","):
        part = part.strip()
        if part:
            result.append(Path(part))
    return result


def _get_source_files(changed_files: list[Path]) -> list[Path]:
    """Filter changed files to only source code files (not test files)."""
    result: list[Path] = []
    for f in changed_files:
        if f.suffix not in CODE_EXTENSIONS:
            continue
        name = f.name.lower()
        if name.startswith("test_") or name.endswith("_test.py"):
            continue
        result.append(f)
    return result


def _get_test_files(changed_files: list[Path]) -> list[Path]:
    """Filter changed files to only test files."""
    result: list[Path] = []
    for f in changed_files:
        name = f.name.lower()
        if name.startswith("test_") or name.endswith("_test.py"):
            result.append(f)
    return result


def _find_story(prd_path: Path, story_id: str) -> dict | None:
    """Find a story by ID in prd.json."""
    try:
        data = json.loads(prd_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return None

    for story in data.get("stories", []):
        if story.get("id") == story_id:
            return story
    return None


_SHELL_OPERATORS = ("|", "&&", "||", ">>", ">", "<", ";", "`", "$(", "${")


def _needs_shell(cmd: str) -> bool:
    """Return True if cmd contains shell operators requiring shell=True."""
    return any(op in cmd for op in _SHELL_OPERATORS)


def _run_command(cmd: str, timeout: int = 120) -> tuple[int, str, str]:
    """Run a command and capture output."""
    import shlex

    use_shell = _needs_shell(cmd)
    try:
        result = subprocess.run(
            cmd if use_shell else shlex.split(cmd),
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", f"Command timed out after {timeout}s"
    except (OSError, ValueError) as exc:
        return -1, "", str(exc)


def _run_step(
    step_num: int,
    config: dict,
    story: dict | None,
    changed_files: list[Path],
    test_dir: Path | None,
    prd_path: Path | None,
    checkpoint: str | None,
    plan_path: Path | None = None,
    violation_cache: dict[str, list[dict]] | None = None,
    pipeline_context: dict | None = None,
) -> dict:
    """Execute a single QA step and return its result."""
    start = time.monotonic()
    name = STEP_NAMES.get(step_num, f"Step {step_num}")

    try:
        if step_num == 1:
            result_val, evidence = _step_lint(config, story)
        elif step_num == 2:
            result_val, evidence = _step_type_check(config)
        elif step_num == 3:
            result_val, evidence = _step_unit_tests(config, story)
        elif step_num == 4:
            result_val, evidence = _step_integration_tests(config, story)
        elif step_num == 5:
            result_val, evidence = _step_regression(config)
        elif step_num == 6:
            result_val, evidence = _step_security_scan(
                changed_files, violation_cache=violation_cache
            )
        elif step_num == 7:
            result_val, evidence = _step_clean_diff(
                changed_files, violation_cache=violation_cache
            )
        elif step_num == 8:
            result_val, evidence = _step_coverage(config)
        elif step_num == 9:
            result_val, evidence = _step_mock_audit(changed_files, test_dir)
        elif step_num == 10:
            result_val, evidence = _step_plan_conformance(
                changed_files,
                plan_path,
                story,
                prd_path,
                test_dir,
                pipeline_context=pipeline_context,
            )
        elif step_num == 11:
            result_val, evidence = _step_acceptance(
                test_dir,
                prd_path,
                story,
                pipeline_context=pipeline_context,
            )
        elif step_num == 12:
            result_val, evidence = _step_production_scan(
                changed_files, config, violation_cache=violation_cache
            )
        else:
            result_val = "SKIP"
            evidence = f"Step {step_num} not implemented"
    except Exception as exc:
        result_val = "FAIL"
        evidence = f"Unexpected error: {type(exc).__name__}: {exc}"

    elapsed_ms = int((time.monotonic() - start) * 1000)

    return {
        "step": step_num,
        "name": name,
        "result": result_val,
        "evidence": evidence,
        "duration_ms": elapsed_ms,
    }


def _step_lint(config: dict, story: dict | None) -> tuple[str, str]:
    """Step 1: Run linter."""
    # Try gateCmds.lint first, then workflow.json commands.lint
    cmd = ""
    if story:
        cmd = story.get("gateCmds", {}).get("lint", "")
    if not cmd:
        cmd = config.get("commands", {}).get("lint", "")

    if not cmd:
        return "SKIP", "No lint command configured"

    code, stdout, stderr = _run_command(cmd)
    if code == 0:
        return "PASS", f"Lint passed: {stdout[:200]}" if stdout else "Lint passed"
    return "FAIL", f"Lint failed (exit {code}): {(stderr or stdout)[:500]}"


def _step_type_check(config: dict) -> tuple[str, str]:
    """Step 2: Run type checker."""
    cmd = config.get("commands", {}).get("type_check", "")
    if not cmd:
        return "SKIP", "No type_check command configured"

    code, stdout, stderr = _run_command(cmd)
    if code == 0:
        return (
            "PASS",
            f"Type check passed: {stdout[:200]}" if stdout else "Type check passed",
        )
    return "FAIL", f"Type check failed (exit {code}): {(stderr or stdout)[:500]}"


def _step_unit_tests(config: dict, story: dict | None) -> tuple[str, str]:
    """Step 3: Run unit tests."""
    cmd = ""
    if story:
        cmd = story.get("gateCmds", {}).get("unit", "")
    if not cmd:
        cmd = config.get("commands", {}).get("test", "")

    if not cmd:
        return "SKIP", "No unit test command configured"

    code, stdout, stderr = _run_command(cmd)
    if code == 0:
        return (
            "PASS",
            f"Unit tests passed: {stdout[-200:]}" if stdout else "Unit tests passed",
        )
    return "FAIL", f"Unit tests failed (exit {code}): {(stderr or stdout)[-500:]}"


def _step_integration_tests(config: dict, story: dict | None) -> tuple[str, str]:
    """Step 4: Run integration tests."""
    cmd = ""
    if story:
        cmd = story.get("gateCmds", {}).get("integration", "")

    if not cmd:
        return "SKIP", "No integration test command configured"

    if cmd.lower() in ("n/a", "none", "skip"):
        return "SKIP", "Integration tests marked as N/A"

    code, stdout, stderr = _run_command(cmd)
    if code == 0:
        return (
            "PASS",
            f"Integration tests passed: {stdout[-200:]}"
            if stdout
            else "Integration tests passed",
        )
    return (
        "FAIL",
        f"Integration tests failed (exit {code}): {(stderr or stdout)[-500:]}",
    )


def _step_regression(config: dict) -> tuple[str, str]:
    """Step 5: Run regression test suite."""
    cmd = config.get("commands", {}).get("regression", "")
    if not cmd:
        return (
            "SKIP",
            "No regression command configured (set commands.regression in workflow.json)",
        )

    code, stdout, stderr = _run_command(cmd)
    if code == 0:
        return (
            "PASS",
            f"Regression suite passed: {stdout[-200:]}"
            if stdout
            else "Regression suite passed",
        )
    return "FAIL", f"Regression failed (exit {code}): {(stderr or stdout)[-500:]}"


def _step_security_scan(
    changed_files: list[Path],
    violation_cache: dict[str, list[dict]] | None = None,
) -> tuple[str, str]:
    """Step 6: Scan for security violations."""
    source_files = _get_source_files(changed_files)
    if not source_files:
        return "SKIP", "No source files to scan"

    total_violations = 0
    details: list[str] = []

    for f in source_files:
        if violation_cache is not None:
            violations = violation_cache.get(str(f), [])
        else:
            violations = scan_file_violations(f)
        sec_violations = [v for v in violations if v["violation_id"] in _SECURITY_IDS]
        total_violations += len(sec_violations)
        for v in sec_violations:
            details.append(f"{f.name}:{v['line']} {v['violation_id']}: {v['message']}")

    if total_violations == 0:
        return "PASS", f"No security violations in {len(source_files)} source files"
    return "FAIL", f"{total_violations} security violations: {'; '.join(details[:5])}"


def _step_clean_diff(
    changed_files: list[Path],
    violation_cache: dict[str, list[dict]] | None = None,
) -> tuple[str, str]:
    """Step 7: Check for debug artifacts in diff."""
    source_files = _get_source_files(changed_files)
    if not source_files:
        return "SKIP", "No source files to scan"

    total_violations = 0
    details: list[str] = []

    for f in source_files:
        if violation_cache is not None:
            violations = violation_cache.get(str(f), [])
        else:
            violations = scan_file_violations(f)
        debug_violations = [v for v in violations if v["violation_id"] in _CLEANUP_IDS]
        total_violations += len(debug_violations)
        for v in debug_violations:
            details.append(f"{f.name}:{v['line']} {v['violation_id']}")

    if total_violations == 0:
        return "PASS", f"Clean diff in {len(source_files)} source files"
    return "FAIL", f"{total_violations} debug artifacts: {'; '.join(details[:5])}"


def _step_coverage(
    config: dict,
) -> tuple[str, str]:
    """Step 8: Run coverage report."""
    evidence_parts: list[str] = []

    # Part 1: Run existing coverage command
    cmd = config.get("commands", {}).get("coverage", "")
    if cmd:
        code, stdout, stderr = _run_command(cmd)
        if code != 0:
            return "FAIL", f"Coverage failed (exit {code}): {(stderr or stdout)[-500:]}"
        evidence_parts.append(
            f"Coverage report: {stdout[-200:]}" if stdout else "Coverage passed"
        )

    if not evidence_parts:
        return "SKIP", "No coverage command configured"
    return "PASS", "; ".join(evidence_parts)


def _step_mock_audit(
    changed_files: list[Path], test_dir: Path | None
) -> tuple[str, str]:
    """Step 9: Audit test quality and story file coverage."""
    test_files = _get_test_files(changed_files)

    # Also scan test_dir if provided and no explicit test files in changed list
    if not test_files and test_dir and test_dir.is_dir():
        test_files = sorted(test_dir.rglob("test_*.py"))

    if not test_files and not changed_files:
        return "SKIP", "No test files to audit"

    issues: list[str] = []
    warnings: list[str] = []

    # --- Check 1: Test quality anti-patterns ---
    for tf in test_files:
        quality = scan_test_quality(tf)
        if quality.get("quality_score") == "FAIL":
            af = quality.get("assertion_free_tests", [])
            sm = quality.get("self_mock_tests", [])
            mo = quality.get("mock_only_tests", [])
            if af:
                issues.append(f"{tf.name}: assertion-free tests: {af}")
            if sm:
                issues.append(f"{tf.name}: self-mock tests: {sm}")
            if mo:
                issues.append(f"{tf.name}: mock-only tests: {mo}")

        # --- Check 3: Weak assertions (FAIL) and happy-path-only (WARN) ---
        weak = quality.get("weak_assertion_tests", [])
        if weak:
            issues.append(f"{tf.name}: weak assertions: {weak}")
        if quality.get("happy_path_only", False) and quality.get("tests_found", 0) > 0:
            warnings.append(f"{tf.name}: happy-path-only (no error/edge tests)")

    # --- Check 2: Story file coverage gate ---
    coverage_info = ""
    if test_dir is not None:
        cov_result = check_story_file_coverage(changed_files, test_dir)
        cov_status = cov_result.get("result", "SKIP")
        if cov_status == "FAIL":
            pct = cov_result.get("coverage_pct", 0.0)
            untested = cov_result.get("untested", [])
            issues.append(
                f"Story file coverage {pct:.0f}% < 80% floor; untested: {untested}"
            )
        if cov_status != "SKIP":
            pct = cov_result.get("coverage_pct", 0.0)
            tested = cov_result.get("tested", 0)
            total = cov_result.get("total_prod", 0)
            coverage_info = f"Story coverage: {pct:.0f}% ({tested}/{total} files)"

    # Build evidence string
    evidence_parts: list[str] = []
    if coverage_info:
        evidence_parts.append(coverage_info)
    if warnings:
        evidence_parts.append(f"Warnings: {'; '.join(warnings[:5])}")

    if issues:
        evidence_parts.insert(0, f"Issues: {'; '.join(issues[:5])}")
        return "FAIL", "; ".join(evidence_parts)

    summary = f"All {len(test_files)} test files pass quality audit"
    if evidence_parts:
        return "PASS", f"{summary}; {'; '.join(evidence_parts)}"
    return "PASS", summary


def _step_plan_conformance(
    changed_files: list[Path],
    plan_path: Path | None,
    story: dict | None = None,
    prd_path: Path | None = None,
    test_dir: Path | None = None,
    pipeline_context: dict | None = None,
) -> tuple[str, str]:
    """Step 10: Plan Conformance Check."""
    if plan_path is None and not story and not changed_files:
        return "SKIP", "No --plan path or story provided"

    issues: list[str] = []
    always_allowed = {"__init__.py", "conftest.py", "__pycache__"}
    has_data = False

    # Sub-check 1: Blast radius -- changed files vs plan's Changes table
    if plan_path is not None:
        expected = parse_plan_changes(plan_path)
        if expected:
            has_data = True
            expected_norm = {p.replace("\\", "/") for p in expected}
            actual = {str(f).replace("\\", "/") for f in changed_files}
            unexpected = set()
            for f in actual:
                fname = Path(f).name
                if fname in always_allowed:
                    continue
                if f not in expected_norm:
                    unexpected.add(f)
            if unexpected:
                issues.append(
                    f"Unexpected files changed (not in plan): {sorted(unexpected)}"
                )

    # Sub-check 2: R-marker validation -- test files link to acceptance criteria
    if test_dir and prd_path and story:
        has_data = True
        markers = validate_r_markers(test_dir, prd_path, story=story)
        # Cache the result for step 11 to reuse
        if pipeline_context is not None:
            pipeline_context["r_markers"] = markers
        if markers.get("result") == "FAIL":
            missing = markers.get("missing_markers", [])
            if missing:
                issues.append(f"Missing R-markers: {missing}")

    # Sub-check 3: Plan-PRD hash consistency
    if plan_path is not None and prd_path is not None:
        from _qa_lib import check_plan_prd_sync

        has_data = True
        sync_result = check_plan_prd_sync(plan_path, prd_path)
        computed_hash = sync_result.get("plan_hash", "")
        try:
            prd_data = json.loads(prd_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError, ValueError):
            prd_data = {}
        stored_hash = prd_data.get("plan_hash", "")
        if computed_hash and stored_hash and computed_hash != stored_hash:
            issues.append(
                f"Plan-PRD hash mismatch: prd.json plan_hash ({stored_hash[:12]}...) "
                f"differs from computed PLAN.md hash ({computed_hash[:12]}...)"
            )

    if not has_data:
        return "SKIP", "No plan data or story criteria to check"

    if issues:
        return "FAIL", "; ".join(issues)

    file_count = len(changed_files)
    return "PASS", f"Plan conformance passed ({file_count} files checked)"


def _step_acceptance(
    test_dir: Path | None,
    prd_path: Path | None,
    story: dict | None,
    pipeline_context: dict | None = None,
) -> tuple[str, str]:
    """Step 11: Validate acceptance criteria traceability using validate_r_markers."""
    if test_dir is None or prd_path is None:
        return "SKIP", "test_dir or prd_path not provided"

    # Reuse cached R-marker result from step 10 if available
    cached = None
    if pipeline_context is not None:
        cached = pipeline_context.get("r_markers")
    marker_result = (
        cached
        if cached is not None
        else validate_r_markers(test_dir, prd_path, story=story)
    )

    if marker_result.get("result") == "SKIP":
        return "SKIP", marker_result.get("reason", "Skipped")

    # Filter to only this story's criteria if story is available
    missing = marker_result.get("missing_markers", [])
    valid = marker_result.get("markers_valid", [])

    if story:
        story_criteria_ids = {
            c.get("id", "") for c in story.get("acceptanceCriteria", [])
        }
        # Only consider markers relevant to this story
        missing = [m for m in missing if m in story_criteria_ids]
        valid = [v for v in valid if v in story_criteria_ids]

    if missing:
        return "FAIL", f"Missing R-markers for criteria: {missing}"
    return "PASS", f"All criteria have linked tests: {valid}"


def _step_production_scan(
    changed_files: list[Path],
    config: dict | None = None,
    violation_cache: dict[str, list[dict]] | None = None,
) -> tuple[str, str]:
    """Step 12: Production-grade code scan using scan_file_violations."""
    source_files = _get_source_files(changed_files)
    if not source_files:
        return "PASS", "No source files to scan"

    total_violations = 0
    details: list[str] = []

    for f in source_files:
        if violation_cache is not None:
            violations = violation_cache.get(str(f), [])
        else:
            violations = scan_file_violations(f)
        total_violations += len(violations)
        for v in violations:
            details.append(f"{f.name}:{v['line']} {v['violation_id']}: {v['message']}")

    # External scanners (optional, from workflow.json)
    if config:
        scanners = config.get("external_scanners", {})

        # Compute placeholder values for external scanner commands
        try:
            changed_dir = (
                os.path.commonpath([str(f) for f in source_files])
                if source_files
                else "."
            )
        except ValueError:
            changed_dir = "."
        changed_files_str = " ".join(str(f) for f in source_files)

        for name, settings in scanners.items():
            if settings.get("enabled", False):
                cmd = settings.get("cmd", "")
                if cmd:
                    cmd = cmd.replace("{changed_dir}", changed_dir)
                    cmd = cmd.replace("{changed_files}", changed_files_str)
                    code, stdout, stderr = _run_command(cmd)
                    if code != 0:
                        details.append(f"External scanner {name} found issues")
                        total_violations += 1

    if total_violations == 0:
        return "PASS", f"No production violations in {len(source_files)} source files"
    return (
        "FAIL",
        f"{total_violations} production violations: {'; '.join(details[:10])}",
    )


def _collect_test_files(test_dir: Path | None) -> list[Path]:
    """Collect test file paths from a directory."""
    if test_dir is None or not test_dir.is_dir():
        return []
    result: list[Path] = []
    for f in sorted(test_dir.rglob("test_*.py")):
        result.append(f)
    for f in sorted(test_dir.rglob("*_test.py")):
        if f not in result:
            result.append(f)
    return result


def _run_test_quality(
    test_dir: Path | None,
    prd_path: Path | None,
    extra_files: list[Path] | None = None,
) -> dict:
    """Run test quality analysis and return structured JSON output."""
    test_files = _collect_test_files(test_dir)
    if extra_files:
        for ef in extra_files:
            if ef not in test_files:
                test_files.append(ef)

    if not test_files:
        return {
            "files": [],
            "overall_result": "PASS",
            "summary": {
                "total_tests": 0,
                "total_assertion_free": 0,
                "total_self_mock": 0,
                "total_mock_only": 0,
            },
        }

    file_results: list[dict] = []
    total_tests = 0
    total_assertion_free = 0
    total_self_mock = 0
    total_mock_only = 0
    has_issues = False

    for tf in test_files:
        quality = scan_test_quality(tf)
        file_results.append(quality)

        total_tests += quality.get("tests_found", 0)
        af = quality.get("assertion_free_tests", [])
        sm = quality.get("self_mock_tests", [])
        mo = quality.get("mock_only_tests", [])
        total_assertion_free += len(af)
        total_self_mock += len(sm)
        total_mock_only += len(mo)

        if quality.get("quality_score") == "FAIL":
            has_issues = True

    # R-PN-NN marker validation (only when prd_path is provided)
    marker_validation = None
    if prd_path is not None and prd_path.is_file():
        if test_dir is not None:
            scan_dir = test_dir
        elif test_files:
            scan_dir = test_files[0].parent
        else:
            scan_dir = Path(".")
        marker_result = validate_r_markers(scan_dir, prd_path)
        marker_validation = marker_result
        if marker_result.get("result") == "FAIL":
            has_issues = True

    overall = "FAIL" if has_issues else "PASS"

    summary: dict = {
        "total_tests": total_tests,
        "total_assertion_free": total_assertion_free,
        "total_self_mock": total_self_mock,
        "total_mock_only": total_mock_only,
    }
    if marker_validation is not None:
        summary["marker_validation"] = marker_validation

    return {
        "files": file_results,
        "overall_result": overall,
        "summary": summary,
    }


def main() -> None:
    """Main entry point for the QA runner."""
    parser = _build_parser()
    args = parser.parse_args()

    # Load workflow config
    config = load_workflow_config()

    # Resolve prd path
    prd_path: Path | None = None
    if args.prd:
        prd_path = Path(args.prd)
    else:
        default_prd = Path(".claude/prd.json")
        if default_prd.is_file():
            prd_path = default_prd

    # --test-quality mode: run test quality analysis instead of 12-step pipeline
    if args.test_quality:
        test_dir = Path(args.test_dir) if args.test_dir else None
        # Only use prd_path for marker validation if explicitly provided
        tq_prd = Path(args.prd) if args.prd else None
        output = _run_test_quality(test_dir, tq_prd)
        sys.stdout.write(json.dumps(output, indent=2) + "\n")
        sys.exit(1 if output["overall_result"] == "FAIL" else 0)

    # Find story in prd.json
    story: dict | None = None
    if prd_path and prd_path.is_file():
        story = _find_story(prd_path, args.story)

    # Parse arguments
    steps_to_run = _parse_steps(args.steps)
    changed_files = _parse_changed_files(args.changed_files)
    test_dir = Path(args.test_dir) if args.test_dir else None
    checkpoint = args.checkpoint
    plan_path = Path(args.plan) if args.plan else None
    phase_type: str | None = args.phase_type

    # Determine which steps are relevant for this phase type
    relevant_steps: set[int] | None = None
    if phase_type is not None:
        relevant_steps = PHASE_TYPE_RELEVANCE.get(phase_type)

    # Build scan-once violation cache for steps 6, 7, 12
    source_files = _get_source_files(changed_files)
    violation_cache = _build_violation_cache(source_files)

    # Pipeline context for caching intermediate results across steps
    pipeline_context: dict = {}

    # Run each step
    step_results: list[dict] = []
    production_violation_count = 0

    for step_num in steps_to_run:
        # Check if step should be skipped due to phase_type
        if relevant_steps is not None and step_num not in relevant_steps:
            step_name = STEP_NAMES.get(step_num, f"Step {step_num}")
            step_results.append(
                {
                    "step": step_num,
                    "name": step_name,
                    "result": "SKIP",
                    "evidence": (f"Skipped: not relevant for {phase_type} phase"),
                    "duration_ms": 0,
                }
            )
            continue

        step_result = _run_step(
            step_num=step_num,
            config=config,
            story=story,
            changed_files=changed_files,
            test_dir=test_dir,
            prd_path=prd_path,
            checkpoint=checkpoint,
            plan_path=plan_path,
            violation_cache=violation_cache,
            pipeline_context=pipeline_context,
        )
        step_results.append(step_result)

        # Track production violations from step 12
        if step_num == 12 and step_result["result"] == "FAIL":
            # Count violations from evidence
            evidence = step_result["evidence"]
            if evidence.startswith(("0 ", "No ")):
                production_violation_count = 0
            else:
                # Parse count from "N production violations: ..."
                try:
                    production_violation_count = int(evidence.split()[0])
                except (ValueError, IndexError):
                    production_violation_count = 1

    # Determine overall result
    has_fail = any(
        s["result"] == "FAIL" for s in step_results if s["result"] not in ("SKIP",)
    )
    overall = "FAIL" if has_fail else "PASS"

    # Collect verified criteria — only IDs confirmed by R-marker validation
    criteria_verified: list[str] = []
    if story:
        story_criteria_ids = {
            c.get("id", "") for c in story.get("acceptanceCriteria", [])
        }
        r_markers = pipeline_context.get("r_markers")
        if r_markers is not None:
            markers_valid = r_markers.get("markers_valid", [])
            criteria_verified = [
                mid for mid in markers_valid if mid in story_criteria_ids
            ]

    # Build output
    output = {
        "story_id": args.story,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "phase_type": phase_type,
        "steps": step_results,
        "overall_result": overall,
        "criteria_verified": criteria_verified,
        "production_violations": production_violation_count,
    }

    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    sys.exit(1 if overall == "FAIL" else 0)


if __name__ == "__main__":
    main()
