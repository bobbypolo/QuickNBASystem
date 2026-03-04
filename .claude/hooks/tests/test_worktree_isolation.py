"""Tests for worktree path isolation (Phase 1 - Hook Resilience).

Prevents worktree edits from contaminating the main project's
.workflow-state.json. Covers is_worktree_path(), write_marker()
worktree guard, and stop_verify_gate worktree sanitization.

# Tests R-P1-01, R-P1-02, R-P1-03
"""

import json
import os
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


class TestIsWorktreePath:
    """Tests for is_worktree_path() -- R-P1-01."""

    def test_unix_worktree_path_detected(self):
        """R-P1-01: Unix worktree paths are detected."""
        from _lib import is_worktree_path

        assert (
            is_worktree_path(
                "/home/user/project/.claude/worktrees/agent-abc123/file.py"
            )
            is True
        )

    def test_windows_worktree_path_detected(self):
        """R-P1-01: Windows worktree paths (backslash separators) are detected."""
        from _lib import is_worktree_path

        assert (
            is_worktree_path(
                "C:\\Users\\user\\project\\.claude\\worktrees\\agent-abc123\\file.py"
            )
            is True
        )

    def test_main_project_path_not_detected(self):
        """R-P1-01: Main project paths are not flagged as worktree paths."""
        from _lib import is_worktree_path

        assert is_worktree_path("/home/user/project/.claude/hooks/_lib.py") is False

    def test_empty_path_returns_false(self):
        """R-P1-01: Empty string returns False."""
        from _lib import is_worktree_path

        assert is_worktree_path("") is False

    def test_marker_content_string_detected(self):
        """R-P1-01: Marker content strings containing worktree paths are detected."""
        from _lib import is_worktree_path

        marker = (
            "Modified: C:\\Users\\user\\.claude\\worktrees\\agent-ad35199d"
            "\\.claude\\hooks\\_lib.py at 2026-03-03T10:00:00"
        )
        assert is_worktree_path(marker) is True


class TestWriteMarkerWorktreeGuard:
    """Tests for write_marker() worktree skip -- R-P1-02."""

    def test_write_marker_skips_worktree_source(self, tmp_path, monkeypatch):
        """R-P1-02: write_marker() silently skips when source_path is a worktree path."""
        monkeypatch.setenv("CLAUDE_PROJECT_ROOT", str(tmp_path))
        import importlib

        import _lib

        importlib.reload(_lib)

        # Ensure state file exists with clean state
        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"needs_verify": None, "stop_block_count": 0, "ralph": {}})
        )

        worktree_path = "/project/.claude/worktrees/agent-abc123/src/main.py"
        _lib.write_marker("Modified: test", source_path=worktree_path)

        # Should NOT have written the marker
        state = json.loads(state_path.read_text())
        assert state["needs_verify"] is None

    def test_write_marker_writes_for_main_source(self, tmp_path, monkeypatch):
        """R-P1-02: write_marker() writes normally when source_path is a main project path."""
        monkeypatch.setenv("CLAUDE_PROJECT_ROOT", str(tmp_path))
        import importlib

        import _lib

        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"needs_verify": None, "stop_block_count": 0, "ralph": {}})
        )

        main_path = "/project/src/main.py"
        _lib.write_marker("Modified: test", source_path=main_path)

        state = json.loads(state_path.read_text())
        assert state["needs_verify"] == "Modified: test"

    def test_write_marker_writes_when_no_source_path(self, tmp_path, monkeypatch):
        """R-P1-02: write_marker() writes normally when source_path is None (backward compat)."""
        monkeypatch.setenv("CLAUDE_PROJECT_ROOT", str(tmp_path))
        import importlib

        import _lib

        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(
            json.dumps({"needs_verify": None, "stop_block_count": 0, "ralph": {}})
        )

        _lib.write_marker("Modified: test")

        state = json.loads(state_path.read_text())
        assert state["needs_verify"] == "Modified: test"


class TestStopGateWorktreeSanitize:
    """Tests for stop_verify_gate worktree sanitization -- R-P1-03."""

    def test_stop_gate_sanitizes_worktree_marker(self, tmp_path, monkeypatch):
        """R-P1-03: stop_verify_gate clears worktree markers and allows stop."""
        monkeypatch.setenv("CLAUDE_PROJECT_ROOT", str(tmp_path))
        import importlib

        import _lib

        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        # Write a state with a worktree marker
        worktree_marker = (
            "Modified: C:\\Users\\user\\.claude\\worktrees\\agent-abc\\file.py"
            " at 2026-03-03T10:00:00"
        )
        state_path.write_text(
            json.dumps(
                {
                    "needs_verify": worktree_marker,
                    "stop_block_count": 0,
                    "ralph": {},
                }
            )
        )

        # Run the stop hook -- it should sanitize the worktree marker and exit 0 (allow)
        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent.parent / "stop_verify_gate.py"),
            ],
            input="{}",
            capture_output=True,
            text=True,
            env={**dict(os.environ), "CLAUDE_PROJECT_ROOT": str(tmp_path)},
            timeout=10,
        )
        assert result.returncode == 0

        # Verify the marker was cleared
        state = json.loads(state_path.read_text())
        assert state["needs_verify"] is None

    def test_stop_gate_blocks_real_marker(self, tmp_path, monkeypatch):
        """R-P1-03: stop_verify_gate still blocks on real (non-worktree) markers."""
        monkeypatch.setenv("CLAUDE_PROJECT_ROOT", str(tmp_path))
        import importlib

        import _lib

        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)
        real_marker = "Modified: /project/src/main.py at 2026-03-03T10:00:00"
        state_path.write_text(
            json.dumps(
                {
                    "needs_verify": real_marker,
                    "stop_block_count": 0,
                    "ralph": {},
                }
            )
        )

        import subprocess

        result = subprocess.run(
            [
                sys.executable,
                str(Path(__file__).resolve().parent.parent / "stop_verify_gate.py"),
            ],
            input="{}",
            capture_output=True,
            text=True,
            env={**dict(os.environ), "CLAUDE_PROJECT_ROOT": str(tmp_path)},
            timeout=10,
        )
        # Should still exit 0 (all hooks exit 0) but with a block decision in output
        assert result.returncode == 0
        output = json.loads(result.stdout)
        assert output["decision"] == "block"
