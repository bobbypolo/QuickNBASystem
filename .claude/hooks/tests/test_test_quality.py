"""Tests for test_quality.py CLI tool."""

import json
import subprocess
import sys
from pathlib import Path


CLI_PATH = Path(__file__).resolve().parent.parent / "test_quality.py"


def run_cli(args: list[str], cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run test_quality.py with given arguments."""
    result = subprocess.run(
        [sys.executable, str(CLI_PATH)] + args,
        capture_output=True,
        text=True,
        timeout=30,
        cwd=cwd,
    )
    return result


# ── CLI existence and help ───────────────────────────────────────────────


class TestCLIExists:
    """# Tests R-P2-06"""

    def test_cli_file_exists(self) -> None:
        """# Tests R-P2-06 -- test_quality.py exists."""
        assert CLI_PATH.exists(), f"CLI not found at {CLI_PATH}"
        assert CLI_PATH.name == "test_quality.py"

    def test_cli_help_exits_0(self) -> None:
        """# Tests R-P2-06 -- --help exits 0 and shows usage."""
        result = run_cli(["--help"])
        assert result.returncode == 0
        assert "usage" in result.stdout.lower() or "help" in result.stdout.lower()

    def test_test_file_exists(self) -> None:
        """test_test_quality.py exists."""
        assert Path(__file__).exists()
        assert Path(__file__).name == "test_test_quality.py"


# ── File list and --dir argument ─────────────────────────────────────────


class TestCLIArguments:
    """# Tests R-P2-06"""

    def test_accepts_file_list(self, tmp_path: Path) -> None:
        """# Tests R-P2-06 -- accepts file paths as positional arguments."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "def test_add():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 0

    def test_accepts_dir_argument(self, tmp_path: Path) -> None:
        """# Tests R-P2-06 -- accepts --dir argument pointing to a directory."""
        test_file = tmp_path / "test_example.py"
        test_file.write_text(
            "def test_add():\n    assert 1 + 1 == 2\n",
            encoding="utf-8",
        )
        result = run_cli(["--dir", str(tmp_path)])
        assert result.returncode == 0

    def test_no_args_exits_2(self) -> None:
        """no arguments exits with code 2."""
        result = run_cli([])
        assert result.returncode == 2


# ── Quality detection tests ──────────────────────────────────────────────


class TestQualityDetection:
    """# Tests ADE-WF-07"""

    def test_detects_assertion_free_tests(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- detects assertion-free tests."""
        test_file = tmp_path / "test_no_assert.py"
        test_file.write_text(
            "def test_nothing():\n    x = 1 + 1\n\n"
            "def test_also_nothing():\n    pass\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 1  # FAIL
        output = json.loads(result.stdout)
        # Check that assertion-free tests are detected
        file_results = output["files"]
        assert len(file_results) >= 1
        file_result = file_results[0]
        assert len(file_result["assertion_free_tests"]) == 2

    def test_detects_self_mock_tests(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- detects self-mock anti-pattern."""
        test_file = tmp_path / "test_self_mock.py"
        test_file.write_text(
            "from unittest.mock import patch\n\n"
            "def test_my_func():\n"
            '    with patch("module.my_func") as mock_func:\n'
            "        mock_func.return_value = 42\n"
            "        result = mock_func()\n"
            "        assert result == 42\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 1  # FAIL
        output = json.loads(result.stdout)
        file_result = output["files"][0]
        assert len(file_result["self_mock_tests"]) > 0

    def test_detects_mock_only_tests(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- detects mock-only anti-pattern."""
        test_file = tmp_path / "test_mock_only.py"
        test_file.write_text(
            "from unittest.mock import MagicMock\n\n"
            "def test_mock_only():\n"
            "    mock = MagicMock()\n"
            "    mock.do_thing()\n"
            "    mock.do_thing.assert_called_once()\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 1  # FAIL
        output = json.loads(result.stdout)
        file_result = output["files"][0]
        mock_count = len(file_result["mock_only_tests"])
        assert mock_count >= 1

    def test_passes_well_formed_tests(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- well-formed tests produce PASS."""
        test_file = tmp_path / "test_good.py"
        test_file.write_text(
            "def test_add():\n    assert 1 + 1 == 2\n\n"
            "def test_sub():\n    assert 3 - 1 == 2\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["overall_result"] == "PASS"


# ── R-PN-NN marker validation ───────────────────────────────────────────


class TestMarkerValidation:
    def test_validates_markers_with_prd(self, tmp_path: Path) -> None:
        """Validates R-PN-NN markers against prd.json."""
        test_file = tmp_path / "test_markers.py"
        test_file.write_text(
            "def test_feature_a():\n"
            '    """# Tests R-P1-01"""\n'
            "    assert 1 == 1\n\n"
            "def test_feature_b():\n"
            '    """# Tests R-P1-02"""\n'
            "    assert 1 == 1\n",
            encoding="utf-8",
        )
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "stories": [
                        {
                            "id": "STORY-001",
                            "acceptanceCriteria": [
                                {"id": "R-P1-01"},
                                {"id": "R-P1-02"},
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = run_cli(["--dir", str(tmp_path), "--prd", str(prd)])
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert "summary" in output
        assert "marker_validation" in output["summary"]

    def test_missing_markers_fails(self, tmp_path: Path) -> None:
        """Missing markers produce FAIL."""
        test_file = tmp_path / "test_incomplete.py"
        test_file.write_text(
            'def test_only_one():\n    """# Tests R-P1-01"""\n    assert True\n',
            encoding="utf-8",
        )
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "stories": [
                        {
                            "id": "STORY-001",
                            "acceptanceCriteria": [
                                {"id": "R-P1-01"},
                                {"id": "R-P1-02"},
                                {"id": "R-P1-03"},
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = run_cli(["--dir", str(tmp_path), "--prd", str(prd)])
        rc = result.returncode
        assert rc == 1  # FAIL due to missing markers
        output = json.loads(result.stdout)
        marker_info = output["summary"]["marker_validation"]
        missing_count = len(marker_info["missing_markers"])
        assert missing_count >= 1

    def test_no_prd_flag_skips_validation(self, tmp_path: Path) -> None:
        """Without --prd flag, marker validation is skipped."""
        test_file = tmp_path / "test_something.py"
        test_file.write_text(
            "def test_it():\n    assert 1 == 1\n",
            encoding="utf-8",
        )
        result = run_cli([str(test_file)])
        assert result.returncode == 0
        output = json.loads(result.stdout)
        # summary should not contain marker_validation when --prd not given
        assert "marker_validation" not in output.get("summary", {})


# ── JSON output structure tests ──────────────────────────────────────────


class TestJSONOutput:
    def test_output_has_files_key(self, tmp_path: Path) -> None:
        """output has 'files' key."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        output = json.loads(result.stdout)
        files_list = output["files"]
        files_type = type(files_list).__name__
        assert files_type == "list"

    def test_output_has_overall_key(self, tmp_path: Path) -> None:
        """output has 'overall_result' key."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        output = json.loads(result.stdout)
        assert "overall_result" in output
        assert output["overall_result"] in ("PASS", "FAIL")

    def test_output_has_summary_key(self, tmp_path: Path) -> None:
        """output has 'summary' key."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        output = json.loads(result.stdout)
        summary = output["summary"]
        summary_type = type(summary).__name__
        assert summary_type == "dict"

    def test_output_is_valid_json(self, tmp_path: Path) -> None:
        """stdout is valid JSON."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        # Should not raise
        data = json.loads(result.stdout)
        data_type = type(data).__name__
        assert data_type == "dict"

    def test_file_entry_has_quality_fields(self, tmp_path: Path) -> None:
        """each file entry has quality analysis fields."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        output = json.loads(result.stdout)
        file_entry = output["files"][0]
        assert "file" in file_entry
        assert "tests_found" in file_entry
        assert "assertion_free_tests" in file_entry
        assert "self_mock_tests" in file_entry
        assert "mock_only_tests" in file_entry
        assert "quality_score" in file_entry

    def test_summary_has_totals(self, tmp_path: Path) -> None:
        """summary contains aggregate totals."""
        test_file = tmp_path / "test_a.py"
        test_file.write_text("def test_x():\n    assert True\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        output = json.loads(result.stdout)
        summary = output["summary"]
        assert "total_tests" in summary
        assert "total_assertion_free" in summary
        assert "total_self_mock" in summary
        assert "total_mock_only" in summary


# ── Exit code tests ──────────────────────────────────────────────────────


class TestExitCodes:
    def test_exits_0_on_pass(self, tmp_path: Path) -> None:
        """Exits 0 when all tests pass quality checks."""
        test_file = tmp_path / "test_good.py"
        test_file.write_text("def test_x():\n    assert 1 == 1\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        assert result.returncode == 0

    def test_exits_1_on_fail(self, tmp_path: Path) -> None:
        """exits 1 when quality issues detected."""
        test_file = tmp_path / "test_bad.py"
        test_file.write_text("def test_x():\n    pass\n", encoding="utf-8")
        result = run_cli([str(test_file)])
        assert result.returncode == 1

    def test_exits_2_on_bad_args(self) -> None:
        """exits 2 on no arguments."""
        result = run_cli([])
        assert result.returncode == 2

    def test_exits_2_on_nonexistent_dir(self) -> None:
        """exits 2 on nonexistent --dir path."""
        result = run_cli(["--dir", "/nonexistent/path/to/tests"])
        assert result.returncode == 2

    def test_exits_0_on_help(self) -> None:
        """exits 0 on --help."""
        result = run_cli(["--help"])
        assert result.returncode == 0
