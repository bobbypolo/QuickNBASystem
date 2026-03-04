"""Validate PLAN.md quality with deterministic checks.

CLI script that validates plan quality by checking for:
- Measurable verbs in Done When criteria (rejects vague-only criteria)
- R-PN-NN format IDs on all Done When items
- Non-empty Testing Strategy per phase
- No placeholder syntax in verification commands
- Test File column coverage in Changes tables

Usage:
    python plan_validator.py --plan PATH [--strict]

Exit codes:
    0 = PASS (all checks passed)
    1 = FAIL (one or more checks failed)
    2 = Bad arguments or file not found
"""

import argparse
import json
import re
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

# Vague verbs that indicate unmeasurable criteria
_VAGUE_VERBS = frozenset(
    {"works", "handles", "supports", "manages", "ensures", "properly", "correctly"}
)

# Measurable verbs that indicate testable behavior
_MEASURABLE_VERBS = frozenset(
    {
        "rejects",
        "returns",
        "raises",
        "contains",
        "produces",
        "creates",
        "emits",
        "increments",
        "decrements",
        "appends",
        "writes",
        "reads",
        "validates",
        "outputs",
        "calls",
        "stores",
        "sets",
        "clears",
        "deletes",
        "removes",
        "updates",
        "exports",
        "imports",
        "passes",
        "fails",
        "exits",
        "logs",
        "sends",
        "receives",
        "matches",
        "includes",
        "excludes",
        "generates",
        "parses",
        "loads",
        "saves",
        "counts",
        "reports",
        "detects",
        "scans",
        "checks",
        "verifies",
        "accepts",
        "blocks",
        "merges",
        "runs",
    }
)

# R-PN-NN marker pattern for Done When items
_DONE_WHEN_R_ID_RE = re.compile(r"^-\s*(R-P\d+-\d{2}):")

# Phase header pattern
_PHASE_HEADER_RE = re.compile(r"^##\s+Phase\s+\d+", re.MULTILINE)

# Placeholder patterns in verification commands
_PLACEHOLDER_RE = re.compile(
    r"\[.*?\]|(?<!\w)TBD(?!\w)|your_command_here", re.IGNORECASE
)

# Changes table row with Test File column (5+ columns)
_CHANGES_ROW_WITH_TEST_RE = re.compile(
    r"^\|\s*(?:CREATE|MODIFY)\s*\|"  # Action column
    r"\s*`?([^`|\n]+?)`?\s*\|"  # File column
    r"\s*[^|]*\|"  # Description column
    r"\s*`?([^`|\n]*?)`?\s*\|"  # Test File column
    r"\s*[^|]*\|",  # Test Type column
    re.MULTILINE,
)

# Changes table row without Test File column (3 columns only)
_CHANGES_ROW_NO_TEST_RE = re.compile(
    r"^\|\s*(?:CREATE|MODIFY)\s*\|"  # Action column
    r"\s*`?([^`|\n]+?)`?\s*\|"  # File column
    r"\s*[^|]*\|"  # Description column
    r"\s*$",
    re.MULTILINE,
)

# Untested Files table marker
_UNTESTED_FILES_RE = re.compile(r"###?\s+Untested\s+Files", re.IGNORECASE)

# Test file exclusion patterns (files that are tests themselves)
_TEST_FILE_PATTERNS = frozenset({"test_", "tests/", "N/A", "(self)"})


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------


def _split_plan_into_phases(content: str) -> list[tuple[str, str]]:
    """Split PLAN.md content into (header, body) tuples per phase.

    Args:
        content: Full PLAN.md text content.

    Returns:
        List of (phase_header, phase_body) tuples. The body extends
        from the header to the next phase header or end of file.
    """
    phases: list[tuple[str, str]] = []
    headers = list(_PHASE_HEADER_RE.finditer(content))

    for i, match in enumerate(headers):
        header_line = content[match.start() : content.index("\n", match.start())]
        start = match.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(content)
        body = content[start:end]
        phases.append((header_line, body))

    return phases


def _extract_done_when_items(phase_body: str) -> list[str]:
    """Extract Done When bullet items from a phase body.

    Args:
        phase_body: Text content of a single plan phase.

    Returns:
        List of Done When line strings (including the R-PN-NN prefix if present).
    """
    items: list[str] = []
    in_done_when = False

    for line in phase_body.splitlines():
        stripped = line.strip()
        if (
            stripped.lower().startswith("### done when")
            or stripped.lower() == "done when"
        ):
            in_done_when = True
            continue
        if in_done_when:
            if stripped.startswith("###") or stripped.startswith("## "):
                break
            if stripped.startswith("- "):
                items.append(stripped[2:].strip())
            elif stripped.startswith("```"):
                break

    return items


