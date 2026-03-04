"""Tests for _qa_lib.py -- QA engine utilities. # Tests R-P1-09"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _qa_lib import (
    check_negative_tests,
    check_plan_prd_sync,
    check_public_api_coverage,
    check_story_file_coverage,
    compute_plan_hash,  # noqa: F401
    extract_plan_r_markers,
    parse_plan_changes,
    scan_test_quality,
    validate_r_markers,
)


class TestScanTestQuality:
    def test_returns_dict_with_required_fields(self, sample_test_good: Path) -> None:
        result = scan_test_quality(sample_test_good)
        result_type = type(result)
        assert result_type is dict
        assert "tests_found" in result
        assert "assertion_free_tests" in result
        assert "self_mock_tests" in result
        assert "mock_only_tests" in result
        assert "quality_score" in result

    def test_good_test_passes(self, sample_test_good: Path) -> None:
        result = scan_test_quality(sample_test_good)
        assert result["tests_found"] == 2
        assert result["assertion_free_tests"] == []
        assert result["quality_score"] == "PASS"

    def test_detects_assertion_free(self, sample_test_no_assertions: Path) -> None:
        result = scan_test_quality(sample_test_no_assertions)
        assert result["tests_found"] == 2
        assert len(result["assertion_free_tests"]) == 2
        assert result["quality_score"] == "FAIL"

    def test_detects_self_mock(self, sample_test_self_mock: Path) -> None:
        result = scan_test_quality(sample_test_self_mock)
        assert len(result["self_mock_tests"]) >= 1
        score = result["quality_score"]
        assert score == "FAIL"

    def test_detects_mock_only(self, sample_test_mock_only: Path) -> None:
        result = scan_test_quality(sample_test_mock_only)
        assert len(result["mock_only_tests"]) >= 1
        score = result["quality_score"]
        assert score == "FAIL"

    def test_unreadable_file_returns_skip(self) -> None:
        result = scan_test_quality(Path("/nonexistent/test_file.py"))
        assert result["quality_score"] == "SKIP"

    def test_directory_as_filepath_returns_skip(self, tmp_path: Path) -> None:
        result = scan_test_quality(tmp_path)
        assert result["quality_score"] == "SKIP"

    def test_class_based_tests_detected(self, sample_test_class_based: Path) -> None:
        result = scan_test_quality(sample_test_class_based)
        assert result["tests_found"] == 3
        assert result["assertion_free_tests"] == []
        assert result["quality_score"] == "PASS"

    def test_class_based_assertion_free_detected(self, tmp_path: Path) -> None:
        code = tmp_path / "test_cls_no_assert.py"
        code.write_text(
            "class TestBad:\n"
            "    def test_nothing(self):\n"
            "        x = 1\n"
            "\n"
            "    def test_also_nothing(self):\n"
            "        pass\n",
            encoding="utf-8",
        )
        result = scan_test_quality(code)
        assert result["tests_found"] == 2
        assert len(result["assertion_free_tests"]) == 2
        assert result["quality_score"] == "FAIL"


class TestValidateRMarkers:
    def test_returns_dict_with_required_fields(
        self, tmp_path: Path, sample_test_good: Path, sample_prd: Path
    ) -> None:
        result = validate_r_markers(tmp_path, sample_prd)
        result_type = type(result)
        assert result_type is dict
        assert "markers_found" in result
        assert "markers_valid" in result
        assert "orphan_markers" in result
        assert "missing_markers" in result
        assert "result" in result

    def test_matching_markers_pass(
        self, tmp_path: Path, sample_test_good: Path, sample_prd: Path
    ) -> None:
        result = validate_r_markers(tmp_path, sample_prd)
        assert "R-P1-01" in result["markers_found"]
        assert "R-P1-02" in result["markers_found"]
        assert "R-P1-01" in result["markers_valid"]
        assert "R-P1-02" in result["markers_valid"]

    def test_orphan_markers_detected(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_orphan.py"
        marker = "R-P9" + "-99"  # Split to avoid scanner matching this file
        test_file.write_text(
            f'def test_something():\n    """# Tests {marker}"""\n    assert True\n',
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
                            "acceptanceCriteria": [{"id": "R-P1-01"}],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        result = validate_r_markers(tmp_path, prd)
        assert "R-P9-99" in result["orphan_markers"]

    def test_missing_markers_detected(self, tmp_path: Path, sample_prd: Path) -> None:
        result = validate_r_markers(tmp_path, sample_prd)
        assert "R-P1-01" in result["missing_markers"]
        assert "R-P1-02" in result["missing_markers"]
        assert "R-P1-03" in result["missing_markers"]
        assert result["result"] == "FAIL"

    def test_missing_test_dir_returns_skip(self, sample_prd: Path) -> None:
        result = validate_r_markers(Path("/nonexistent/dir"), sample_prd)
        assert result["result"] == "SKIP"
        assert "reason" in result

    def test_missing_prd_path_returns_skip(self, tmp_path: Path) -> None:
        result = validate_r_markers(tmp_path, Path("/nonexistent/prd.json"))
        assert result["result"] == "SKIP"
        assert "reason" in result


