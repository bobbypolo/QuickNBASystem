"""QA engine: test-quality scanning, R-marker validation, story coverage, plan sync, verification logs."""

import hashlib
import json
import re
from pathlib import Path

from _lib import CODE_EXTENSIONS, PROJECT_ROOT, load_workflow_config  # noqa: F401

_TEST_FUNC_RE = re.compile(r"^[ \t]*(?:async\s+)?def\s+(test_\w+)\s*\(", re.MULTILINE)
_ASSERT_RE = re.compile(
    r"\bassert\b|\bassertEqual\b|\bassertTrue\b|\bassertRaises\b"
    r"|\bexpect\b|\bshould\b|\bverify\b|\.assert_called"
)
_SELF_MOCK_RE = re.compile(r"""(?:patch|mock\.patch)\s*\(\s*['"]([^'"]+)['"]\s*\)""")
_MOCK_ASSERT_RE = re.compile(
    r"\.assert_called|\bassert_called_once\b|\bassert_called_with\b"
    r"|\bassert_any_call\b|\bassert_has_calls\b"
)

# Weak assertion patterns: assertions that prove almost nothing.
# Matches: assert x is not None, assert x (bare truthiness), assertTrue(result),
#          assert isinstance(x, T), assert len(x) > 0, assert callable(x),
#          assert hasattr(x, "attr")
# Does NOT match: assertEqual, assert x == value, assertRaises, assert x in y
_WEAK_ASSERT_RE = re.compile(
    r"\bassert\s+\w+\s+is\s+not\s+None\b"  # assert x is not None
    r"|\bassert\s+\w+\s*$"  # assert x (bare truthiness, end of line)
    r"|\bassertTrue\s*\(\s*\w+\s*\)"  # assertTrue(result) with no comparison
    r"|\bassert\s+isinstance\s*\("  # assert isinstance(x, T)
    r"|\bassert\s+len\s*\([^)]*\)\s*>\s*0"  # assert len(x) > 0
    r"|\bassert\s+callable\s*\("  # assert callable(x)
    r"|\bassert\s+hasattr\s*\("  # assert hasattr(x, "attr")
)
# Strong assertion patterns that should NOT be flagged as weak.
_STRONG_ASSERT_RE = re.compile(
    r"\bassertEqual\b"
    r"|\bassertRaises\b"
    r"|\bassert\s+\w+\s*==\s*"  # assert x == value
    r"|\bassert\s+\w+\s*!=\s*"  # assert x != value
    r"|\bassert\s+\w+\s*>\s*"  # assert x > value
    r"|\bassert\s+\w+\s*<\s*"  # assert x < value
    r"|\bassert\s+\w+\s*>=\s*"  # assert x >= value
    r"|\bassert\s+\w+\s*<=\s*"  # assert x <= value
    r"|\bassert\s+\w+\s+in\s+"  # assert x in y
    r"|\bassert\s+\w+\s+not\s+in\s+"  # assert x not in y
    r"|\bassert\s+\w+\s+is\s+(?!not\s+None\b)\w"  # assert x is y (excludes is not None)
)

# Keywords in test function names that indicate negative/error/edge testing.
_NEGATIVE_TEST_KEYWORDS: frozenset[str] = frozenset(
    {
        "invalid",
        "error",
        "fail",
        "reject",
        "edge",
        "boundary",
        "malformed",
        "negative",
    }
)

# Keywords in criterion text that indicate validation behavior.
_VALIDATION_KEYWORDS: frozenset[str] = frozenset(
    {
        "validate",
        "reject",
        "filter",
        "boundary",
        "limit",
        "invalid",
        "error",
    }
)

# Regex to extract public function definitions from a Python source file.
_PUBLIC_FUNC_RE = re.compile(r"^def\s+([a-zA-Z]\w*)\s*\(", re.MULTILINE)