def _extract_verification_command(phase_body: str) -> str:
    """Extract the verification command from a phase body.

    Args:
        phase_body: Text content of a single plan phase.

    Returns:
        The verification command text, or empty string if not found.
    """
    in_verification = False
    in_code_block = False
    cmd_lines: list[str] = []

    for line in phase_body.splitlines():
        stripped = line.strip()
        if "verification command" in stripped.lower():
            in_verification = True
            continue
        if in_verification:
            if stripped.startswith("```") and not in_code_block:
                in_code_block = True
                continue
            if stripped.startswith("```") and in_code_block:
                break
            if in_code_block:
                cmd_lines.append(stripped)

    return "\n".join(cmd_lines).strip()


def _is_production_file(filepath: str) -> bool:
    """Check if a filepath represents a production (non-test) file.

    Args:
        filepath: File path string to check.

    Returns:
        True if the file is a production file (not a test or N/A marker).
    """
    lower = filepath.lower().strip()
    if not lower:
        return False
    for pattern in _TEST_FILE_PATTERNS:
        if pattern in lower:
            return False
    return True


# ---------------------------------------------------------------------------
# Check functions (the 5 _check_* helpers)
# ---------------------------------------------------------------------------


def _check_vague_criteria(phases: list[tuple[str, str]]) -> dict:
    """Check that Done When criteria contain measurable verbs.

    Args:
        phases: List of (header, body) tuples from the plan.

    Returns:
        Check result dict with name, result, and evidence.
    """
    failing_criteria: list[str] = []

    for _header, body in phases:
        items = _extract_done_when_items(body)
        for item in items:
            words = set(re.findall(r"\b[a-z]+\b", item.lower()))
            has_vague = bool(words & _VAGUE_VERBS)
            has_measurable = bool(words & _MEASURABLE_VERBS)
            if has_vague and not has_measurable:
                # Extract R-ID if present for reporting
                r_match = _DONE_WHEN_R_ID_RE.match(f"- {item}")
                r_id = r_match.group(1) if r_match else "unknown"
                failing_criteria.append(f"{r_id}: {item[:120]}")

    if failing_criteria:
        return {
            "name": "vague_criteria",
            "result": "FAIL",
            "evidence": "; ".join(failing_criteria),
        }
    return {
        "name": "vague_criteria",
        "result": "PASS",
        "evidence": "All criteria contain measurable verbs",
    }


def _check_r_id_format(phases: list[tuple[str, str]]) -> dict:
    """Check that all Done When items have R-PN-NN format IDs.

    Args:
        phases: List of (header, body) tuples from the plan.

    Returns:
        Check result dict with name, result, and evidence.
    """
    missing_ids: list[str] = []

    for header, body in phases:
        items = _extract_done_when_items(body)
        for item in items:
            r_match = _DONE_WHEN_R_ID_RE.match(f"- {item}")
            if not r_match:
                missing_ids.append(f"{header}: {item[:80]}")

    if missing_ids:
        return {
            "name": "r_id_format",
            "result": "FAIL",
            "evidence": f"Missing R-PN-NN IDs: {'; '.join(missing_ids)}",
        }
    return {
        "name": "r_id_format",
        "result": "PASS",
        "evidence": "All Done When items have R-PN-NN format IDs",
    }


def _check_testing_strategy(phases: list[tuple[str, str]]) -> dict:
    """Check that each phase has a non-empty Testing Strategy section.

    Args:
        phases: List of (header, body) tuples from the plan.

    Returns:
        Check result dict with name, result, and evidence.
    """
    missing_phases: list[str] = []

    for header, body in phases:
        if "### testing strategy" not in body.lower():
            missing_phases.append(header)
            continue
        # Check it has at least one table row (pipe-delimited line after header row)
        in_strategy = False
        has_content_row = False
        for line in body.splitlines():
            if "testing strategy" in line.lower() and line.strip().startswith("#"):
                in_strategy = True
                continue
            if in_strategy:
                stripped = line.strip()
                if stripped.startswith("###") or stripped.startswith("## "):
                    break
                if stripped.startswith("|") and "---" not in stripped:
                    # Skip header rows (contain column names like What, Type)
                    lower_line = stripped.lower()
                    if "what" not in lower_line and "type" not in lower_line:
                        has_content_row = True
                        break

        if not has_content_row:
            missing_phases.append(f"{header} (empty)")

    if missing_phases:
        return {
            "name": "testing_strategy",
            "result": "FAIL",
            "evidence": f"Missing or empty Testing Strategy: {'; '.join(missing_phases)}",
        }
    return {
        "name": "testing_strategy",
        "result": "PASS",
        "evidence": "All phases have non-empty Testing Strategy sections",
    }


