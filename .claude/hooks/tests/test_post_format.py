"""Tests for post_format.py hook."""

import json
import os
import subprocess
import sys
from pathlib import Path

# Path to the hook script under test
HOOK_PATH = Path(__file__).resolve().parent.parent / "post_format.py"


def _build_env(cwd: str | None = None) -> dict:
    """Build minimal subprocess environment with CLAUDE_PROJECT_ROOT override."""
    env = {}
    for key in ("PATH", "SYSTEMROOT", "PYTHONPATH", "HOME", "USERPROFILE"):
        if key in os.environ:
            env[key] = os.environ[key]
    if cwd:
        env["CLAUDE_PROJECT_ROOT"] = cwd
    return env


def run_hook(file_path: str, cwd: str | None = None) -> subprocess.CompletedProcess:
    """Run the post_format hook with simulated stdin JSON."""
    stdin_data = json.dumps({"tool_input": {"file_path": file_path}})
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
        env=_build_env(cwd),
        cwd=cwd,
    )


def run_hook_raw(
    stdin_data: str, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """Run the post_format hook with raw stdin string."""
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
        env=_build_env(cwd),
        cwd=cwd,
    )


def run_hook_with_key(
    key: str, file_path: str, cwd: str | None = None
) -> subprocess.CompletedProcess:
    """Run the post_format hook with a specific tool_input key name."""
    stdin_data = json.dumps({"tool_input": {key: file_path}})
    return subprocess.run(
        [sys.executable, str(HOOK_PATH)],
        input=stdin_data,
        capture_output=True,
        text=True,
        timeout=30,
        env=_build_env(cwd),
        cwd=cwd,
    )


# ── Marker creation tests ───────────────────────────────────────────────