def scan_test_quality(filepath: Path) -> dict:
    """Analyze a test file for quality anti-patterns."""
    file_str = str(filepath)

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return {"file": file_str, "tests_found": 0, "quality_score": "SKIP"}

    test_names = _TEST_FUNC_RE.findall(content)
    if not test_names:
        return {
            "file": file_str,
            "tests_found": 0,
            "assertion_free_tests": [],
            "self_mock_tests": [],
            "mock_only_tests": [],
            "weak_assertion_tests": [],
            "happy_path_only": True,
            "quality_score": "PASS",
        }

    # Split content into per-function blocks for analysis.
    # Handles both module-level functions (indent=0) and class methods (indent>0).
    # Correctly skips multi-line signatures before starting body-end detection.
    lines = content.splitlines()
    func_bodies: dict[str, str] = {}
    current_func: str | None = None
    current_lines: list[str] = []
    current_indent: int = 0
    in_signature: bool = False

    for line in lines:
        match = re.match(r"^([ \t]*)(?:async\s+)?def\s+(test_\w+)\s*\(", line)
        if match:
            if current_func is not None:
                func_bodies[current_func] = "\n".join(current_lines)
            current_func = match.group(2)
            current_indent = len(match.group(1).expandtabs(4))
            current_lines = [line]
            # Check if signature closes on same line (single-line def)
            # Signature ends when we see ')' followed by ':' (with optional return type)
            no_comment = line.split("#")[0]
            in_signature = not (
                ")" in no_comment and ":" in no_comment.rsplit(")", 1)[-1]
            )
        elif in_signature:
            # Still inside multi-line function signature -- wait for ')...:'
            current_lines.append(line)
            no_comment = line.split("#")[0]
            if ")" in no_comment and ":" in no_comment.rsplit(")", 1)[-1]:
                in_signature = False
        elif current_func is not None:
            # End of function: a non-blank line at same or lesser indent
            stripped = line.rstrip()
            if stripped:
                line_indent = len(line) - len(line.lstrip())
                line_indent = len(line[:line_indent].expandtabs(4))
                if line_indent <= current_indent and not stripped.startswith("#"):
                    func_bodies[current_func] = "\n".join(current_lines)
                    current_func = None
                    current_lines = []
                else:
                    current_lines.append(line)
            else:
                current_lines.append(line)

    if current_func is not None:
        func_bodies[current_func] = "\n".join(current_lines)

    assertion_free: list[str] = []
    self_mock: list[str] = []
    mock_only: list[str] = []
    weak_assertion: list[str] = []

    for func_name in test_names:
        body = func_bodies.get(func_name, "")

        # Check assertion-free
        if not _ASSERT_RE.search(body):
            assertion_free.append(func_name)

        # Check self-mock: test patches the function name it tests
        patched = _SELF_MOCK_RE.findall(body)
        for patch_target in patched:
            # Extract the last component of the patch target
            target_func = patch_target.rsplit(".", 1)[-1]
            # If the test function name contains the patched function name
            test_suffix = func_name.replace("test_", "", 1)
            if target_func == test_suffix or target_func in func_name:
                self_mock.append(func_name)
                break

        # Check mock-only: only mock assertions, no real value assertions
        has_mock_assert = bool(_MOCK_ASSERT_RE.search(body))
        has_real_assert = bool(
            re.search(r"\bassert\s+\w|\bassert\s*\(|\bassertEqual\b", body)
        )
        if has_mock_assert and not has_real_assert:
            mock_only.append(func_name)

        # Check weak assertions: only truthiness/is-not-None/assertTrue(x)
        # with no specific value comparison. Skip assertion-free tests.
        if body and _ASSERT_RE.search(body):
            has_weak = bool(_WEAK_ASSERT_RE.search(body))
            has_strong = bool(_STRONG_ASSERT_RE.search(body))
            if has_weak and not has_strong:
                weak_assertion.append(func_name)

    # Happy-path-only detection: check if ANY test name contains a negative keyword.
    has_negative_test = any(
        keyword in name.lower()
        for name in test_names
        for keyword in _NEGATIVE_TEST_KEYWORDS
    )
    happy_path_only = not has_negative_test

    has_issues = bool(assertion_free or self_mock or mock_only or weak_assertion)
    quality_score = "FAIL" if has_issues else "PASS"

    return {
        "file": file_str,
        "tests_found": len(test_names),
        "assertion_free_tests": assertion_free,
        "self_mock_tests": self_mock,
        "mock_only_tests": mock_only,
        "weak_assertion_tests": weak_assertion,
        "happy_path_only": happy_path_only,
        "quality_score": quality_score,
    }


