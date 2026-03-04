#!/usr/bin/env python3
"""Test Quality Validator -- Backward-compatible wrapper around qa_runner.

Delegates to qa_runner._run_test_quality() for the actual analysis.
Preserves the original CLI interface (positional files, --dir, --prd).

Usage:
    python test_quality.py FILE [FILE ...]
    python test_quality.py --dir PATH/TO/TESTS
    python test_quality.py --dir PATH --prd PATH/TO/prd.json
    python test_quality.py --help

Output: JSON to stdout with files, overall_result, and summary keys.
Exit codes: 0 = PASS, 1 = FAIL, 2 = bad arguments.
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from qa_runner import _run_test_quality


def _collect_extra_files(paths: list[str]) -> list[Path]:
    """Collect test file paths from positional arguments.

    Args:
        paths: List of file/directory paths from positional arguments.

    Returns:
        List of Path objects pointing to test files.
    """
    result: list[Path] = []
    for p in paths:
        fp = Path(p)
        if fp.is_file():
            result.append(fp)
        elif fp.is_dir():
            for f in sorted(fp.rglob("test_*.py")):
                if f not in result:
                    result.append(f)
            for f in sorted(fp.rglob("*_test.py")):
                if f not in result:
                    result.append(f)
    return result


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser.

    Returns:
        Configured ArgumentParser instance.
    """
    parser = argparse.ArgumentParser(
        prog="test_quality",
        description="Analyze test files for quality anti-patterns.",
        epilog="Exit codes: 0=PASS, 1=FAIL, 2=bad arguments",
    )
    parser.add_argument(
        "files",
        nargs="*",
        help="Test file paths to analyze",
    )
    parser.add_argument(
        "--dir",
        dest="test_dir",
        help="Directory to scan for test_*.py files",
    )
    parser.add_argument(
        "--prd",
        dest="prd_path",
        help="Path to prd.json for R-PN-NN marker validation",
    )
    return parser


def main() -> None:
    """Main entry point for the test quality CLI."""
    parser = _build_parser()
    args = parser.parse_args()

    # Validate: must have either files or --dir
    if not args.files and not args.test_dir:
        parser.print_usage(sys.stderr)
        sys.stderr.write("Error: provide file paths or --dir argument\n")
        sys.exit(2)

    # Validate --dir exists if provided
    if args.test_dir:
        d = Path(args.test_dir)
        if not d.is_dir():
            sys.stderr.write(f"Error: directory not found: {args.test_dir}\n")
            sys.exit(2)

    # Collect extra files from positional arguments
    extra_files = _collect_extra_files(args.files) if args.files else None

    # Resolve paths
    test_dir = Path(args.test_dir) if args.test_dir else None
    prd_path = Path(args.prd_path) if args.prd_path else None

    # Delegate to qa_runner
    output = _run_test_quality(test_dir, prd_path, extra_files=extra_files)

    sys.stdout.write(json.dumps(output, indent=2) + "\n")
    sys.exit(1 if output["overall_result"] == "FAIL" else 0)


if __name__ == "__main__":
    main()