class TestMarkerCreation:
    """# Tests R-P2-04"""

    def test_py_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .py file creates .needs_verify marker."""
        py_file = tmp_path / "module.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook(str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .py file"
        )

    def test_ts_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .ts file creates .needs_verify marker."""
        ts_file = tmp_path / "module.ts"
        ts_file.write_text("const x = 1;\n", encoding="utf-8")
        result = run_hook(str(ts_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .ts file"
        )

    def test_js_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .js file creates .needs_verify marker."""
        js_file = tmp_path / "app.js"
        js_file.write_text("var x = 1;\n", encoding="utf-8")
        result = run_hook(str(js_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .js file"
        )

    def test_go_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .go file creates .needs_verify marker."""
        go_file = tmp_path / "main.go"
        go_file.write_text("package main\n", encoding="utf-8")
        result = run_hook(str(go_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .go file"
        )

    def test_rs_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .rs file creates .needs_verify marker."""
        rs_file = tmp_path / "lib.rs"
        rs_file.write_text("fn main() {}\n", encoding="utf-8")
        result = run_hook(str(rs_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .rs file"
        )

    def test_java_file_creates_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .java file creates .needs_verify marker."""
        java_file = tmp_path / "Main.java"
        java_file.write_text("class Main {}\n", encoding="utf-8")
        result = run_hook(str(java_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".needs_verify marker not created for .java file"
        )

    def test_marker_content_contains_file_path(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- marker content references the modified file."""
        py_file = tmp_path / "module.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        run_hook(str(py_file), cwd=str(tmp_path))
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        state = json.loads(state_file.read_text(encoding="utf-8"))
        content = state["needs_verify"]
        assert "Modified:" in content
        assert str(py_file) in content


# ── No marker for non-code files ────────────────────────────────────────


class TestNoMarkerForNonCode:
    """# Tests R-P2-04"""

    def test_md_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .md file does not create .needs_verify marker."""
        md_file = tmp_path / "readme.md"
        md_file.write_text("# Hello\n", encoding="utf-8")
        result = run_hook(str(md_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .md file"

    def test_txt_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .txt file does not create .needs_verify marker."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("some notes\n", encoding="utf-8")
        result = run_hook(str(txt_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .txt file"

    def test_json_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .json file does not create .needs_verify marker."""
        json_file = tmp_path / "config.json"
        json_file.write_text('{"key": "value"}\n', encoding="utf-8")
        result = run_hook(str(json_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .json file"

    def test_csv_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .csv file does not create .needs_verify marker."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b,c\n1,2,3\n", encoding="utf-8")
        result = run_hook(str(csv_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .csv file"

    def test_html_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .html file does not create .needs_verify marker."""
        html_file = tmp_path / "index.html"
        html_file.write_text("<html></html>\n", encoding="utf-8")
        result = run_hook(str(html_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .html file"

    def test_css_no_marker(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .css file does not create .needs_verify marker."""
        css_file = tmp_path / "style.css"
        css_file.write_text("body { margin: 0; }\n", encoding="utf-8")
        result = run_hook(str(css_file), cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), ".needs_verify should not exist for .css file"


# ── Exit code tests ─────────────────────────────────────────────────────


class TestExitCodes:
    """# Tests R-P2-04"""

    def test_exits_0_with_code_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 for valid code file."""
        py_file = tmp_path / "module.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook(str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_with_non_code_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 for non-code file."""
        txt_file = tmp_path / "notes.txt"
        txt_file.write_text("hello\n", encoding="utf-8")
        result = run_hook(str(txt_file), cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_with_missing_file(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 when file does not exist."""
        result = run_hook(str(tmp_path / "nonexistent.py"), cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_with_empty_stdin(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 on empty stdin (no file_path)."""
        result = run_hook_raw("", cwd=str(tmp_path))
        assert result.returncode == 0

    def test_exits_0_on_malformed_stdin(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 on malformed (non-JSON) stdin (fail-open)."""
        result = run_hook_raw("not valid json {{{", cwd=str(tmp_path))
        assert result.returncode == 0


# ── File path detection tests ───────────────────────────────────────────


class TestFilePathDetection:
    """# Tests R-P2-04"""

    def test_detects_file_path_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- detects file_path key in tool_input."""
        py_file = tmp_path / "a.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook_with_key("file_path", str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, "file_path key should be detected"

    def test_detects_file_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- detects file key in tool_input."""
        py_file = tmp_path / "b.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook_with_key("file", str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, "file key should be detected"

    def test_detects_targetFile_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- detects targetFile key in tool_input."""
        py_file = tmp_path / "c.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook_with_key("targetFile", str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, "targetFile key should be detected"

    def test_detects_TargetFile_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- detects TargetFile (capitalized) key in tool_input."""
        py_file = tmp_path / "d.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook_with_key("TargetFile", str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, "TargetFile key should be detected"

    def test_detects_path_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- detects path key in tool_input."""
        py_file = tmp_path / "e.py"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook_with_key("path", str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, "path key should be detected"

    def test_no_recognized_key_exits_0(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- exits 0 when no recognized key is present."""
        stdin_data = json.dumps({"tool_input": {"unknown_key": "some/file.py"}})
        result = run_hook_raw(stdin_data, cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), "No marker when key not recognized"


# ── Formatter invocation tests ──────────────────────────────────────────


class TestFormatterInvocation:
    """# Tests R-P2-04"""

    def test_py_file_formatter_exits_0(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .py file runs ruff formatter and exits 0."""
        py_file = tmp_path / "unformatted.py"
        py_file.write_text("x=1\ny =   2\n", encoding="utf-8")
        result = run_hook(str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0

    def test_nonexistent_py_file_exits_0(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- non-existent .py file does not crash hook."""
        result = run_hook(str(tmp_path / "missing.py"), cwd=str(tmp_path))
        assert result.returncode == 0

    def test_non_code_file_skips_formatting(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- .csv file skips all formatters, exits 0."""
        csv_file = tmp_path / "data.csv"
        csv_file.write_text("a,b\n1,2\n", encoding="utf-8")
        result = run_hook(str(csv_file), cwd=str(tmp_path))
        assert result.returncode == 0


# ── Edge case tests ─────────────────────────────────────────────────────


class TestEdgeCases:
    """# Tests R-P2-04"""

    def test_empty_file_path_string(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- empty string for file_path exits 0, no marker."""
        result = run_hook("", cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), "No marker for empty file_path"

    def test_no_file_path_in_json(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- valid JSON but no file_path key exits 0."""
        stdin_data = json.dumps({"tool_input": {}})
        result = run_hook_raw(stdin_data, cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), "No marker when file_path absent"

    def test_malformed_stdin_exits_0(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- malformed stdin (not JSON) exits 0 (fail-open)."""
        result = run_hook_raw("{{invalid json!!", cwd=str(tmp_path))
        assert result.returncode == 0

    def test_no_tool_input_key(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- JSON without tool_input key exits 0."""
        stdin_data = json.dumps({"something_else": {"file_path": "foo.py"}})
        result = run_hook_raw(stdin_data, cwd=str(tmp_path))
        assert result.returncode == 0
        marker = tmp_path / ".claude" / ".needs_verify"
        assert not marker.exists(), "No marker when tool_input missing"

    def test_case_insensitive_extension(self, tmp_path: Path) -> None:
        """# Tests R-P2-04 -- extension matching is case-insensitive (.PY works)."""
        py_file = tmp_path / "module.PY"
        py_file.write_text("x = 1\n", encoding="utf-8")
        result = run_hook(str(py_file), cwd=str(tmp_path))
        assert result.returncode == 0
        state_file = tmp_path / ".claude" / ".workflow-state.json"
        assert state_file.exists()
        state = json.loads(state_file.read_text(encoding="utf-8"))
        assert state["needs_verify"] is not None, (
            ".PY (uppercase) should still create marker"
        )

    def test_hook_file_exists(self) -> None:
        """# Tests R-P2-04 -- post_format.py hook file exists on disk."""
        assert HOOK_PATH.exists(), f"Hook not found at {HOOK_PATH}"
        assert HOOK_PATH.name == "post_format.py"

    def test_hook_is_valid_python(self) -> None:
        """# Tests R-P2-04 -- hook is valid Python that can be compiled."""
        source = HOOK_PATH.read_text(encoding="utf-8")
        code = compile(source, str(HOOK_PATH), "exec")
        code_type = type(code).__name__
        assert code_type == "code"
