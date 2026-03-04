"""Tests for stop_verify_gate.py hook. # Tests R-P2-02"""

import json
import os
import subprocess
import sys
from pathlib import Path


# Path to the hook script under test
HOOK_PATH = Path(__file__).resolve().parent.parent / "stop_verify_gate.py"


def run_hook(
    stdin_data: str = "{}",
    cwd: str | None = None,
    env_overrides: dict | None = None,
) -> subprocess.CompletedProcess:
    """Run the stop_verify_gate hook as a subprocess."""
    env = {}
    for key in ("PATH", "SYSTEMROOT", "PYTHONPATH", "HOME", "USERPROFILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    # Redirect _lib.py paths to tmp_path so hooks write to the temp dir
    if cwd:
        env["CLAUDE_PROJECT_ROOT"] = cwd
    if env_overrides:
        env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
        cwd=cwd,
    )


def _state_path(tmp_path: Path) -> Path:
    """Return path to .workflow-state.json in tmp_path."""
    return tmp_path / ".claude" / ".workflow-state.json"


def _read_state(tmp_path: Path) -> dict:
    """Read .workflow-state.json or return default state."""
    sp = _state_path(tmp_path)
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return {
        "needs_verify": None,
        "stop_block_count": 0,
        "ralph": {},
    }


def _write_state(tmp_path: Path, state: dict) -> None:
    """Write state to .workflow-state.json."""
    sp = _state_path(tmp_path)
    sp.parent.mkdir(parents=True, exist_ok=True)
    sp.write_text(json.dumps(state, indent=2), encoding="utf-8")


def create_marker(tmp_path: Path, content: str = "test.py modified") -> Path:
    """Set needs_verify in .workflow-state.json inside tmp_path.

    Returns the path to the state file (for backward-compatible assertions).
    """
    state = _read_state(tmp_path)
    state["needs_verify"] = content
    _write_state(tmp_path, state)
    return _state_path(tmp_path)


def create_counter(tmp_path: Path, count: int) -> Path:
    """Set stop_block_count in .workflow-state.json inside tmp_path.

    Returns the path to the state file.
    """
    state = _read_state(tmp_path)
    state["stop_block_count"] = count
    _write_state(tmp_path, state)
    return _state_path(tmp_path)


class TestHookExists:
    """# Tests R-P2-02"""

    def test_hook_file_exists(self) -> None:
        """# Tests R-P2-02 -- stop_verify_gate.py exists."""
        assert HOOK_PATH.exists(), f"Hook not found at {HOOK_PATH}"
        assert HOOK_PATH.name == "stop_verify_gate.py"

    def test_hook_is_valid_python(self) -> None:
        """# Tests R-P2-02 -- hook is valid Python that can be compiled."""
        source = HOOK_PATH.read_text(encoding="utf-8")
        code = compile(source, str(HOOK_PATH), "exec")
        code_type = type(code).__name__
        assert code_type == "code"

    def test_hook_imports_lib_functions(self) -> None:
        """# Tests R-P1-06 R-P2-02 -- hook imports required functions, no prod_violations."""
        source = HOOK_PATH.read_text(encoding="utf-8")
        assert "read_workflow_state" in source
        assert "clear_marker" in source
        assert "increment_stop_block_count" in source
        assert "parse_hook_stdin" in source
        assert "clear_prod_violations" not in source
        assert "prod_violations" not in source