def _check_verification_placeholders(phases: list[tuple[str, str]]) -> dict:
    """Check that verification commands do not contain placeholder syntax.

    Args:
        phases: List of (header, body) tuples from the plan.

    Returns:
        Check result dict with name, result, and evidence.
    """
    placeholder_phases: list[str] = []

    for header, body in phases:
        cmd = _extract_verification_command(body)
        if not cmd:
            continue
        if _PLACEHOLDER_RE.search(cmd):
            placeholder_phases.append(f"{header}: {cmd[:80]}")

    if placeholder_phases:
        return {
            "name": "placeholder_commands",
            "result": "FAIL",
            "evidence": f"Placeholder syntax found: {'; '.join(placeholder_phases)}",
        }
    return {
        "name": "placeholder_commands",
        "result": "PASS",
        "evidence": "No placeholder syntax in verification commands",
    }


def _check_test_file_coverage(phases: list[tuple[str, str]]) -> dict:
    """Check that production files in Changes tables have Test File entries.

    A phase passes if either:
    - All CREATE/MODIFY production files have a Test File column entry, OR
    - The phase has an Untested Files justification table.

    Args:
        phases: List of (header, body) tuples from the plan.

    Returns:
        Check result dict with name, result, and evidence.
    """
    uncovered_phases: list[str] = []

    for header, body in phases:
        has_untested_table = bool(_UNTESTED_FILES_RE.search(body))

        # Find Changes table rows with Test File column
        rows_with_test = _CHANGES_ROW_WITH_TEST_RE.findall(body)
        # Find Changes table rows without Test File column (3-column format)
        rows_no_test = _CHANGES_ROW_NO_TEST_RE.findall(body)

        if rows_no_test and not has_untested_table:
            # Has production file rows but no Test File column and no justification
            prod_files = [f for f in rows_no_test if _is_production_file(f)]
            if prod_files:
                uncovered_phases.append(
                    f"{header}: missing Test File column for {', '.join(prod_files[:3])}"
                )
            continue

        # Check rows that have Test File column but empty entries
        if rows_with_test:
            missing_test: list[str] = []
            for filepath, test_file in rows_with_test:
                if _is_production_file(filepath) and not test_file.strip():
                    missing_test.append(filepath.strip())
            if missing_test and not has_untested_table:
                uncovered_phases.append(
                    f"{header}: no test file for {', '.join(missing_test[:3])}"
                )

    if uncovered_phases:
        return {
            "name": "test_file_coverage",
            "result": "FAIL",
            "evidence": f"Production files without test coverage: {'; '.join(uncovered_phases)}",
        }
    return {
        "name": "test_file_coverage",
        "result": "PASS",
        "evidence": "All production files have test file entries or justification",
    }


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def validate_plan_quality(plan_path: Path) -> dict:
    """Validate PLAN.md quality with deterministic checks.

    Runs the following checks on each phase:
    - Measurable verb check (rejects vague-only criteria)
    - R-PN-NN format on all Done When items
    - Non-empty Testing Strategy per phase
    - No placeholder syntax in verification commands
    - Test File column coverage in Changes tables

    Args:
        plan_path: Path to the PLAN.md file.

    Returns:
        Dict with keys:
        - result: "PASS", "FAIL", or "SKIP"
        - checks: list of dicts with name, result, evidence
        - reason: (only when result is "SKIP") explanation string

        Returns {"result": "SKIP", "reason": str} when the file
        does not exist or cannot be read.
    """
    if not plan_path.is_file():
        return {"result": "SKIP", "reason": f"File not found: {plan_path}"}

    try:
        content = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return {"result": "SKIP", "reason": f"Cannot read file: {plan_path}"}

    phases = _split_plan_into_phases(content)
    if not phases:
        return {
            "result": "SKIP",
            "reason": "No phases found in plan",
        }

    checks = [
        _check_vague_criteria(phases),
        _check_r_id_format(phases),
        _check_testing_strategy(phases),
        _check_verification_placeholders(phases),
        _check_test_file_coverage(phases),
    ]

    overall = "FAIL" if any(c["result"] == "FAIL" for c in checks) else "PASS"

    return {"result": overall, "checks": checks}


def validate_plan(plan_path: Path) -> dict:
    """Validate a PLAN.md file and return structured results.

    This is a convenience wrapper around validate_plan_quality() that
    provides the function signature expected by tests and CLI.

    Args:
        plan_path: Path to the PLAN.md file.

    Returns:
        Dict with keys: result ("PASS"/"FAIL"/"SKIP"),
        checks (list of per-check dicts), and optionally reason.
    """
    return validate_plan_quality(plan_path)


def main() -> None:
    """CLI entry point for plan validation."""
    parser = argparse.ArgumentParser(
        description="Validate PLAN.md quality with deterministic checks"
    )
    parser.add_argument(
        "--plan",
        type=Path,
        required=True,
        help="Path to the PLAN.md file to validate",
    )
    args = parser.parse_args()

    if not args.plan.is_file():
        sys.stderr.write(f"Error: Plan file not found: {args.plan}\n")
        sys.exit(2)

    result = validate_plan(args.plan)
    json.dump(result, sys.stdout, indent=2)
    sys.stdout.write("\n")

    if result.get("result") == "FAIL":
        sys.exit(1)
    elif result.get("result") == "SKIP":
        sys.exit(2)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