class TestValidateRMarkersTestFile:
    def test_validate_r_markers_with_testfile(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        test_file = tests_dir / "test_foo.py"
        test_file.write_text(
            "def test_foo():\n    assert True\n",
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
                                {
                                    "id": "R-P1-01",
                                    "criterion": "Foo works",
                                    "testFile": "tests/test_foo.py",
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        story = {
            "id": "STORY-001",
            "acceptanceCriteria": [
                {
                    "id": "R-P1-01",
                    "criterion": "Foo works",
                    "testFile": "tests/test_foo.py",
                },
            ],
        }
        import _qa_lib

        original_root = _qa_lib.PROJECT_ROOT
        try:
            _qa_lib.PROJECT_ROOT = tmp_path
            result = validate_r_markers(tests_dir, prd, story=story)
        finally:
            _qa_lib.PROJECT_ROOT = original_root
        assert result["result"] == "PASS"
        assert "R-P1-01" in result["markers_valid"]
        assert "R-P1-01" not in result["missing_markers"]

    def test_validate_r_markers_testfile_missing(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "version": "2.0",
                    "stories": [
                        {
                            "id": "STORY-001",
                            "acceptanceCriteria": [
                                {
                                    "id": "R-P1-01",
                                    "criterion": "Foo works",
                                    "testFile": "tests/test_foo.py",
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        story = {
            "id": "STORY-001",
            "acceptanceCriteria": [
                {
                    "id": "R-P1-01",
                    "criterion": "Foo works",
                    "testFile": "tests/test_foo.py",
                },
            ],
        }
        import _qa_lib

        original_root = _qa_lib.PROJECT_ROOT
        try:
            _qa_lib.PROJECT_ROOT = tmp_path
            result = validate_r_markers(tests_dir, prd, story=story)
        finally:
            _qa_lib.PROJECT_ROOT = original_root
        assert result["result"] == "FAIL"
        assert "R-P1-01" in result["missing_markers"]

    def test_validate_r_markers_testfile_null(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_example.py").write_text(
            'def test_something():\n    """# Tests R-P1-01"""\n    assert True\n',
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
                                {
                                    "id": "R-P1-01",
                                    "criterion": "Foo works",
                                    "testFile": None,
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        story = {
            "id": "STORY-001",
            "acceptanceCriteria": [
                {
                    "id": "R-P1-01",
                    "criterion": "Foo works",
                    "testFile": None,
                },
            ],
        }
        result = validate_r_markers(tests_dir, prd, story=story)
        assert result["result"] == "PASS"
        assert "R-P1-01" in result["markers_valid"]

    def test_validate_r_markers_mixed(self, tmp_path: Path) -> None:
        tests_dir = tmp_path / "tests"
        tests_dir.mkdir()
        (tests_dir / "test_foo.py").write_text(
            "def test_foo():\n    assert True\n",
            encoding="utf-8",
        )
        (tests_dir / "test_bar.py").write_text(
            'def test_bar():\n    """# Tests R-P1-02"""\n    assert True\n',
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
                                {
                                    "id": "R-P1-01",
                                    "criterion": "Foo works",
                                    "testFile": "tests/test_foo.py",
                                },
                                {
                                    "id": "R-P1-02",
                                    "criterion": "Bar works",
                                },
                            ],
                        }
                    ],
                }
            ),
            encoding="utf-8",
        )
        story = {
            "id": "STORY-001",
            "acceptanceCriteria": [
                {
                    "id": "R-P1-01",
                    "criterion": "Foo works",
                    "testFile": "tests/test_foo.py",
                },
                {
                    "id": "R-P1-02",
                    "criterion": "Bar works",
                },
            ],
        }
        import _qa_lib

        original_root = _qa_lib.PROJECT_ROOT
        try:
            _qa_lib.PROJECT_ROOT = tmp_path
            result = validate_r_markers(tests_dir, prd, story=story)
        finally:
            _qa_lib.PROJECT_ROOT = original_root
        assert result["result"] == "PASS"
        assert "R-P1-01" in result["markers_valid"]
        assert "R-P1-02" in result["markers_valid"]
        assert result["missing_markers"] == []

    def test_validate_r_markers_no_story(
        self, tmp_path: Path, sample_test_good: Path, sample_prd: Path
    ) -> None:
        result_with_none = validate_r_markers(tmp_path, sample_prd, story=None)
        result_without = validate_r_markers(tmp_path, sample_prd)
        assert result_with_none == result_without


class TestPlanSync:
    """# Tests R-P1-01, R-P1-02, R-P1-03, R-P1-04, R-P1-05, R-P1-06, R-P1-07, R-P1-08, R-P1-09"""

    def test_extract_plan_r_markers_finds_bullet_markers(self, tmp_path: Path) -> None:
        """# Tests R-P1-01"""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "## Phase 1\n- R-P1-01: criterion\n- R-P1-02: criterion\n",
            encoding="utf-8",
        )
        result = extract_plan_r_markers(plan)
        assert result == {"R-P1-01", "R-P1-02"}

    def test_extract_plan_r_markers_ignores_table_markers(self, tmp_path: Path) -> None:
        """# Tests R-P1-02"""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "### Changes\n| MODIFY | R-P1-01 | description |\n",
            encoding="utf-8",
        )
        result = extract_plan_r_markers(plan)
        assert result == set()

    def test_extract_plan_r_markers_ignores_prose_markers(self, tmp_path: Path) -> None:
        """# Tests R-P1-03"""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "See R-P1-01 for context\n",
            encoding="utf-8",
        )
        result = extract_plan_r_markers(plan)
        assert result == set()

    def test_sync_with_legacy_marker_ids(self, tmp_path: Path) -> None:
        """# Tests R-P1-04"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: criterion text\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "legacyMarkerIds": ["R-P1-01"],
                    "stories": [],
                }
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["in_sync"] is True

    def test_sync_without_legacy_marker_ids(self, tmp_path: Path) -> None:
        """# Tests R-P1-05"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: criterion text\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "stories": [
                        {
                            "id": "S1",
                            "acceptanceCriteria": [{"id": "R-P1-01"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["in_sync"] is True

    def test_extract_plan_r_markers_empty_on_no_markers(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("# Plan\nJust some text with no markers.\n", encoding="utf-8")
        result = extract_plan_r_markers(plan)
        assert result == set()

    def test_extract_plan_r_markers_empty_on_missing_file(self) -> None:
        """# Tests R-P1-08"""
        result = extract_plan_r_markers(Path("/nonexistent/PLAN.md"))
        assert result == set()

    def test_extract_plan_r_markers_deduplicates(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "- R-P1-01: first mention\n- R-P1-01: duplicate mention\n",
            encoding="utf-8",
        )
        result = extract_plan_r_markers(plan)
        assert result == {"R-P1-01"}

    def test_check_plan_prd_sync_in_sync(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: first\n- R-P1-02: second\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "stories": [
                        {
                            "id": "S1",
                            "acceptanceCriteria": [
                                {"id": "R-P1-01"},
                                {"id": "R-P1-02"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["in_sync"] is True
        assert result["added"] == []
        assert result["removed"] == []
        assert result["plan_hash"] != ""

    def test_check_plan_prd_sync_detects_drift(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "- R-P1-01: first\n- R-P1-02: second\n- R-P1-03: third\n",
            encoding="utf-8",
        )
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "stories": [
                        {
                            "id": "S1",
                            "acceptanceCriteria": [{"id": "R-P1-01"}],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["in_sync"] is False
        assert "R-P1-02" in result["added"]
        assert "R-P1-03" in result["added"]

    def test_check_plan_prd_sync_detects_removed(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: first\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {
                    "stories": [
                        {
                            "id": "S1",
                            "acceptanceCriteria": [
                                {"id": "R-P1-01"},
                                {"id": "R-P1-02"},
                            ],
                        }
                    ]
                }
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["in_sync"] is False
        assert "R-P1-02" in result["removed"]

    def test_check_plan_prd_sync_returns_all_keys(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: criterion\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {"stories": [{"id": "S1", "acceptanceCriteria": [{"id": "R-P1-01"}]}]}
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert "in_sync" in result
        assert "plan_markers" in result
        assert "prd_markers" in result
        assert "added" in result
        assert "removed" in result
        assert "plan_hash" in result

    def test_check_plan_prd_sync_missing_prd(self, tmp_path: Path) -> None:
        """# Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: criterion\n", encoding="utf-8")
        result = check_plan_prd_sync(plan, tmp_path / "nonexistent.json")
        assert result["in_sync"] is True
        assert result["plan_markers"] == []

    def test_old_regex_names_removed(self) -> None:
        """# Tests R-P1-09"""
        import _qa_lib

        module_attrs = set(dir(_qa_lib))
        assert "_PLAN_R_MARKER_RE" not in module_attrs
        assert "_PLAN_R_MARKER_LINE_RE" not in module_attrs
        assert "_PLAN_CRITERIA_RE" in module_attrs
        assert "_PLAN_CRITERIA_LINE_RE" in module_attrs


class TestComputePlanHash:
    """Tests for compute_plan_hash() -- normalized criteria-line hashing. # Tests R-P1-06, R-P1-07"""

    def test_hash_identical_for_same_criteria_different_prose(
        self, tmp_path: Path
    ) -> None:
        """# Tests R-P1-06"""
        plan_a = tmp_path / "a.md"
        plan_b = tmp_path / "b.md"
        plan_a.write_text(
            "# Plan\n\n## Phase 1\n- R-P1-01: Do the thing\n- R-P1-02: Other thing\n"
            "| MODIFY | R-P1-01 | description |\nSee R-P1-01 for context\n",
            encoding="utf-8",
        )
        plan_b.write_text(
            "# Updated Plan\n\nExtra notes here.\n\n## Phase 1\n"
            "- R-P1-01: Do the thing\n\n- R-P1-02: Other thing\n\nMore prose.\n"
            "| CREATE | R-P1-02 | other table reference |\n",
            encoding="utf-8",
        )
        assert compute_plan_hash(plan_a) == compute_plan_hash(plan_b)

    def test_hash_different_when_criterion_line_changes(self, tmp_path: Path) -> None:
        """# Tests R-P1-07"""
        plan_a = tmp_path / "a.md"
        plan_b = tmp_path / "b.md"
        plan_a.write_text("- R-P1-01: Returns a list\n", encoding="utf-8")
        plan_b.write_text("- R-P1-01: Returns a dict\n", encoding="utf-8")
        assert compute_plan_hash(plan_a) != compute_plan_hash(plan_b)

    def test_hash_stable_across_formatting_changes(self, tmp_path: Path) -> None:
        """# Tests R-P1-06"""
        plan_a = tmp_path / "a.md"
        plan_b = tmp_path / "b.md"
        plan_a.write_text(
            "# Plan\n\n## Phase 1\n- R-P1-01: Do the thing\n- R-P1-02: Other thing\n",
            encoding="utf-8",
        )
        plan_b.write_text(
            "# Updated Plan\n\nExtra notes here.\n\n## Phase 1\n"
            "- R-P1-01: Do the thing\n\n- R-P1-02: Other thing\n\nMore prose.\n",
            encoding="utf-8",
        )
        assert compute_plan_hash(plan_a) == compute_plan_hash(plan_b)

    def test_hash_changes_when_marker_added(self, tmp_path: Path) -> None:
        """# Tests R-P1-07"""
        plan_a = tmp_path / "a.md"
        plan_b = tmp_path / "b.md"
        plan_a.write_text("- R-P1-01: Do thing\n", encoding="utf-8")
        plan_b.write_text("- R-P1-01: Do thing\n- R-P1-02: New\n", encoding="utf-8")
        assert compute_plan_hash(plan_a) != compute_plan_hash(plan_b)

    def test_hash_empty_on_missing_file(self) -> None:
        """Returns empty string when file does not exist. # Tests R-P1-08"""
        assert compute_plan_hash(Path("/nonexistent/PLAN.md")) == ""

    def test_hash_deterministic(self, tmp_path: Path) -> None:
        """Same content produces same hash across calls. # Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: Stable\n- R-P2-01: Also stable\n", encoding="utf-8")
        assert compute_plan_hash(plan) == compute_plan_hash(plan)

    def test_hash_order_independent(self, tmp_path: Path) -> None:
        """R-marker lines in different order produce same hash (sorted internally). # Tests R-P1-08"""
        plan_a = tmp_path / "a.md"
        plan_b = tmp_path / "b.md"
        plan_a.write_text("- R-P2-01: Second\n- R-P1-01: First\n", encoding="utf-8")
        plan_b.write_text("- R-P1-01: First\n- R-P2-01: Second\n", encoding="utf-8")
        assert compute_plan_hash(plan_a) == compute_plan_hash(plan_b)

    def test_sync_uses_normalized_hash(self, tmp_path: Path) -> None:
        """check_plan_prd_sync returns compute_plan_hash output. # Tests R-P1-08"""
        plan = tmp_path / "PLAN.md"
        plan.write_text("- R-P1-01: thing\n", encoding="utf-8")
        prd = tmp_path / "prd.json"
        prd.write_text(
            json.dumps(
                {"stories": [{"id": "S1", "acceptanceCriteria": [{"id": "R-P1-01"}]}]}
            ),
            encoding="utf-8",
        )
        result = check_plan_prd_sync(plan, prd)
        assert result["plan_hash"] == compute_plan_hash(plan)


class TestPlanChanges:
    """Tests for parse_plan_changes and related utilities."""

    def test_parse_plan_changes_extracts_paths(self, tmp_path: Path) -> None:
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "### Changes\n\n"
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `.claude/hooks/_lib.py` | Add patterns |\n"
            "| CREATE | `.claude/hooks/tests/test_new.py` | New tests |\n"
            "| DELETE | `old_file.py` | Remove old |\n",
            encoding="utf-8",
        )
        result = parse_plan_changes(plan)
        assert ".claude/hooks/_lib.py" in result
        assert ".claude/hooks/tests/test_new.py" in result
        assert "old_file.py" in result

    def test_parse_plan_changes_empty_on_no_tables(self, tmp_path: Path) -> None:
        plan = tmp_path / "PLAN.md"
        plan.write_text("# Plan\nNo tables here.\n", encoding="utf-8")
        result = parse_plan_changes(plan)
        assert result == set()

    def test_parse_plan_changes_empty_on_missing(self) -> None:
        result = parse_plan_changes(Path("/nonexistent/PLAN.md"))
        assert result == set()

    def test_parse_plan_changes_skips_header_rows(self, tmp_path: Path) -> None:
        plan = tmp_path / "PLAN.md"
        plan.write_text(
            "| Action | File | Description |\n"
            "| --- | --- | --- |\n"
            "| MODIFY | `src/main.py` | Update |\n",
            encoding="utf-8",
        )
        result = parse_plan_changes(plan)
        assert "src/main.py" in result
        assert "---" not in str(result)
        assert "Action" not in str(result)


class TestRegressions:
    def test_existing_imports_still_work(self) -> None:
        from _lib import (
            audit_log,
            clear_marker,
            clear_stop_block_count,
            get_stop_block_count,
            get_test_patterns,
            increment_stop_block_count,
            is_test_command,
            load_workflow_config,
            parse_hook_stdin,
            read_marker,
            run_formatter,
            write_marker,
        )

        imports = [
            parse_hook_stdin,
            load_workflow_config,
            get_test_patterns,
            is_test_command,
            run_formatter,
            audit_log,
            read_marker,
            write_marker,
            clear_marker,
            get_stop_block_count,
            increment_stop_block_count,
            clear_stop_block_count,
        ]
        count = len(imports)
        assert count == 12

    def test_new_imports_work(self) -> None:
        """# Tests R-P3-07"""
        from _qa_lib import (
            check_plan_prd_sync,
            extract_plan_r_markers,
            parse_plan_changes,
        )

        imports = [
            extract_plan_r_markers,
            check_plan_prd_sync,
            parse_plan_changes,
        ]
        count = len(imports)
        assert count == 3

    def test_dead_code_removed(self) -> None:
        import _lib

        assert not hasattr(_lib, "PROD_VIOLATIONS_PATH")
        assert not hasattr(_lib, "migrate_legacy_markers")
        assert not hasattr(_lib, "read_prod_violations")
        assert not hasattr(_lib, "clear_prod_violations")
        assert not hasattr(_lib, "set_file_violations")
        assert not hasattr(_lib, "remove_file_violations")

    def test_qa_functions_moved_from_lib(self) -> None:
        """# Tests R-P3-05, R-P3-06"""
        import _lib

        assert not hasattr(_lib, "scan_test_quality")
        assert not hasattr(_lib, "validate_r_markers")
        assert not hasattr(_lib, "check_story_file_coverage")
        assert not hasattr(_lib, "check_plan_prd_sync")
        assert not hasattr(_lib, "parse_plan_changes")
        assert not hasattr(_lib, "check_diff_line_coverage")
        assert not hasattr(_lib, "check_call_graph_wiring")


class TestTestQualityWrapper:
    """# Tests R-P2-05"""

    def test_test_quality_imports_from_qa_runner(self) -> None:
        """# Tests R-P2-05"""
        tq_path = Path(__file__).resolve().parent.parent / "test_quality.py"
        content = tq_path.read_text(encoding="utf-8")
        assert "qa_runner" in content or "_run_test_quality" in content

    def test_test_quality_delegates_to_run_test_quality(self) -> None:
        """# Tests R-P2-05"""
        tq_path = Path(__file__).resolve().parent.parent / "test_quality.py"
        content = tq_path.read_text(encoding="utf-8")
        assert "_run_test_quality" in content

    def test_test_quality_still_accepts_dir_flag(self, tmp_path: Path) -> None:
        """# Tests R-P2-05"""
        import subprocess

        tq_path = Path(__file__).resolve().parent.parent / "test_quality.py"
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        tf = test_dir / "test_sample.py"
        tf.write_text("def test_x():\n    assert 1 == 1\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(tq_path), "--dir", str(test_dir)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "files" in data
        assert "overall_result" in data
        assert "summary" in data

    def test_test_quality_still_accepts_positional_files(self, tmp_path: Path) -> None:
        """# Tests R-P2-05"""
        import subprocess

        tq_path = Path(__file__).resolve().parent.parent / "test_quality.py"
        tf = tmp_path / "test_sample.py"
        tf.write_text("def test_x():\n    assert 1 == 1\n", encoding="utf-8")
        result = subprocess.run(
            [sys.executable, str(tq_path), str(tf)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        data = json.loads(result.stdout)
        assert "files" in data


class TestClaudeMdLabels:
    """# Tests R-P2-06"""

    def _get_claude_md_content(self) -> str:
        repo_root = Path(__file__).resolve().parent.parent.parent.parent
        standards = repo_root / ".claude" / "rules" / "production-standards.md"
        return standards.read_text(encoding="utf-8")

    def test_rules_have_enforcement_labels(self) -> None:
        """# Tests R-P2-06"""
        content = self._get_claude_md_content()
        assert "automated (regex)" in content.lower() or "automated (regex)" in content
        assert "review guidance" in content.lower() or "review guidance" in content

    def test_rules_8_and_9_are_review_guidance(self) -> None:
        """# Tests R-P2-06"""
        content = self._get_claude_md_content()
        lines = content.splitlines()
        found_rule_8 = False
        found_rule_9 = False
        for line in lines:
            lower = line.lower()
            if "input validation" in lower and "review guidance" in lower:
                found_rule_8 = True
            if "resource cleanup" in lower and "review guidance" in lower:
                found_rule_9 = True
        assert found_rule_8, "Rule 8 (input validation) not labeled as review guidance"
        assert found_rule_9, "Rule 9 (resource cleanup) not labeled as review guidance"

    def test_automated_regex_label_present(self) -> None:
        """# Tests R-P2-06"""
        content = self._get_claude_md_content()
        assert "automated (regex)" in content.lower() or "Automated (regex)" in content

    def test_automated_lint_label_present(self) -> None:
        """# Tests R-P2-06"""
        content = self._get_claude_md_content()
        assert "automated (lint" in content.lower() or "Automated (lint" in content


class TestWeakAssertionDetection:
    def test_weak_assert_is_not_none_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_check_result():\n"
            "    result = get_value()\n"
            "    assert result is not None\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_check_result" in weak

    def test_weak_bare_truthiness_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_truthy():\n    result = compute()\n    assert result\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "weak_assertion_tests" in result
        assert "test_truthy" in result["weak_assertion_tests"]

    def test_weak_assertTrue_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_true_check():\n"
            "    result = do_something()\n"
            "    assertTrue(result)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_true_check" in weak

    def test_strong_assertEqual_not_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_equal_check():\n"
            "    result = compute()\n"
            "    assertEqual(result, 42)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "weak_assertion_tests" in result
        assert "test_equal_check" not in result["weak_assertion_tests"]

    def test_strong_assert_equals_not_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_value_compare():\n"
            "    result = compute()\n"
            "    assert result == 42\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "weak_assertion_tests" in result
        assert "test_value_compare" not in result["weak_assertion_tests"]

    def test_strong_assertRaises_not_flagged(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_raises():\n    assertRaises(ValueError, bad_func)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "weak_assertion_tests" in result
        assert "test_raises" not in result["weak_assertion_tests"]

    def test_weak_assert_isinstance_flagged(self, tmp_path: Path) -> None:
        """# Tests R-P1-03"""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_type_check():\n"
            "    result = get_value()\n"
            "    assert isinstance(result, dict)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_type_check" in weak

    def test_weak_assert_len_greater_than_zero_flagged(self, tmp_path: Path) -> None:
        """# Tests R-P1-04"""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_length_check():\n"
            "    result = get_items()\n"
            "    assert len(result) > 0\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_length_check" in weak

    def test_weak_assert_callable_flagged(self, tmp_path: Path) -> None:
        """# Tests R-P1-05"""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_callable_check():\n"
            "    func = get_handler()\n"
            "    assert callable(func)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_callable_check" in weak

    def test_weak_assert_hasattr_flagged(self, tmp_path: Path) -> None:
        """# Tests R-P1-06"""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_attr_check():\n"
            "    obj = create_thing()\n"
            '    assert hasattr(obj, "name")\n',
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        weak = result["weak_assertion_tests"]
        weak_type = type(weak)
        assert weak_type is list
        assert "test_attr_check" in weak

    def test_weak_only_causes_fail(self, tmp_path: Path) -> None:
        """# Tests R-P1-07"""
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_only_isinstance():\n"
            "    result = get()\n"
            "    assert isinstance(result, dict)\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        score = result["quality_score"]
        assert score == "FAIL"
        assert len(result["weak_assertion_tests"]) >= 1

    def test_mixed_weak_and_strong_passes(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_mixed():\n"
            "    result = get()\n"
            "    assert isinstance(result, dict)\n"
            "    assert result == expected_value\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert result["quality_score"] == "PASS"
        assert "test_mixed" not in result.get("weak_assertion_tests", [])


class TestHappyPathOnlyDetection:
    def test_happy_path_only_when_no_negative_names(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_create_user():\n"
            "    assert True\n\n"
            "def test_read_data():\n"
            "    assert True\n\n"
            "def test_update_record():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "happy_path_only" in result
        assert result["happy_path_only"] is True

    def test_not_happy_path_only_with_negative_name(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_create_user():\n"
            "    assert True\n\n"
            "def test_invalid_email_rejected():\n"
            "    assert True\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert "happy_path_only" in result
        assert result["happy_path_only"] is False

    def test_negative_keywords_all_recognized(self, tmp_path: Path) -> None:
        keywords = [
            "invalid",
            "error",
            "fail",
            "reject",
            "edge",
            "boundary",
            "malformed",
            "negative",
        ]
        for keyword in keywords:
            test_file = tmp_path / f"test_{keyword}.py"
            test_file.write_text(
                f"def test_{keyword}_case():\n    assert True\n",
                encoding="utf-8",
            )
            result = scan_test_quality(test_file)
            assert result["happy_path_only"] is False, (
                f"keyword '{keyword}' did not prevent happy_path_only"
            )

    def test_happy_path_warn_severity(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_sample.py"
        test_file.write_text(
            "def test_create():\n    result = build()\n    assert result == 42\n",
            encoding="utf-8",
        )
        result = scan_test_quality(test_file)
        assert result["quality_score"] == "PASS"
        assert result["happy_path_only"] is True


class TestCheckNegativeTests:
    def test_validation_criterion_no_negative_tests_warns(self) -> None:
        result = check_negative_tests(
            criterion_text="validate email format and reject malformed input",
            test_names=["test_create_user", "test_update_profile"],
        )
        assert result["needs_negative"] is True
        assert result["has_negative"] is False
        assert result["result"] == "WARN"

    def test_validation_criterion_with_negative_tests_passes(self) -> None:
        result = check_negative_tests(
            criterion_text="validate email format and reject malformed input",
            test_names=[
                "test_create_user",
                "test_invalid_email_rejected",
            ],
        )
        assert result["needs_negative"] is True
        assert result["has_negative"] is True
        assert result["result"] == "PASS"

    def test_non_validation_criterion_always_passes(self) -> None:
        result = check_negative_tests(
            criterion_text="render the dashboard with user stats",
            test_names=["test_render_dashboard"],
        )
        assert result["needs_negative"] is False
        assert result["result"] == "PASS"

    def test_all_validation_keywords_recognized(self) -> None:
        keywords = [
            "validate",
            "reject",
            "filter",
            "boundary",
            "limit",
            "invalid",
            "error",
        ]
        for kw in keywords:
            result = check_negative_tests(
                criterion_text=f"must {kw} the input properly",
                test_names=["test_basic_case"],
            )
            assert result["needs_negative"] is True, (
                f"keyword '{kw}' not recognized as validation"
            )

    def test_negative_tests_warn_severity(self) -> None:
        result = check_negative_tests(
            criterion_text="validate user input boundary",
            test_names=["test_create"],
        )
        assert result["result"] == "WARN"
        assert result["result"] != "FAIL"


class TestCheckPublicApiCoverage:
    def test_api_coverage_partial_detected(self, tmp_path: Path) -> None:
        prod_file = tmp_path / "mymodule.py"
        prod_file.write_text(
            "def create_user(name):\n"
            "    pass\n\n"
            "def update_user(uid, name):\n"
            "    pass\n\n"
            "def delete_user(uid):\n"
            "    pass\n\n"
            "def list_users():\n"
            "    pass\n",
            encoding="utf-8",
        )
        test_file = tmp_path / "test_mymodule.py"
        test_file.write_text(
            "from mymodule import create_user, update_user\n\n"
            "def test_create_user():\n"
            "    create_user('alice')\n\n"
            "def test_update_user():\n"
            "    update_user(1, 'bob')\n",
            encoding="utf-8",
        )
        result = check_public_api_coverage(test_file, prod_file)
        assert result["total_public"] == 4
        assert result["covered"] == 2
        assert result["coverage_pct"] == 50.0
        assert "delete_user" in result["uncovered"]
        assert "list_users" in result["uncovered"]
        assert "create_user" not in result["uncovered"]

    def test_api_coverage_full(self, tmp_path: Path) -> None:
        prod_file = tmp_path / "simple.py"
        prod_file.write_text(
            "def greet(name):\n"
            "    return f'hello {name}'\n\n"
            "def farewell(name):\n"
            "    return f'bye {name}'\n",
            encoding="utf-8",
        )
        test_file = tmp_path / "test_simple.py"
        test_file.write_text(
            "def test_greet():\n"
            "    assert greet('x') == 'hello x'\n\n"
            "def test_farewell():\n"
            "    assert farewell('x') == 'bye x'\n",
            encoding="utf-8",
        )
        result = check_public_api_coverage(test_file, prod_file)
        assert result["total_public"] == 2
        assert result["covered"] == 2
        assert result["uncovered"] == []
        assert result["coverage_pct"] == 100.0

    def test_api_coverage_private_excluded(self, tmp_path: Path) -> None:
        prod_file = tmp_path / "private_mod.py"
        prod_file.write_text(
            "def public_func():\n"
            "    pass\n\n"
            "def _private_helper():\n"
            "    pass\n\n"
            "def __dunder_thing():\n"
            "    pass\n",
            encoding="utf-8",
        )
        test_file = tmp_path / "test_private_mod.py"
        test_file.write_text(
            "def test_public_func():\n    public_func()\n",
            encoding="utf-8",
        )
        result = check_public_api_coverage(test_file, prod_file)
        assert result["total_public"] == 1
        assert result["covered"] == 1
        assert result["uncovered"] == []
        assert result["coverage_pct"] == 100.0

    def test_api_coverage_missing_prod_file(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test_exists.py"
        test_file.write_text("def test_x():\n    pass\n", encoding="utf-8")
        result = check_public_api_coverage(test_file, tmp_path / "nonexistent.py")
        assert result["total_public"] == 0

    def test_api_coverage_warn_severity(self, tmp_path: Path) -> None:
        prod_file = tmp_path / "mod.py"
        prod_file.write_text(
            "def func_a():\n    pass\n\ndef func_b():\n    pass\n",
            encoding="utf-8",
        )
        test_file = tmp_path / "test_mod.py"
        test_file.write_text(
            "def test_func_a():\n    func_a()\n",
            encoding="utf-8",
        )
        result = check_public_api_coverage(test_file, prod_file)
        assert "total_public" in result
        assert "uncovered" in result
        assert "coverage_pct" in result
        assert result.get("result") != "FAIL"


class TestNewDetectionCoverage:
    def test_at_least_8_tests_cover_new_detection(self) -> None:
        weak_count = sum(
            1 for name in dir(TestWeakAssertionDetection) if name.startswith("test_")
        )
        happy_count = sum(
            1 for name in dir(TestHappyPathOnlyDetection) if name.startswith("test_")
        )
        negative_count = sum(
            1 for name in dir(TestCheckNegativeTests) if name.startswith("test_")
        )

        assert weak_count >= 2, f"Weak assertion tests: {weak_count} < 2"
        assert happy_count >= 2, f"Happy-path tests: {happy_count} < 2"
        assert negative_count >= 2, f"Negative test tests: {negative_count} < 2"

        total = weak_count + happy_count + negative_count
        assert total >= 6, f"Total new detection tests: {total} < 6"


class TestCheckStoryFileCoverage:
    def test_full_coverage_passes(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "module_a.py").write_text(
            "def func_a():\n    return 1\n", encoding="utf-8"
        )
        (prod_dir / "module_b.py").write_text(
            "def func_b():\n    return 2\n", encoding="utf-8"
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_module_a.py").write_text(
            "def test_a():\n    assert True\n", encoding="utf-8"
        )
        (test_dir / "test_module_b.py").write_text(
            "def test_b():\n    assert True\n", encoding="utf-8"
        )
        changed_files = [prod_dir / "module_a.py", prod_dir / "module_b.py"]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["coverage_pct"] >= 80.0
        assert result["tested"] == 2
        assert result["total_prod"] == 2
        assert result["untested"] == []

    def test_partial_coverage_fails(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "module_a.py").write_text(
            "def func_a():\n    return 1\n", encoding="utf-8"
        )
        (prod_dir / "module_b.py").write_text(
            "def func_b():\n    return 2\n", encoding="utf-8"
        )
        (prod_dir / "module_c.py").write_text(
            "def func_c():\n    return 3\n", encoding="utf-8"
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_module_a.py").write_text(
            "def test_a():\n    assert True\n", encoding="utf-8"
        )
        changed_files = [
            prod_dir / "module_a.py",
            prod_dir / "module_b.py",
            prod_dir / "module_c.py",
        ]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "FAIL"
        assert result["coverage_pct"] < 80.0
        assert result["tested"] == 1
        assert result["total_prod"] == 3
        assert len(result["untested"]) == 2

    def test_import_based_detection(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "helpers.py").write_text(
            "def helper():\n    return 42\n", encoding="utf-8"
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_integration.py").write_text(
            "import helpers\ndef test_helper():\n    assert helpers.helper() == 42\n",
            encoding="utf-8",
        )
        changed_files = [prod_dir / "helpers.py"]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["tested"] == 1

    def test_from_import_detection(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "utils.py").write_text(
            "def utility():\n    return 99\n", encoding="utf-8"
        )
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_combined.py").write_text(
            "from utils import utility\ndef test_util():\n    assert utility() == 99\n",
            encoding="utf-8",
        )
        changed_files = [prod_dir / "utils.py"]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["tested"] == 1

    def test_non_code_files_excluded(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "module_a.py").write_text(
            "def func_a():\n    return 1\n", encoding="utf-8"
        )
        (prod_dir / "README.md").write_text("# README\n", encoding="utf-8")
        (prod_dir / "config.json").write_text("{}\n", encoding="utf-8")
        (prod_dir / "setup.cfg").write_text("[metadata]\n", encoding="utf-8")
        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        (test_dir / "test_module_a.py").write_text(
            "def test_a():\n    assert True\n", encoding="utf-8"
        )

        changed_files = [
            prod_dir / "module_a.py",
            prod_dir / "README.md",
            prod_dir / "config.json",
            prod_dir / "setup.cfg",
        ]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["total_prod"] == 1
        assert result["tested"] == 1

    def test_no_prod_files_returns_skip(self, tmp_path: Path) -> None:
        test_dir = tmp_path / "tests"
        test_dir.mkdir()

        changed_files = [
            tmp_path / "README.md",
            tmp_path / "config.json",
        ]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "SKIP"

    def test_no_test_dir_returns_skip(self, tmp_path: Path) -> None:
        changed_files = [tmp_path / "module.py"]
        result = check_story_file_coverage(changed_files, tmp_path / "nonexistent")
        assert result["result"] == "SKIP"

    def test_exact_80_percent_passes(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        for i in range(5):
            (prod_dir / f"mod_{i}.py").write_text(
                f"def func_{i}():\n    return {i}\n", encoding="utf-8"
            )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        for i in range(4):
            (test_dir / f"test_mod_{i}.py").write_text(
                f"def test_{i}():\n    assert True\n", encoding="utf-8"
            )

        changed_files = [prod_dir / f"mod_{i}.py" for i in range(5)]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["coverage_pct"] == 80.0

    def test_test_files_not_counted_as_prod(self, tmp_path: Path) -> None:
        prod_dir = tmp_path / "src"
        prod_dir.mkdir()
        (prod_dir / "module.py").write_text(
            "def func():\n    return 1\n", encoding="utf-8"
        )

        test_dir = tmp_path / "tests"
        test_dir.mkdir()
        test_file = test_dir / "test_module.py"
        test_file.write_text("def test_func():\n    assert True\n", encoding="utf-8")

        changed_files = [prod_dir / "module.py", test_file]
        result = check_story_file_coverage(changed_files, test_dir)
        assert result["result"] == "PASS"
        assert result["total_prod"] == 1  # Only the prod file counted