def check_negative_tests(criterion_text: str, test_names: list[str]) -> dict:
    """Check whether a validation criterion has negative/error/edge tests."""
    criterion_lower = criterion_text.lower()
    needs_negative = any(kw in criterion_lower for kw in _VALIDATION_KEYWORDS)

    if not needs_negative:
        return {
            "needs_negative": False,
            "has_negative": False,
            "result": "PASS",
        }

    # Check if any test name contains a negative keyword
    has_negative = any(
        keyword in name.lower()
        for name in test_names
        for keyword in _NEGATIVE_TEST_KEYWORDS
    )

    return {
        "needs_negative": True,
        "has_negative": has_negative,
        "result": "PASS" if has_negative else "WARN",
    }


def check_public_api_coverage(test_file: Path, prod_file: Path) -> dict:
    """Check how many public functions in prod_file are referenced in test_file."""
    empty_result: dict = {
        "total_public": 0,
        "covered": 0,
        "uncovered": [],
        "coverage_pct": 0.0,
    }

    try:
        prod_content = prod_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return dict(empty_result)

    try:
        test_content = test_file.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return dict(empty_result)

    # Extract public function names (not starting with underscore)
    public_funcs = _PUBLIC_FUNC_RE.findall(prod_content)
    if not public_funcs:
        return dict(empty_result)

    total_public = len(public_funcs)
    covered_funcs: list[str] = []
    uncovered_funcs: list[str] = []

    for func_name in public_funcs:
        if func_name in test_content:
            covered_funcs.append(func_name)
        else:
            uncovered_funcs.append(func_name)

    covered_count = len(covered_funcs)
    coverage_pct = (covered_count / total_public) * 100.0 if total_public > 0 else 0.0

    return {
        "total_public": total_public,
        "covered": covered_count,
        "uncovered": uncovered_funcs,
        "coverage_pct": coverage_pct,
    }


_COVERAGE_FLOOR = 80.0


def check_story_file_coverage(changed_files: list[Path], test_dir: Path) -> dict:
    """Check that changed production files have corresponding test files."""
    if not test_dir.is_dir():
        return {
            "result": "SKIP",
            "coverage_pct": 0.0,
            "tested": 0,
            "total_prod": 0,
            "untested": [],
        }

    # Filter to production code files only (exclude test files and non-code)
    prod_files: list[Path] = []
    for f in changed_files:
        if f.suffix not in CODE_EXTENSIONS:
            continue
        name_lower = f.name.lower()
        if name_lower.startswith("test_") or name_lower.endswith("_test.py"):
            continue
        if name_lower == "conftest.py":
            continue
        prod_files.append(f)

    if not prod_files:
        return {
            "result": "SKIP",
            "coverage_pct": 0.0,
            "tested": 0,
            "total_prod": 0,
            "untested": [],
        }

    # Collect all test files and their contents for import-based detection
    test_file_stems: set[str] = set()
    test_file_contents: dict[str, str] = {}
    for tf in sorted(test_dir.rglob("test_*.py")):
        # Extract the module name from test_<module>.py
        stem = tf.stem
        if stem.startswith("test_"):
            module_stem = stem[5:]  # Remove "test_" prefix
            test_file_stems.add(module_stem)
        try:
            test_file_contents[str(tf)] = tf.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError, ValueError):
            pass

    tested: list[str] = []
    untested: list[str] = []

    for pf in prod_files:
        module_stem = pf.stem  # e.g., "module_a" from "module_a.py"
        is_covered = False

        # Check 1: naming convention (test_{module}.py exists)
        if module_stem in test_file_stems:
            is_covered = True

        # Check 2: import-based detection
        if not is_covered:
            for _tf_path, content in test_file_contents.items():
                # Check for "import module_stem" or "from module_stem import"
                if (
                    f"import {module_stem}" in content
                    or f"from {module_stem}" in content
                ):
                    is_covered = True
                    break

        if is_covered:
            tested.append(str(pf))
        else:
            untested.append(str(pf))

    total_prod = len(prod_files)
    tested_count = len(tested)
    coverage_pct = (tested_count / total_prod) * 100.0 if total_prod > 0 else 0.0

    result = "PASS" if coverage_pct >= _COVERAGE_FLOOR else "FAIL"

    return {
        "result": result,
        "coverage_pct": coverage_pct,
        "tested": tested_count,
        "total_prod": total_prod,
        "untested": untested,
    }


VERIFICATION_LOG_PATH = (
    Path(__file__).resolve().parent.parent / "docs" / "verification-log.jsonl"
)

_R_MARKER_RE = re.compile(r"#\s*Tests?\s+(R-P\d+-\d{2}(?:\s*,\s*R-P\d+-\d{2})*)")


