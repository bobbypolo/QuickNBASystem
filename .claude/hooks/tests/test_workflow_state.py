"""Tests for workflow state management (ADE workflow state — not NBA safety rails)."""

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def _setup_project(tmp_path: Path) -> Path:
    """Create minimal project root with .claude dir."""
    (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
    return tmp_path


def _get_lib(tmp_path: Path):
    """Import _lib rooted at tmp_path via CLAUDE_PROJECT_ROOT."""
    old_root = os.environ.get("CLAUDE_PROJECT_ROOT")
    os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
    try:
        if "_lib" in sys.modules:
            del sys.modules["_lib"]
        import _lib

        return _lib
    finally:
        if old_root is not None:
            os.environ["CLAUDE_PROJECT_ROOT"] = old_root
        elif "CLAUDE_PROJECT_ROOT" in os.environ:
            del os.environ["CLAUDE_PROJECT_ROOT"]


def _state_path(tmp_path: Path) -> Path:
    """Return .workflow-state.json path under tmp_path."""
    return tmp_path / ".claude" / ".workflow-state.json"


class TestWorkflowStateSchema:
    """# Tests R-P2-01 -- .workflow-state.json replaces marker files."""

    def test_default_state_has_required_keys(self, tmp_path: Path) -> None:
        """# Tests R-P1-08 R-P2-01 -- required keys present, no prod_violations."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert "needs_verify" in state
        assert "stop_block_count" in state
        assert "prod_violations" not in state
        assert "ralph" in state

    def test_default_state_needs_verify_is_none(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- default needs_verify is None."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["needs_verify"] is None

    def test_default_state_stop_block_count_is_zero(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- default stop_block_count is 0."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["stop_block_count"] == 0

    def test_default_state_ralph_has_required_keys(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- ralph section has all required keys."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        ralph = state["ralph"]
        assert ralph["consecutive_skips"] == 0
        assert ralph["stories_passed"] == 0
        assert ralph["stories_skipped"] == 0
        assert ralph["feature_branch"] == ""
        assert ralph["current_story_id"] == ""
        assert ralph["current_attempt"] == 0
        assert ralph["max_attempts"] == 4
        assert ralph["prior_failure_summary"] == ""

    def test_current_step_in_default_state(self, tmp_path: Path) -> None:
        """R-P4B-01: ralph default includes current_step."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert "current_step" in lib.DEFAULT_WORKFLOW_STATE["ralph"]
        assert lib.DEFAULT_WORKFLOW_STATE["ralph"]["current_step"] == ""

    def test_state_path_constant_exists(self, tmp_path: Path) -> None:
        """# Tests R-P2-01 -- WORKFLOW_STATE_PATH constant is defined."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        path_str = str(lib.WORKFLOW_STATE_PATH)
        assert path_str != ""
        assert path_str.endswith(".workflow-state.json")


class TestArtifactCleanup:
    """Artifact cleanup: stash_created removed, legacy path removed."""

    def test_stash_created_not_in_defaults(self, tmp_path: Path) -> None:
        """stash_created not in DEFAULT_WORKFLOW_STATE."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert "stash_created" not in lib.DEFAULT_WORKFLOW_STATE["ralph"]

    def test_legacy_ralph_state_path_not_defined(self, tmp_path: Path) -> None:
        """_LEGACY_RALPH_STATE_PATH constant is removed."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert not hasattr(lib, "_LEGACY_RALPH_STATE_PATH")

    def test_read_state_has_no_stash_created(self, tmp_path: Path) -> None:
        """ralph section has no stash_created."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert "stash_created" not in state["ralph"]


class TestWorkflowStateFunctions:
    """# Tests R-P1-01 R-P2-02 -- _lib.py exports read/write/update."""

    def test_read_workflow_state_exported(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- read_workflow_state is callable."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert lib.read_workflow_state.__name__ == "read_workflow_state"

    def test_write_workflow_state_exported(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- write_workflow_state is callable."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert lib.write_workflow_state.__name__ == "write_workflow_state"

    def test_update_workflow_state_exported(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- update_workflow_state is callable."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert lib.update_workflow_state.__name__ == "update_workflow_state"

    def test_migrate_legacy_markers_absent(self, tmp_path: Path) -> None:
        """# Tests R-P1-01 -- migrate_legacy_markers absent."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert not hasattr(lib, "migrate_legacy_markers")

    def test_read_returns_dict(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- read_workflow_state returns a dict."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert type(lib.read_workflow_state()).__name__ == "dict"

    def test_write_creates_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- write creates state file."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_workflow_state(lib.read_workflow_state())
        assert _state_path(tmp_path).exists()

    def test_write_then_read_roundtrip(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- write/read roundtrip."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        state["needs_verify"] = "test.py modified at 2026-01-01"
        state["stop_block_count"] = 2
        lib.write_workflow_state(state)
        loaded = lib.read_workflow_state()
        assert loaded["needs_verify"] == "test.py modified at 2026-01-01"
        assert loaded["stop_block_count"] == 2

    def test_update_modifies_top_level_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- update modifies top-level key."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        result = lib.update_workflow_state(needs_verify="foo.py changed")
        assert result["needs_verify"] == "foo.py changed"
        loaded = lib.read_workflow_state()
        assert loaded["needs_verify"] == "foo.py changed"

    def test_update_returns_full_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- update returns full state dict."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        result = lib.update_workflow_state(stop_block_count=5)
        assert "needs_verify" in result
        assert "ralph" in result
        assert result["stop_block_count"] == 5

    def test_update_preserves_unmodified_keys(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- update only changes specified keys."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(needs_verify="initial")
        result = lib.update_workflow_state(stop_block_count=3)
        assert result["needs_verify"] == "initial"
        assert result["stop_block_count"] == 3

    def test_update_ralph_section(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- update can modify ralph section."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        ralph_update = {
            "consecutive_skips": 1,
            "stories_passed": 3,
            "feature_branch": "ralph/test-branch",
        }
        result = lib.update_workflow_state(ralph=ralph_update)
        assert result["ralph"]["consecutive_skips"] == 1
        assert result["ralph"]["stories_passed"] == 3
        assert result["ralph"]["feature_branch"] == "ralph/test-branch"
        assert result["ralph"]["max_attempts"] == 4


class TestBackwardCompatibleMarkers:
    """# Tests R-P2-04 -- marker functions delegate to state file."""

    def test_write_marker_updates_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- write_marker stores in state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("app.py modified at 12:00")
        state = lib.read_workflow_state()
        assert state["needs_verify"] == "app.py modified at 12:00"

    def test_read_marker_reads_from_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- read_marker reads from state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(needs_verify="utils.py changed")
        assert lib.read_marker() == "utils.py changed"

    def test_read_marker_returns_none_when_empty(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- read_marker returns None when unset."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert lib.read_marker() is None

    def test_clear_marker_clears_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- clear_marker resets needs_verify and count."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(needs_verify="dirty", stop_block_count=3)
        lib.clear_marker()
        state = lib.read_workflow_state()
        assert state["needs_verify"] is None
        assert state["stop_block_count"] == 0

    def test_get_stop_block_count_reads_from_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- reads count from state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(stop_block_count=7)
        assert lib.get_stop_block_count() == 7

    def test_increment_stop_block_count_updates_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- increment updates state file."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        new_count = lib.increment_stop_block_count()
        assert new_count == 1
        state = lib.read_workflow_state()
        assert state["stop_block_count"] == 1

    def test_increment_stop_block_count_from_existing(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- increment from existing value."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(stop_block_count=5)
        assert lib.increment_stop_block_count() == 6

    def test_clear_stop_block_count_resets_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- clear resets to 0."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(stop_block_count=5)
        lib.clear_stop_block_count()
        state = lib.read_workflow_state()
        assert state["stop_block_count"] == 0

    def test_prod_violations_functions_absent(self, tmp_path: Path) -> None:
        """# Tests R-P1-03 -- prod_violations functions absent."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert not hasattr(lib, "read_prod_violations")
        assert not hasattr(lib, "clear_prod_violations")
        assert not hasattr(lib, "set_file_violations")
        assert not hasattr(lib, "remove_file_violations")

    def test_write_marker_signature_unchanged(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- write_marker accepts single string."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("content")
        assert lib.read_marker() == "content"

    def test_read_marker_signature_unchanged(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- read_marker returns str or None."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        result = lib.read_marker()
        assert result is None or isinstance(result, str)


class TestAtomicWrite:
    """write_workflow_state uses atomic write."""

    def test_tmp_file_not_left_behind(self, tmp_path: Path) -> None:
        """.workflow-state.json.tmp not left after write."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_workflow_state(lib.read_workflow_state())
        tmp_file = tmp_path / ".claude" / ".workflow-state.json.tmp"
        assert not tmp_file.exists(), "Temp file should be removed after atomic write"

    def test_state_file_created(self, tmp_path: Path) -> None:
        """.workflow-state.json created after write."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_workflow_state(lib.read_workflow_state())
        assert _state_path(tmp_path).exists()

    def test_atomic_write_is_valid_json(self, tmp_path: Path) -> None:
        """file content is valid JSON after atomic write."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        state["needs_verify"] = "test atomic"
        lib.write_workflow_state(state)
        content = _state_path(tmp_path).read_text(encoding="utf-8")
        loaded = json.loads(content)
        assert loaded["needs_verify"] == "test atomic"

    def test_sequential_writes_produce_valid_json(self, tmp_path: Path) -> None:
        """multiple sequential writes keep file valid."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        for i in range(10):
            state = lib.read_workflow_state()
            state["stop_block_count"] = i
            lib.write_workflow_state(state)

        content = _state_path(tmp_path).read_text(encoding="utf-8")
        loaded = json.loads(content)
        assert loaded["stop_block_count"] == 9

    def test_write_creates_parent_directory(self, tmp_path: Path) -> None:
        """write creates .claude dir if missing."""
        lib = _get_lib(tmp_path)  # skip _setup_project intentionally
        state = lib.read_workflow_state()
        lib.write_workflow_state(state)
        assert _state_path(tmp_path).exists()


class TestEdgeCases:
    """# Tests ADE-WF-07 -- error handling and edge cases."""

    def test_read_corrupt_json_returns_default(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- corrupt JSON returns default."""
        _setup_project(tmp_path)
        state_file = _state_path(tmp_path)
        state_file.write_text("{corrupt json here", encoding="utf-8")
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["needs_verify"] is None
        assert state["stop_block_count"] == 0

    def test_read_empty_file_returns_default(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- empty file returns default."""
        _setup_project(tmp_path)
        state_file = _state_path(tmp_path)
        state_file.write_text("", encoding="utf-8")
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["needs_verify"] is None

    def test_read_partial_state_fills_defaults(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- partial state filled with defaults."""
        _setup_project(tmp_path)
        state_file = _state_path(tmp_path)
        state_file.write_text(json.dumps({"needs_verify": "partial"}), encoding="utf-8")
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["needs_verify"] == "partial"
        assert state["stop_block_count"] == 0
        assert "ralph" in state

    def test_read_missing_ralph_section_fills_default(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- missing ralph section gets defaults."""
        _setup_project(tmp_path)
        state_file = _state_path(tmp_path)
        state_file.write_text(
            json.dumps({"needs_verify": None, "stop_block_count": 0}),
            encoding="utf-8",
        )
        lib = _get_lib(tmp_path)
        state = lib.read_workflow_state()
        assert state["ralph"]["consecutive_skips"] == 0
        assert state["ralph"]["max_attempts"] == 4

    def test_update_with_no_kwargs_is_noop(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- update with no kwargs preserves state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(needs_verify="before")
        result = lib.update_workflow_state()
        assert result["needs_verify"] == "before"

    def test_write_marker_then_read_marker_roundtrip(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- write then read marker roundtrip."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("test.py at 2026-01-01T00:00:00Z")
        assert lib.read_marker() == "test.py at 2026-01-01T00:00:00Z"

    def test_clear_marker_then_read_marker_returns_none(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- clear then read returns None."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("something")
        lib.clear_marker()
        assert lib.read_marker() is None

    def test_state_file_permissions_are_readable(self, tmp_path: Path) -> None:
        """# Tests ADE-WF-07 -- state file readable after write."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_workflow_state(lib.read_workflow_state())
        path = _state_path(tmp_path)
        assert path.exists()
        assert os.access(str(path), os.R_OK)


class TestHookIntegration:
    """# Tests R-P2-03 -- hooks work with state file."""

    def test_post_format_write_marker_uses_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- write_marker stores in state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("Modified: app.py at 2026-01-01T00:00:00Z")
        state = lib.read_workflow_state()
        assert state["needs_verify"] is not None
        assert "app.py" in state["needs_verify"]

    def test_post_bash_capture_clear_marker_uses_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- clear_marker clears state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("dirty code")
        lib.clear_marker()
        state = lib.read_workflow_state()
        assert state["needs_verify"] is None
        assert state["stop_block_count"] == 0

    def test_stop_verify_gate_reads_from_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- reads markers from state."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.update_workflow_state(needs_verify="unverified code")
        assert lib.read_marker() == "unverified code"

    def test_stop_verify_gate_counter_uses_state(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- counter uses state file."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        assert lib.get_stop_block_count() == 0
        lib.increment_stop_block_count()
        assert lib.get_stop_block_count() == 1
        lib.increment_stop_block_count()
        assert lib.get_stop_block_count() == 2

    def test_all_marker_ops_use_single_state_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-03 -- all ops use single .workflow-state.json."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)
        lib.write_marker("test.py changed")
        lib.increment_stop_block_count()
        state = lib.read_workflow_state()
        assert state["needs_verify"] == "test.py changed"
        assert state["stop_block_count"] == 1
        claude_dir = tmp_path / ".claude"
        assert not (claude_dir / ".needs_verify").exists()
        assert not (claude_dir / ".stop_block_count").exists()
        assert not (claude_dir / ".prod_violations").exists()


class TestWriteResilience:
    """Write resilience: retry on PermissionError (Phase 3)."""

    def test_retry_on_permission_error(self, tmp_path, monkeypatch):
        """R-P3-01: Retries os.replace, succeeds on 3rd attempt."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        call_count = 0
        original_replace = os.replace

        def flaky_replace(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count < 3:
                raise PermissionError("File locked by antivirus")
            return original_replace(src, dst)

        monkeypatch.setattr(os, "replace", flaky_replace)
        lib.write_workflow_state(
            {"needs_verify": None, "stop_block_count": 0, "ralph": {}}
        )

        assert call_count == 3
        assert (tmp_path / ".claude" / ".workflow-state.json").exists()

    def test_exhausted_retries_logs_audit(self, tmp_path, monkeypatch):
        """R-P3-02: Exhausted retries produce audit entry."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        def always_fail(src, dst):
            raise PermissionError("Permanently locked")

        monkeypatch.setattr(os, "replace", always_fail)

        audit_calls = []
        original_audit = lib.audit_log

        def capture_audit(hook, decision, detail):
            audit_calls.append((hook, decision, detail))
            original_audit(hook, decision, detail)

        monkeypatch.setattr(lib, "audit_log", capture_audit)

        lib.write_workflow_state(
            {"needs_verify": None, "stop_block_count": 0, "ralph": {}}
        )

        assert any(
            call[0] == "write_workflow_state" and call[1] == "retry_exhausted"
            for call in audit_calls
        )

    def test_non_retryable_error_breaks_immediately(self, tmp_path, monkeypatch):
        """R-P3-03: Non-retryable errors break immediately with audit."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        audit_calls = []
        original_audit = lib.audit_log

        def capture_audit(hook, decision, detail):
            audit_calls.append((hook, decision, detail))
            original_audit(hook, decision, detail)

        monkeypatch.setattr(lib, "audit_log", capture_audit)

        lib.write_workflow_state({"key": object()})  # unserializable triggers TypeError

        assert any(
            call[0] == "write_workflow_state" and call[1] == "write_error"
            for call in audit_calls
        )

    def test_failed_write_cleans_up_temp_file(self, tmp_path, monkeypatch):
        """R-P3-04: Failed writes clean up .json.tmp file."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        def always_fail(src, dst):
            raise PermissionError("Locked forever")

        monkeypatch.setattr(os, "replace", always_fail)
        lib.write_workflow_state(
            {"needs_verify": None, "stop_block_count": 0, "ralph": {}}
        )

        tmp_file = tmp_path / ".claude" / ".workflow-state.json.tmp"
        assert not tmp_file.exists(), "Temp file should be cleaned up after failure"
