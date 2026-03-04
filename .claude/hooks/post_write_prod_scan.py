#!/usr/bin/env python3
"""Post-Write Production Scan -- Warn on production code violations.

Runs after Edit/Write tool use on code files. Scans for production
violations using scan_file_violations() from _lib.py. Two-tier enforcement:
security violations (severity=block) exit 2 to block the action, hygiene
violations (severity=warn) exit 0 with warnings. Skips test files and
non-code files. Stateless: scan-and-print only, no state writes.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (  # noqa: E402
    CODE_EXTENSIONS,
    audit_log,
    load_workflow_config,
    parse_hook_stdin,
    scan_file_violations,
)


def _is_test_file(filepath: Path) -> bool:
    """Check if a file is a test file based on naming conventions.

    Args:
        filepath: Path to check.

    Returns:
        True if the filename matches test_* or *_test.* patterns.
    """
    name = filepath.name
    stem = filepath.stem
    return name.startswith("test_") or stem.endswith("_test")


def _is_hook_file(filepath: str) -> bool:
    """Check if a file is inside the .claude/hooks/ directory.

    Args:
        filepath: File path string to check.

    Returns:
        True if the path contains .claude/hooks/ or .claude\\hooks\\.
    """
    normalized = filepath.replace("\\", "/")
    return ".claude/hooks/" in normalized


def _is_excluded(filepath: str, patterns: list[str]) -> bool:
    """Check if a file matches any exclude pattern.

    Args:
        filepath: File path string to check.
        patterns: List of fnmatch-style glob patterns.

    Returns:
        True if the filename matches any pattern.
    """
    import fnmatch

    name = Path(filepath).name
    return any(fnmatch.fnmatch(name, pat) for pat in patterns)


def _is_code_file(filepath: Path) -> bool:
    """Check if a file is a source code file based on extension.

    Args:
        filepath: Path to check.

    Returns:
        True if the file extension is in CODE_EXTENSIONS.
    """
    return filepath.suffix.lower() in CODE_EXTENSIONS


def main() -> None:
    """Main entry point for the production scan hook."""
    data = parse_hook_stdin()
    tool_input = data.get("tool_input", {})

    # Flexible key search for the target file (same pattern as post_format.py)
    file_path = (
        tool_input.get("file_path")
        or tool_input.get("file")
        or tool_input.get("targetFile")
        or tool_input.get("TargetFile")
        or tool_input.get("path")
    )

    if not file_path:
        sys.exit(0)

    p = Path(file_path)

    # Skip non-code files
    if not _is_code_file(p):
        sys.exit(0)

    # Skip test files
    if _is_test_file(p):
        sys.exit(0)

    # Skip hook files (files inside .claude/hooks/)
    if _is_hook_file(file_path):
        sys.exit(0)

    # Skip files matching workflow.json exclude_patterns
    config = load_workflow_config()
    exclude_patterns = (
        config.get("qa_runner", {})
        .get("production_scan", {})
        .get("exclude_patterns", [])
    )
    if _is_excluded(file_path, exclude_patterns):
        sys.exit(0)

    # Scan for violations
    violations = scan_file_violations(p)

    if violations:
        has_block = any(v.get("severity") == "block" for v in violations)
        for v in violations:
            line = v.get("line", "?")
            vid = v.get("violation_id", "unknown")
            msg = v.get("message", "")
            sev = v.get("severity", "warn")
            tag = "PROD BLOCK" if sev == "block" else "PROD WARN"
            sys.stdout.write(f"[{tag}] {vid}: {file_path}:{line} -- {msg}\n")
        sys.stdout.flush()

        if has_block:
            audit_log(
                "post_write_prod_scan",
                "block",
                f"{len(violations)} violation(s) in {file_path} (security)",
            )
            sys.exit(2)
        else:
            audit_log(
                "post_write_prod_scan",
                "warn",
                f"{len(violations)} violation(s) in {file_path} (hygiene)",
            )
    else:
        audit_log("post_write_prod_scan", "clean", file_path)

    sys.exit(0)


if __name__ == "__main__":
    main()