def validate_r_markers(
    test_dir: Path,
    prd_path: Path,
    story: dict | None = None,
) -> dict:
    """Validate R-PN-NN markers in test files against prd.json criteria."""
    if not test_dir.is_dir():
        return {"result": "SKIP", "reason": f"test_dir not found: {test_dir}"}

    if not prd_path.is_file():
        return {"result": "SKIP", "reason": f"prd_path not found: {prd_path}"}

    # Extract expected marker IDs from prd.json
    try:
        prd_data = json.loads(prd_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, ValueError):
        return {"result": "SKIP", "reason": f"Cannot parse prd.json: {prd_path}"}

    expected_ids: set[str] = set()
    manual_ids: set[str] = set()
    for s in prd_data.get("stories", []):
        for criterion in s.get("acceptanceCriteria", []):
            cid = criterion.get("id", "")
            if cid:
                expected_ids.add(cid)
                if criterion.get("testType") == "manual":
                    manual_ids.add(cid)

    # -- testFile-based coverage (when story is provided) --
    # Criteria whose testFile is non-null are resolved by file existence.
    # Their IDs are removed from the marker-scan pool so they are not
    # double-counted.
    testfile_covered: set[str] = set()
    testfile_missing: set[str] = set()
    if story is not None:
        for criterion in story.get("acceptanceCriteria", []):
            cid = criterion.get("id", "")
            if not cid:
                continue
            test_file_val = criterion.get("testFile")
            if test_file_val is not None:
                # Resolve relative to project root
                resolved = PROJECT_ROOT / test_file_val
                if resolved.is_file() or resolved.is_dir():
                    testfile_covered.add(cid)
                else:
                    testfile_missing.add(cid)

    # -- R-marker scan (for criteria not handled by testFile) --
    _ID_RE = re.compile(r"R-P\d+-\d{2}")
    found_markers: set[str] = set()
    for test_file in test_dir.rglob("test_*.py"):
        try:
            content = test_file.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for group in _R_MARKER_RE.findall(content):
            found_markers.update(_ID_RE.findall(group))

    # Merge testFile coverage into marker results
    all_covered = found_markers | testfile_covered
    markers_valid = sorted(all_covered & expected_ids)
    orphan_markers = sorted(found_markers - expected_ids)
    # Exclude manual criteria from missing
    testable_ids = expected_ids - manual_ids
    # Exclude testFile-covered criteria from the marker-scan requirement
    need_markers = testable_ids - testfile_covered
    missing_markers = sorted((need_markers - found_markers) | testfile_missing)

    result = "PASS" if not missing_markers else "FAIL"

    return {
        "markers_found": sorted(found_markers),
        "markers_valid": markers_valid,
        "orphan_markers": orphan_markers,
        "missing_markers": missing_markers,
        "manual_criteria": sorted(manual_ids),
        "result": result,
    }


VERIFICATION_ENTRY_REQUIRED_KEYS: frozenset[str] = frozenset(
    {"story_id", "timestamp", "overall_result", "attempt"}
)

_VALID_OVERALL_RESULTS: frozenset[str] = frozenset({"PASS", "FAIL", "SKIP"})


def validate_verification_entry(entry: dict) -> list[str]:
    """Validate a verification log entry against required schema.

    Returns a list of warning strings. Empty list means valid entry.
    Advisory only -- does not block writes.
    """
    warnings: list[str] = []

    # Check required keys
    for key in sorted(VERIFICATION_ENTRY_REQUIRED_KEYS):
        if key not in entry:
            warnings.append(f"Missing required key: {key}")

    # Check overall_result value if present
    overall = entry.get("overall_result")
    if overall is not None and overall not in _VALID_OVERALL_RESULTS:
        warnings.append(
            f"Invalid overall_result: {overall!r} (must be one of {sorted(_VALID_OVERALL_RESULTS)})"
        )

    return warnings


def append_verification_entry(log_path: Path, entry: dict) -> None:
    """Append a single JSON object as a new line to a JSONL verification log."""
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(entry, separators=(",", ":"))
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(line + "\n")
    except (OSError, TypeError, ValueError):
        pass