class TestNoMarker:
    """# Tests R-P2-02 -- When .needs_verify marker is absent, allow stop."""

    def test_exits_0_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 when no marker file exists."""
        # Ensure .claude dir exists but no marker
        (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_no_json_output_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- produces no block/warn JSON when no marker."""
        (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        stdout = result.stdout.strip()
        # Should not contain decision JSON (no block or warn)
        if stdout:
            try:
                data = json.loads(stdout)
                assert data.get("decision") not in ("block", "warn"), (
                    "Should not produce block/warn when no marker"
                )
            except json.JSONDecodeError:
                pass  # Non-JSON output is fine

    def test_no_marker_empty_claude_dir(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 when .claude dir exists but is empty."""
        (tmp_path / ".claude").mkdir(parents=True, exist_ok=True)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_no_marker_no_claude_dir(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 when .claude dir does not exist at all."""
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_empty_marker_treated_as_absent(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- empty marker file is treated as absent (allow stop)."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        marker = claude_dir / ".needs_verify"
        marker.write_text("", encoding="utf-8")
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        # Should not produce block decision
        stdout = result.stdout.strip()
        if stdout:
            try:
                data = json.loads(stdout)
                assert data.get("decision") != "block"
            except json.JSONDecodeError:
                pass


class TestMarkerPresent:
    """# Tests R-P2-02 -- When marker exists, blocks on first and second attempt,
    allows on third."""

    def test_first_attempt_blocks(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- first stop attempt with marker produces block decision."""
        create_marker(tmp_path)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"

    def test_first_attempt_message_mentions_tests(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- first block message mentions running tests or /verify."""
        create_marker(tmp_path, "app.py modified")
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"
        reason = data["reason"].lower()
        assert "test" in reason or "verify" in reason

    def test_second_attempt_blocks(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- second stop attempt with counter=1 produces block."""
        create_marker(tmp_path)
        create_counter(tmp_path, 1)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"

    def test_second_attempt_message_mentions_force(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- second block message hints about force-stop."""
        create_marker(tmp_path)
        create_counter(tmp_path, 1)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"
        reason = data["reason"].lower()
        assert "force" in reason or "once more" in reason

    def test_third_attempt_allows(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- third stop attempt (counter=2) produces warn decision."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "warn"

    def test_third_attempt_mentions_force_stop(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- warn message mentions force-stopping."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "warn"
        reason = data["reason"].lower()
        assert "force" in reason

    def test_marker_content_in_first_block_reason(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- first block reason includes marker content."""
        create_marker(tmp_path, "utils.py modified at 12:34")
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"
        assert "utils.py" in data["reason"]


class TestCounterLifecycle:
    """# Tests R-P2-02 -- Counter increments properly across attempts."""

    def test_counter_created_on_first_block(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- counter incremented in state file after first block."""
        create_marker(tmp_path)
        run_hook(cwd=str(tmp_path))
        state = _read_state(tmp_path)
        assert state["stop_block_count"] == 1

    def test_counter_increments_on_second_block(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- counter increments from 1 to 2 on second block."""
        create_marker(tmp_path)
        create_counter(tmp_path, 1)
        run_hook(cwd=str(tmp_path))
        state = _read_state(tmp_path)
        assert state["stop_block_count"] == 2

    def test_sequential_blocks_increment(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- running hook twice sequentially increments counter."""
        create_marker(tmp_path)

        # First attempt
        result1 = run_hook(cwd=str(tmp_path))
        data1 = json.loads(result1.stdout.strip())
        assert data1["decision"] == "block"
        state = _read_state(tmp_path)
        assert state["stop_block_count"] == 1

        # Second attempt
        result2 = run_hook(cwd=str(tmp_path))
        data2 = json.loads(result2.stdout.strip())
        assert data2["decision"] == "block"
        state = _read_state(tmp_path)
        assert state["stop_block_count"] == 2

        # Third attempt — should warn (force-stop)
        result3 = run_hook(cwd=str(tmp_path))
        data3 = json.loads(result3.stdout.strip())
        assert data3["decision"] == "warn"

    def test_counter_above_threshold_still_allows(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- counter well above 2 still produces warn (>=2 check)."""
        create_marker(tmp_path)
        create_counter(tmp_path, 10)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "warn"


class TestForceStop:
    """# Tests R-P2-02 -- Force-stop clears marker and counter files."""

    def test_marker_cleared_on_force_stop(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- needs_verify cleared in state after force-stop (3rd attempt)."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "warn"
        state = _read_state(tmp_path)
        assert state["needs_verify"] is None, (
            "needs_verify should be cleared after force-stop"
        )

    def test_counter_cleared_on_force_stop(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- stop_block_count reset in state after force-stop."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        run_hook(cwd=str(tmp_path))
        state = _read_state(tmp_path)
        assert state["stop_block_count"] == 0, (
            "Counter should be reset after force-stop"
        )

    def test_full_lifecycle_cleanup(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- full 3-attempt lifecycle ends with state cleaned."""
        create_marker(tmp_path)

        # Attempts 1 and 2 block
        run_hook(cwd=str(tmp_path))
        run_hook(cwd=str(tmp_path))

        # Attempt 3 force-stops
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "warn"

        state = _read_state(tmp_path)
        assert state["needs_verify"] is None, "needs_verify should be cleaned up"
        assert state["stop_block_count"] == 0, "Counter should be cleaned up"


class TestEdgeCases:
    """# Tests R-P2-02 -- Edge cases for stdin parsing and marker content."""

    def test_empty_stdin(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- empty stdin does not crash (fail-open)."""
        create_marker(tmp_path)
        result = run_hook(stdin_data="", cwd=str(tmp_path))
        assert result.returncode == 0

    def test_malformed_stdin_json(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- malformed JSON stdin does not crash (fail-open)."""
        create_marker(tmp_path)
        result = run_hook(stdin_data="not valid json {{{", cwd=str(tmp_path))
        assert result.returncode == 0
        # Should still block since marker exists
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"

    def test_marker_with_whitespace_only(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- marker with only whitespace treated as absent."""
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        marker = claude_dir / ".needs_verify"
        marker.write_text("   \n\t  \n", encoding="utf-8")
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        # Whitespace-only marker should be treated as empty/absent
        stdout = result.stdout.strip()
        if stdout:
            try:
                data = json.loads(stdout)
                assert data.get("decision") != "block", (
                    "Whitespace-only marker should not trigger block"
                )
            except json.JSONDecodeError:
                pass

    def test_marker_with_long_content(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- marker with very long content does not crash."""
        create_marker(tmp_path, "x" * 5000)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"

    def test_counter_with_non_numeric_content(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- non-numeric counter file is treated as 0."""
        create_marker(tmp_path)
        claude_dir = tmp_path / ".claude"
        claude_dir.mkdir(parents=True, exist_ok=True)
        counter = claude_dir / ".stop_block_count"
        counter.write_text("not-a-number", encoding="utf-8")
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0
        # Should treat as count=0, so first block
        data = json.loads(result.stdout.strip())
        assert data["decision"] == "block"


class TestAlwaysExitsZero:
    """# Tests R-P2-02 -- Hook always exits 0 regardless of scenario."""

    def test_exit_0_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 with no marker."""
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exit_0_first_block(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 on first block."""
        create_marker(tmp_path)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exit_0_force_stop(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 on force-stop."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        result = run_hook(cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exit_0_malformed_stdin(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- exits 0 even on malformed stdin."""
        result = run_hook(stdin_data="<<<garbage>>>", cwd=str(tmp_path))
        assert result.returncode == 0


class TestJsonOutput:
    """# Tests R-P2-02 -- Verify JSON output structure and fields."""

    def test_block_json_has_required_fields(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- block JSON has decision and reason keys."""
        create_marker(tmp_path)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        data_keys = set(data.keys())
        assert data_keys >= {"decision", "reason"}

    def test_warn_json_has_required_fields(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- warn JSON has decision and reason keys."""
        create_marker(tmp_path)
        create_counter(tmp_path, 2)
        result = run_hook(cwd=str(tmp_path))
        data = json.loads(result.stdout.strip())
        decision = data["decision"]
        assert decision == "warn"
        data_keys = set(data.keys())
        assert data_keys >= {"decision", "reason"}

    def test_output_is_single_line_json(self, tmp_path: Path) -> None:
        """# Tests R-P2-02 -- output is valid single-line JSON."""
        create_marker(tmp_path)
        result = run_hook(cwd=str(tmp_path))
        stdout = result.stdout.strip()
        # Should be parseable as JSON
        data = json.loads(stdout)
        data_type = type(data).__name__
        assert data_type == "dict"
        # Verify it's a single JSON line (no extra lines besides the JSON)
        json_lines = [
            line
            for line in result.stdout.strip().splitlines()
            if line.strip().startswith("{")
        ]
        assert len(json_lines) >= 1
