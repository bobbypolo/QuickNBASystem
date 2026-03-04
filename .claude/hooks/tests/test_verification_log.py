"""Tests for JSONL verification log utilities.

Tests R-P4-14: .claude/hooks/tests/test_verification_log.py exists with
passing tests for JSONL format.

# ADE-WF-08 (full regression: all tests in this file must pass)
"""

import json
import sys
from pathlib import Path


# Add hooks directory to path for imports
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from _qa_lib import (
    append_verification_entry,
    read_verification_log,
)


class TestAppendVerificationEntry:
    """Tests for append_verification_entry (JSONL writer)."""

    def test_write_single_entry(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-001",
            "timestamp": "2026-02-28T12:00:00Z",
            "attempt": 1,
            "overall_result": "PASS",
            "criteria_verified": ["R-P1-01", "R-P1-02"],
            "files_changed": ["src/main.py"],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 1
        parsed = json.loads(lines[0])
        assert parsed["story_id"] == "STORY-001"
        assert parsed["overall_result"] == "PASS"
        assert parsed["criteria_verified"] == ["R-P1-01", "R-P1-02"]

    def test_append_multiple_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        entries = [
            {
                "story_id": "STORY-001",
                "timestamp": "2026-02-28T12:00:00Z",
                "attempt": 1,
                "overall_result": "PASS",
                "criteria_verified": ["R-P1-01"],
                "files_changed": [],
                "production_violations": 0,
            },
            {
                "story_id": "STORY-002",
                "timestamp": "2026-02-28T13:00:00Z",
                "attempt": 1,
                "overall_result": "FAIL",
                "criteria_verified": [],
                "files_changed": ["lib/util.py"],
                "production_violations": 3,
            },
            {
                "story_id": "STORY-002",
                "timestamp": "2026-02-28T14:00:00Z",
                "attempt": 2,
                "overall_result": "PASS",
                "criteria_verified": ["R-P2-01"],
                "files_changed": ["lib/util.py"],
                "production_violations": 0,
            },
        ]
        for entry in entries:
            append_verification_entry(log_path, entry)

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 3
        assert json.loads(lines[0])["story_id"] == "STORY-001"
        assert json.loads(lines[1])["story_id"] == "STORY-002"
        assert json.loads(lines[1])["overall_result"] == "FAIL"
        assert json.loads(lines[2])["attempt"] == 2

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nested" / "dir" / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-001",
            "timestamp": "2026-02-28T12:00:00Z",
            "attempt": 1,
            "overall_result": "PASS",
            "criteria_verified": [],
            "files_changed": [],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)
        assert log_path.exists()
        parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert parsed["story_id"] == "STORY-001"

    def test_each_line_is_valid_json(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        for i in range(5):
            append_verification_entry(
                log_path,
                {
                    "story_id": f"STORY-{i:03d}",
                    "timestamp": "2026-02-28T12:00:00Z",
                    "attempt": 1,
                    "overall_result": "PASS",
                    "criteria_verified": [],
                    "files_changed": [],
                    "production_violations": 0,
                },
            )

        lines = log_path.read_text(encoding="utf-8").strip().splitlines()
        assert len(lines) == 5
        for line in lines:
            parsed = json.loads(line)
            assert "story_id" in parsed

    def test_entry_with_spot_check(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-003",
            "timestamp": "2026-02-28T15:00:00Z",
            "attempt": 1,
            "overall_result": "PASS",
            "criteria_verified": ["R-P3-01"],
            "files_changed": ["hooks/qa_runner.py"],
            "production_violations": 0,
            "spot_check": {
                "unit": {"exit_code": 0, "result": "PASS"},
                "lint": {"exit_code": 0, "result": "PASS"},
            },
        }
        append_verification_entry(log_path, entry)
        parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert parsed["spot_check"]["unit"]["result"] == "PASS"

    def test_entry_with_qa_steps(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-001",
            "timestamp": "2026-02-28T12:00:00Z",
            "attempt": 1,
            "qa_steps": [
                {"step": 1, "name": "lint", "result": "PASS", "duration_ms": 120},
                {"step": 3, "name": "unit_tests", "result": "PASS", "duration_ms": 500},
            ],
            "overall_result": "PASS",
            "criteria_verified": ["R-P1-01"],
            "files_changed": [],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)
        parsed = json.loads(log_path.read_text(encoding="utf-8").strip())
        assert len(parsed["qa_steps"]) == 2
        assert parsed["qa_steps"][0]["name"] == "lint"


class TestReadVerificationLog:
    """Tests for read_verification_log (JSONL reader with error tolerance)."""

    def test_read_valid_entries(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        entries = [
            {"story_id": "STORY-001", "overall_result": "PASS"},
            {"story_id": "STORY-002", "overall_result": "FAIL"},
        ]
        with log_path.open("w", encoding="utf-8") as f:
            for entry in entries:
                f.write(json.dumps(entry) + "\n")

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 2
        assert result["entries"][0]["story_id"] == "STORY-001"
        assert result["entries"][1]["overall_result"] == "FAIL"
        assert result["parse_errors"] == 0

    def test_skip_corrupt_lines(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        content = (
            '{"story_id": "STORY-001", "overall_result": "PASS"}\n'
            "this is not valid json\n"
            '{"story_id": "STORY-002", "overall_result": "PASS"}\n'
            "{broken json\n"
            '{"story_id": "STORY-003", "overall_result": "FAIL"}\n'
        )
        log_path.write_text(content, encoding="utf-8")

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 3
        assert result["parse_errors"] == 2
        assert result["entries"][0]["story_id"] == "STORY-001"
        assert result["entries"][1]["story_id"] == "STORY-002"
        assert result["entries"][2]["story_id"] == "STORY-003"

    def test_missing_file_returns_skip(self, tmp_path: Path) -> None:
        log_path = tmp_path / "nonexistent.jsonl"
        result = read_verification_log(log_path)
        assert result["result"] == "SKIP"
        assert (
            "not found" in result["reason"].lower()
            or "missing" in result["reason"].lower()
        )

    def test_empty_file(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        log_path.write_text("", encoding="utf-8")

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 0
        assert result["parse_errors"] == 0

    def test_blank_lines_ignored(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        content = '{"story_id": "STORY-001"}\n\n   \n{"story_id": "STORY-002"}\n'
        log_path.write_text(content, encoding="utf-8")

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 2
        assert result["parse_errors"] == 0

    def test_round_trip_write_then_read(self, tmp_path: Path) -> None:
        log_path = tmp_path / "verification-log.jsonl"
        original_entries = [
            {
                "story_id": "STORY-001",
                "timestamp": "2026-02-28T12:00:00Z",
                "attempt": 1,
                "overall_result": "PASS",
                "criteria_verified": ["R-P1-01", "R-P1-02"],
                "files_changed": ["src/main.py"],
                "production_violations": 0,
            },
            {
                "story_id": "STORY-002",
                "timestamp": "2026-02-28T13:00:00Z",
                "attempt": 1,
                "overall_result": "FAIL",
                "criteria_verified": [],
                "files_changed": ["lib/util.py"],
                "production_violations": 2,
            },
        ]
        for entry in original_entries:
            append_verification_entry(log_path, entry)

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 2
        assert result["parse_errors"] == 0
        assert result["entries"][0]["story_id"] == "STORY-001"
        assert result["entries"][0]["criteria_verified"] == ["R-P1-01", "R-P1-02"]
        assert result["entries"][1]["production_violations"] == 2


class TestValidateVerificationEntry:
    """Tests for validate_verification_entry schema validation.

    # Tests R-P2-01, R-P2-02, R-P2-03
    """

    def test_valid_pass_entry_returns_empty_list(self) -> None:
        """# Tests R-P2-01"""
        from _qa_lib import validate_verification_entry

        entry = {
            "story_id": "STORY-001",
            "timestamp": "2026-03-03T10:00:00Z",
            "overall_result": "PASS",
            "attempt": 1,
        }
        warnings = validate_verification_entry(entry)
        assert warnings == []

    def test_missing_story_id_returns_error(self) -> None:
        """# Tests R-P2-02"""
        from _qa_lib import validate_verification_entry

        entry = {
            "timestamp": "2026-03-03T10:00:00Z",
            "overall_result": "PASS",
            "attempt": 1,
        }
        warnings = validate_verification_entry(entry)
        warning_count = len(warnings)
        assert warning_count >= 1
        joined = " ".join(warnings)
        assert "story_id" in joined

    def test_invalid_overall_result_returns_error(self) -> None:
        """# Tests R-P2-03"""
        from _qa_lib import validate_verification_entry

        entry = {
            "story_id": "STORY-001",
            "timestamp": "2026-03-03T10:00:00Z",
            "overall_result": "UNKNOWN",
            "attempt": 1,
        }
        warnings = validate_verification_entry(entry)
        warning_count = len(warnings)
        assert warning_count >= 1
        joined = " ".join(warnings)
        assert "overall_result" in joined

    def test_valid_fail_entry_returns_empty_list(self) -> None:
        """Valid FAIL entry with all required keys should pass validation."""
        from _qa_lib import validate_verification_entry

        entry = {
            "story_id": "STORY-002",
            "timestamp": "2026-03-03T10:00:00Z",
            "overall_result": "FAIL",
            "attempt": 2,
            "failure_summary": "Tests failed",
        }
        warnings = validate_verification_entry(entry)
        assert warnings == []

    def test_valid_skip_entry_returns_empty_list(self) -> None:
        """Valid SKIP entry with all required keys should pass validation."""
        from _qa_lib import validate_verification_entry

        entry = {
            "story_id": "STORY-003",
            "timestamp": "2026-03-03T10:00:00Z",
            "overall_result": "SKIP",
            "attempt": 4,
            "failure_summary": "Exhausted retries",
        }
        warnings = validate_verification_entry(entry)
        assert warnings == []

    def test_multiple_missing_keys_returns_multiple_errors(self) -> None:
        """Entry missing multiple required keys returns multiple warnings."""
        from _qa_lib import validate_verification_entry

        entry = {"overall_result": "PASS"}
        warnings = validate_verification_entry(entry)
        assert len(warnings) >= 3  # missing story_id, timestamp, attempt


class TestFailEntries:
    """Tests for FAIL entry round-trip through JSONL.

    # Tests R-P2-04
    """

    def test_fail_entry_round_trip(self, tmp_path: Path) -> None:
        """# Tests R-P2-04"""
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-002",
            "timestamp": "2026-03-03T10:00:00Z",
            "attempt": 2,
            "overall_result": "FAIL",
            "failure_summary": "qa_runner step 3 failed: 2 test failures",
            "criteria_verified": [],
            "files_changed": ["hooks/_qa_lib.py"],
            "production_violations": 1,
        }
        append_verification_entry(log_path, entry)

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 1
        assert result["parse_errors"] == 0
        read_entry = result["entries"][0]
        assert read_entry["story_id"] == "STORY-002"
        assert read_entry["overall_result"] == "FAIL"
        assert (
            read_entry["failure_summary"] == "qa_runner step 3 failed: 2 test failures"
        )
        assert read_entry["attempt"] == 2

    def test_fail_entry_with_plan_hash(self, tmp_path: Path) -> None:
        """FAIL entry preserves plan_hash field through round-trip."""
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-002",
            "timestamp": "2026-03-03T10:00:00Z",
            "attempt": 1,
            "overall_result": "FAIL",
            "failure_summary": "Lint errors",
            "plan_hash": "abc123def456",
            "criteria_verified": [],
            "files_changed": [],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)

        result = read_verification_log(log_path)
        read_entry = result["entries"][0]
        assert read_entry["plan_hash"] == "abc123def456"
        assert read_entry["overall_result"] == "FAIL"


class TestSkipEntries:
    """Tests for SKIP entry round-trip through JSONL.

    # Tests R-P2-05
    """

    def test_skip_entry_round_trip(self, tmp_path: Path) -> None:
        """# Tests R-P2-05"""
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-003",
            "timestamp": "2026-03-03T11:00:00Z",
            "attempt": 4,
            "overall_result": "SKIP",
            "failure_summary": "Exhausted 4 attempts: persistent type errors in module",
            "criteria_verified": [],
            "files_changed": [],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)

        result = read_verification_log(log_path)
        assert len(result["entries"]) == 1
        assert result["parse_errors"] == 0
        read_entry = result["entries"][0]
        assert read_entry["story_id"] == "STORY-003"
        assert read_entry["overall_result"] == "SKIP"
        assert (
            read_entry["failure_summary"]
            == "Exhausted 4 attempts: persistent type errors in module"
        )
        assert read_entry["attempt"] == 4

    def test_skip_entry_with_plan_hash(self, tmp_path: Path) -> None:
        """SKIP entry preserves plan_hash field through round-trip."""
        log_path = tmp_path / "verification-log.jsonl"
        entry = {
            "story_id": "STORY-003",
            "timestamp": "2026-03-03T11:00:00Z",
            "attempt": 4,
            "overall_result": "SKIP",
            "failure_summary": "Exhausted retries",
            "plan_hash": "xyz789",
            "criteria_verified": [],
            "files_changed": [],
            "production_violations": 0,
        }
        append_verification_entry(log_path, entry)

        result = read_verification_log(log_path)
        read_entry = result["entries"][0]
        assert read_entry["plan_hash"] == "xyz789"
        assert read_entry["overall_result"] == "SKIP"


class TestPlanHashFiltering:
    """Tests for plan_hash filtering in read_verification_log.

    # Tests R-P3-01, R-P3-02, R-P3-03
    """

    def _write_mixed_entries(self, log_path: Path) -> None:
        """Helper: write entries with different plan_hash values."""
        entries = [
            {
                "story_id": "STORY-001",
                "overall_result": "PASS",
                "plan_hash": "abc123",
            },
            {
                "story_id": "STORY-002",
                "overall_result": "PASS",
                "plan_hash": "abc123",
            },
            {
                "story_id": "STORY-003",
                "overall_result": "FAIL",
                "plan_hash": "def456",
            },
            {
                "story_id": "STORY-004",
                "overall_result": "PASS",
            },
            {
                "story_id": "STORY-005",
                "overall_result": "SKIP",
                "plan_hash": "abc123",
            },
        ]
        for entry in entries:
            append_verification_entry(log_path, entry)

    def test_filter_by_plan_hash_returns_matching_entries(self, tmp_path: Path) -> None:
        """# Tests R-P3-01

        read_verification_log(path, plan_hash="abc123") returns only entries
        where entry["plan_hash"] == "abc123".
        """
        log_path = tmp_path / "verification-log.jsonl"
        self._write_mixed_entries(log_path)

        result = read_verification_log(log_path, plan_hash="abc123")
        entries = result["entries"]
        entry_count = len(entries)
        assert entry_count == 3
        story_ids = [e["story_id"] for e in entries]
        assert story_ids == ["STORY-001", "STORY-002", "STORY-005"]
        for entry in entries:
            assert entry["plan_hash"] == "abc123"

    def test_no_filter_returns_all_entries(self, tmp_path: Path) -> None:
        """# Tests R-P3-02

        read_verification_log(path, plan_hash=None) returns all entries
        (backward compatible).
        """
        log_path = tmp_path / "verification-log.jsonl"
        self._write_mixed_entries(log_path)

        result = read_verification_log(log_path, plan_hash=None)
        entries = result["entries"]
        entry_count = len(entries)
        assert entry_count == 5

    def test_no_filter_default_returns_all_entries(self, tmp_path: Path) -> None:
        """# Tests R-P3-02

        read_verification_log(path) with no plan_hash arg returns all entries.
        """
        log_path = tmp_path / "verification-log.jsonl"
        self._write_mixed_entries(log_path)

        result = read_verification_log(log_path)
        entries = result["entries"]
        entry_count = len(entries)
        assert entry_count == 5

    def test_filter_excludes_entries_without_plan_hash(self, tmp_path: Path) -> None:
        """# Tests R-P3-03

        read_verification_log(path, plan_hash="abc123") excludes entries
        that have no plan_hash field.
        """
        log_path = tmp_path / "verification-log.jsonl"
        self._write_mixed_entries(log_path)

        result = read_verification_log(log_path, plan_hash="abc123")
        entries = result["entries"]
        # STORY-004 has no plan_hash -- must be excluded
        story_ids = [e["story_id"] for e in entries]
        assert "STORY-004" not in story_ids
        # STORY-003 has plan_hash="def456" -- must be excluded
        assert "STORY-003" not in story_ids

    def test_filter_with_nonexistent_hash_returns_empty(self, tmp_path: Path) -> None:
        """Filter with a hash matching no entries returns empty list."""
        log_path = tmp_path / "verification-log.jsonl"
        self._write_mixed_entries(log_path)

        result = read_verification_log(log_path, plan_hash="nonexistent_hash")
        entries = result["entries"]
        entry_count = len(entries)
        assert entry_count == 0
        assert result["parse_errors"] == 0

    def test_filter_with_corrupt_lines_still_works(self, tmp_path: Path) -> None:
        """Filter handles corrupt lines gracefully alongside plan_hash filtering."""
        log_path = tmp_path / "verification-log.jsonl"
        content = (
            '{"story_id": "STORY-001", "plan_hash": "abc123", "overall_result": "PASS"}\n'
            "not valid json\n"
            '{"story_id": "STORY-002", "plan_hash": "def456", "overall_result": "FAIL"}\n'
            '{"story_id": "STORY-003", "overall_result": "PASS"}\n'
        )
        log_path.write_text(content, encoding="utf-8")

        result = read_verification_log(log_path, plan_hash="abc123")
        entries = result["entries"]
        entry_count = len(entries)
        assert entry_count == 1
        assert entries[0]["story_id"] == "STORY-001"
        assert result["parse_errors"] == 1
