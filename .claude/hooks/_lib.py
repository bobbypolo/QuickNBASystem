"""Shared utilities for Claude Code workflow hooks."""

import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

# Constants — paths resolved from __file__. Override via CLAUDE_PROJECT_ROOT env var.

_env_root = os.environ.get("CLAUDE_PROJECT_ROOT")
if _env_root:
    PROJECT_ROOT = Path(_env_root)
    _CLAUDE_DIR = PROJECT_ROOT / ".claude"
else:
    _HOOKS_DIR = Path(__file__).resolve().parent  # .claude/hooks/
    _CLAUDE_DIR = _HOOKS_DIR.parent  # .claude/
    PROJECT_ROOT = _CLAUDE_DIR.parent  # project root

MARKER_PATH = _CLAUDE_DIR / ".needs_verify"
STOP_COUNTER_PATH = _CLAUDE_DIR / ".stop_block_count"
AUDIT_LOG_PATH = _CLAUDE_DIR / "errors" / "hook_audit.jsonl"
ERROR_DIR = _CLAUDE_DIR / "errors"
WORKFLOW_CONFIG_PATH = _CLAUDE_DIR / "workflow.json"
WORKFLOW_STATE_PATH = _CLAUDE_DIR / ".workflow-state.json"

DEFAULT_WORKFLOW_STATE: dict = {
    "needs_verify": None,
    "stop_block_count": 0,
    "ralph": {
        "consecutive_skips": 0,
        "stories_passed": 0,
        "stories_skipped": 0,
        "feature_branch": "",
        "current_story_id": "",
        "current_attempt": 0,
        "max_attempts": 4,
        "prior_failure_summary": "",
        "current_step": "",  # tracks orchestrator position for compaction recovery
    },
}

DEFAULT_TEST_PATTERNS = [
    "pytest",
    "python -m pytest",
    "vitest",
    "jest",
    "npm test",
    "npm run test",
    "go test",
    "cargo test",
    "tox",
    "mocha",
    "rspec",
    "phpunit",
    "dotnet test",
    "mix test",
    "bundle exec rspec",
]

CODE_EXTENSIONS: frozenset[str] = frozenset(
    {
        ".py",
        ".ts",
        ".tsx",
        ".js",
        ".jsx",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".cs",
        ".php",
        ".c",
        ".cpp",
        ".h",
        ".hpp",
    }
)

AUDIT_MAX_LINES = 500
AUDIT_TRIM_TO = 250
AUDIT_SIZE_THRESHOLD = 75_000


def _deep_merge_defaults(state: dict, defaults: dict) -> dict:
    """Merge defaults into state, filling missing keys recursively."""
    result = dict(defaults)
    for key, default_val in defaults.items():
        if key in state:
            if isinstance(default_val, dict) and isinstance(state[key], dict):
                result[key] = _deep_merge_defaults(state[key], default_val)
            else:
                result[key] = state[key]
    return result


def read_workflow_state() -> dict:
    """Read .workflow-state.json, returning default state if missing or corrupt."""
    import copy

    defaults = copy.deepcopy(DEFAULT_WORKFLOW_STATE)
    try:
        if WORKFLOW_STATE_PATH.exists():
            content = WORKFLOW_STATE_PATH.read_text(encoding="utf-8").strip()
            if content:
                loaded = json.loads(content)
                if isinstance(loaded, dict):
                    return _deep_merge_defaults(loaded, defaults)
    except (json.JSONDecodeError, OSError, PermissionError, ValueError):
        pass
    return defaults


def write_workflow_state(state: dict) -> None:
    """Atomically write state. Retries 3x on PermissionError (Windows locking)."""
    import time

    tmp_path = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
    try:
        WORKFLOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

        # Retry os.replace up to 3 times on PermissionError (Windows locking)
        last_err = None
        for attempt in range(3):
            try:
                os.replace(str(tmp_path), str(WORKFLOW_STATE_PATH))
                return  # Success
            except PermissionError as exc:
                last_err = exc
                if attempt < 2:
                    time.sleep(0.01 * (attempt + 1))  # 10ms, 20ms

        # Exhausted retries
        audit_log(
            "write_workflow_state",
            "retry_exhausted",
            f"3 PermissionError retries failed: {last_err}",
        )
    except (TypeError, ValueError) as exc:
        # Non-retryable: data serialization errors
        audit_log("write_workflow_state", "write_error", f"Non-retryable: {exc}")
    except OSError as exc:
        # Non-retryable: filesystem errors other than PermissionError in replace
        audit_log(
            "write_workflow_state", "write_error", f"Non-retryable OS error: {exc}"
        )
    finally:
        # Always clean up temp file
        try:
            if tmp_path.exists():
                tmp_path.unlink(missing_ok=True)
        except OSError:
            pass


def update_workflow_state(**kwargs) -> dict:
    """Read-modify-write for workflow state. The 'ralph' key is merged, not replaced."""
    state = read_workflow_state()
    for key, value in kwargs.items():
        if key == "ralph" and isinstance(value, dict):
            # Merge ralph sub-keys instead of replacing the whole section
            ralph_section = state.get("ralph", {})
            ralph_section.update(value)
            state["ralph"] = ralph_section
        else:
            state[key] = value
    write_workflow_state(state)
    return state