def read_verification_log(log_path: Path, plan_hash: str | None = None) -> dict:
    """Read a JSONL verification log, skipping corrupt lines.

    Args:
        log_path: Path to the JSONL verification log file.
        plan_hash: Optional plan hash to filter entries. When provided, only
            entries whose ``plan_hash`` field matches are returned.  Entries
            without a ``plan_hash`` field are excluded when a filter is active.
            When ``None`` (default), all entries are returned for backward
            compatibility.

    Returns:
        On success: {"entries": [dict, ...], "parse_errors": int}
        On missing file: {"result": "SKIP", "reason": "..."}
    """
    if not log_path.is_file():
        return {"result": "SKIP", "reason": f"File not found: {log_path}"}

    entries: list[dict] = []
    parse_errors = 0

    try:
        text = log_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError):
        return {"result": "SKIP", "reason": f"Cannot read file: {log_path}"}

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        try:
            entry = json.loads(stripped)
        except (json.JSONDecodeError, ValueError):
            parse_errors += 1
            continue

        # Apply plan_hash filter when provided
        if plan_hash is not None:
            entry_hash = entry.get("plan_hash")
            if entry_hash != plan_hash:
                continue

        entries.append(entry)

    return {"entries": entries, "parse_errors": parse_errors}


_PLAN_CRITERIA_RE = re.compile(r"^-\s+(R-P\d+-\d{2}):", re.MULTILINE)


def extract_plan_r_markers(plan_path: Path) -> set[str]:
    """Extract R-PN-NN markers from bullet-format criteria lines in a PLAN.md file.

    Only matches lines formatted as ``- R-Pn-nn: ...`` (Done When bullets).
    Markers appearing in tables, prose, or other contexts are ignored.
    """
    try:
        content = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return set()

    return set(_PLAN_CRITERIA_RE.findall(content))


# Regex to capture full bullet-format R-marker lines for hashing
_PLAN_CRITERIA_LINE_RE = re.compile(r"^-\s+R-P\d+-\d{2}:.*$", re.MULTILINE)


def compute_plan_hash(plan_path: Path) -> str:
    """Compute a normalized hash of PLAN.md based on criteria bullet lines only.

    Extracts only ``- R-Pn-nn: ...`` bullet lines, strips whitespace,
    sorts them, and returns the SHA-256 hex digest.  This makes the hash
    insensitive to formatting, prose, table content, or whitespace changes
    that don't affect the acceptance criteria contract.

    Returns empty string on read errors.
    """
    try:
        content = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return ""

    lines = _PLAN_CRITERIA_LINE_RE.findall(content)
    normalized = "\n".join(sorted(line.strip() for line in lines))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def check_plan_prd_sync(plan_path: Path, prd_path: Path) -> dict:
    """Check whether PLAN.md and prd.json R-markers are in sync."""
    plan_markers = extract_plan_r_markers(plan_path)

    prd_markers: set[str] = set()
    try:
        prd_data = json.loads(prd_path.read_text(encoding="utf-8"))
        for story in prd_data.get("stories", []):
            for criterion in story.get("acceptanceCriteria", []):
                cid = criterion.get("id", "")
                if cid:
                    prd_markers.add(cid)
        # Union with legacyMarkerIds for backward compatibility
        for legacy_id in prd_data.get("legacyMarkerIds", []):
            if legacy_id:
                prd_markers.add(legacy_id)
    except (json.JSONDecodeError, OSError, ValueError):
        return {
            "in_sync": True,
            "plan_markers": [],
            "prd_markers": [],
            "added": [],
            "removed": [],
            "plan_hash": "",
        }

    # Compute normalized plan hash (R-marker lines only)
    plan_hash = compute_plan_hash(plan_path)

    added = sorted(plan_markers - prd_markers)
    removed = sorted(prd_markers - plan_markers)

    return {
        "in_sync": len(added) == 0 and len(removed) == 0,
        "plan_markers": sorted(plan_markers),
        "prd_markers": sorted(prd_markers),
        "added": added,
        "removed": removed,
        "plan_hash": plan_hash,
    }


_PLAN_CHANGES_RE = re.compile(
    r"^\|\s*(?:MODIFY|CREATE|DELETE)\s*\|\s*`?([^`|\s]+?)`?\s*\|",
    re.MULTILINE,
)


def parse_plan_changes(plan_path: Path) -> set[str]:
    """Extract file paths from PLAN.md Changes tables."""
    try:
        content = plan_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return set()

    return {m.group(1).strip() for m in _PLAN_CHANGES_RE.finditer(content)}