def parse_hook_stdin() -> dict:
    """Parse JSON from stdin. Returns {} on any failure. Logs parse errors."""
    if sys.stdin.isatty():
        return {}

    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        audit_log("parse_hook_stdin", "parse_error", str(exc)[:300])
        return {}


def load_workflow_config() -> dict:
    """Load .claude/workflow.json with fallback defaults. Never crashes."""
    try:
        if WORKFLOW_CONFIG_PATH.exists():
            return json.loads(WORKFLOW_CONFIG_PATH.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, ValueError, OSError):
        pass
    return {}


def get_test_patterns(config: dict) -> list[str]:
    """Return test patterns from config, merged with hardcoded defaults."""
    extra = config.get("test_patterns", [])
    if not isinstance(extra, list):
        extra = []
    # Merge: defaults + user patterns, preserving order, deduped
    seen = set()
    merged = []
    for p in DEFAULT_TEST_PATTERNS + extra:
        if p not in seen:
            seen.add(p)
            merged.append(p)
    return merged


_SPLIT_RE = re.compile(r"\s*(?:&&|\|\||\||;)\s*")
_ENV_VAR_PREFIX_RE = re.compile(r"^(\w+=\S+\s+)+")


def is_test_command(cmd: str, patterns: list[str]) -> bool:
    """Split on &&/||/;/|, strip env prefixes, check if any segment starts with a pattern."""
    segments = _SPLIT_RE.split(cmd)
    for segment in segments:
        segment = segment.strip()
        # Strip leading env var assignments like PYTHONPATH=. or CI=1
        cleaned = _ENV_VAR_PREFIX_RE.sub("", segment).strip()
        for pattern in patterns:
            if cleaned.startswith(pattern):
                return True
    return False


def run_formatter(cmd, timeout: int = 30) -> tuple[int, str]:
    """Run formatter with timeout. List→shell=False, str→shell=True. Returns (rc, stderr)."""
    use_shell = isinstance(cmd, str)
    try:
        result = subprocess.run(
            cmd,
            shell=use_shell,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stderr
    except subprocess.TimeoutExpired:
        return -1, f"Formatter timed out after {timeout}s"
    except FileNotFoundError:
        return -1, f"Formatter not found: {cmd}"
    except (OSError, ValueError) as e:
        return -1, str(e)


def audit_log(hook_name: str, decision: str, detail: str):
    """Append to hook_audit.jsonl. Silent on failure. Auto-rotates by size."""
    try:
        AUDIT_LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
        entry = json.dumps(
            {
                "ts": datetime.now(timezone.utc).isoformat(),
                "hook": hook_name,
                "decision": decision,
                "detail": detail[:500],
            }
        )
        with AUDIT_LOG_PATH.open("a", encoding="utf-8") as f:
            f.write(entry + "\n")

        # Size-based rotation: only read file when it exceeds the threshold
        try:
            file_size = os.path.getsize(AUDIT_LOG_PATH)
        except OSError:
            return
        if file_size >= AUDIT_SIZE_THRESHOLD:
            lines = AUDIT_LOG_PATH.read_text(encoding="utf-8").strip().split("\n")
            if len(lines) > AUDIT_MAX_LINES:
                AUDIT_LOG_PATH.write_text(
                    "\n".join(lines[-AUDIT_TRIM_TO:]) + "\n",
                    encoding="utf-8",
                )
    except (OSError, json.JSONDecodeError, ValueError):
        pass


def read_marker() -> str | None:
    """Read needs_verify from .workflow-state.json, or None if absent/empty."""
    state = read_workflow_state()
    value = state.get("needs_verify")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def write_marker(content: str, source_path: str | None = None) -> None:
    """Write needs_verify. Skips if source_path is a worktree path."""
    if source_path is not None and is_worktree_path(source_path):
        return
    update_workflow_state(needs_verify=content)


def clear_marker() -> None:
    """Clear needs_verify and stop_block_count."""
    update_workflow_state(needs_verify=None, stop_block_count=0)


def is_worktree_path(path: str) -> bool:
    """Check if path is inside .claude/worktrees/. Handles Unix and Windows separators."""
    normalized = path.replace("\\", "/")
    return ".claude/worktrees/" in normalized


def get_stop_block_count() -> int:
    """Read stop_block_count from .workflow-state.json, return 0 if absent."""
    state = read_workflow_state()
    count = state.get("stop_block_count", 0)
    if isinstance(count, int):
        return count
    return 0


def increment_stop_block_count() -> int:
    """Increment stop_block_count and return new value."""
    count = get_stop_block_count() + 1
    update_workflow_state(stop_block_count=count)
    return count


def clear_stop_block_count() -> None:
    """Reset stop_block_count to 0."""
    update_workflow_state(stop_block_count=0)


# Re-export from _prod_patterns for backward compatibility
from _prod_patterns import PROD_VIOLATION_PATTERNS, scan_file_violations  # noqa: E402, F401
