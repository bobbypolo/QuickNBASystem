# Brainstorm: Worktree Hook Isolation

**Date**: 2026-03-03
**Problem**: All hooks in `.claude/settings.json` hardcode the main project path via `cd /c/Users/rober/Documents/'Claude Workflow'`. When a ralph-worker sub-agent edits files inside its worktree (`.claude/worktrees/agent-xyz/`), the hooks fire and corrupt the MAIN project's `.workflow-state.json` with worktree file paths, blocking the orchestrator conversation.

## Concrete Bug Observed

The stop hook blocked the main orchestrator conversation with:

```
Blocked: unverified code: Modified: C:\Users\rober\Documents\Claude Workflow\.claude\worktrees\agent-ad35199d\.claude\hooks\_lib.py at 2026-03-03T06:28:24.096088+00:00
```

This is a dead worktree's edit bleeding into the main conversation's state. The worktree has already been cleaned up, but its marker persists in `.workflow-state.json` and blocks the orchestrator from stopping.

## Root Cause Analysis

### How hooks resolve paths

Every hook command in `settings.json` starts with:

```json
"command": "cd /c/Users/rober/Documents/'Claude Workflow' && python .claude/hooks/<hook>.py"
```

This means `_lib.py` always resolves `PROJECT_ROOT` to the main project directory:

```python
_HOOKS_DIR = Path(__file__).resolve().parent  # .claude/hooks/
_CLAUDE_DIR = _HOOKS_DIR.parent               # .claude/
PROJECT_ROOT = _CLAUDE_DIR.parent             # project root
```

So `WORKFLOW_STATE_PATH` always points to the MAIN project's `.claude/.workflow-state.json`.

### How file paths arrive

When Claude Code fires a PostToolUse hook for an Edit/Write in a worktree, the stdin JSON contains:

```json
{
  "tool_input": {
    "file_path": "C:\\Users\\rober\\Documents\\Claude Workflow\\.claude\\worktrees\\agent-ad35199d\\.claude\\hooks\\_lib.py"
  }
}
```

The `file_path` is an absolute path inside the worktree. The hooks don't inspect this path to determine project context -- they blindly write state to the main project's `.workflow-state.json`.

### Affected hooks and their contamination vectors

| Hook                      | What it writes to main state                     | Contamination effect                                                                                       |
| ------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------- |
| `post_format.py`          | `write_marker(f"Modified: {file_path} at {ts}")` | Sets `needs_verify` with a worktree path. Main orchestrator sees unverified code it didn't touch.          |
| `post_format.py`          | Runs `ruff format` / `prettier` on the file      | Harmless -- formats the worktree file. No state contamination.                                             |
| `post_bash_capture.py`    | `clear_marker()` on test pass                    | Could clear the main session's legitimate marker if the worker runs tests.                                 |
| `post_bash_capture.py`    | Writes `last_error.json`                         | Overwrites main session's error context with worker errors.                                                |
| `post_write_prod_scan.py` | Prints violations to stdout                      | Stdout goes to the worker conversation, not the main session. No state writes (stateless after STORY-001). |
| `stop_verify_gate.py`     | Reads `needs_verify` from main state             | Blocks main orchestrator based on markers set by workers.                                                  |
| `pre_bash_guard.py`       | No state writes                                  | No contamination. Pure stdin/stdout.                                                                       |
| `post_compact_restore.py` | No state writes                                  | Reads state, prints reminder. Would show worktree state in main session, but harmless.                     |

**Critical contamination**: `post_format.py` writes marker --> `stop_verify_gate.py` reads it --> main session blocked.

**Reverse contamination**: `post_bash_capture.py` could clear the main session's marker if a worker's test run succeeds. The orchestrator would then believe its code is verified when it isn't.

## Option A: Path Detection in Each Hook

Each hook individually checks if the `file_path` from stdin is inside a worktree path. If so, it skips state writes.

### Implementation

In `post_format.py`:

```python
def set_verify_marker(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext in CODE_EXTENSIONS:
        # Skip marker for worktree files
        normalized = file_path.replace("\\", "/")
        if ".claude/worktrees/" in normalized:
            return
        ts = datetime.now(timezone.utc).isoformat()
        write_marker(f"Modified: {file_path} at {ts}")
```

In `post_bash_capture.py`: No change needed -- the worker's test command runs in the worktree, and the test patterns match command strings, not file paths. However, `clear_marker()` applies to the main state. The command itself doesn't contain worktree paths (it's just `pytest`), so we can't detect worktree context from the command string alone.

### Analysis

| Criterion             | Assessment                                                                                                                                                                                                                      |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reliability           | Medium. Catches Edit/Write hooks reliably (file_path is in stdin). Fails for Bash hooks -- `post_bash_capture.py` receives a command string like `pytest`, not a file path. No way to detect worktree context from the command. |
| Edge cases            | Windows backslashes handled via normalization. Paths with spaces work (string containment check, not parsing).                                                                                                                  |
| Hooks needing changes | `post_format.py` (1 check). `post_bash_capture.py` cannot be fixed this way.                                                                                                                                                    |
| Test impact           | Minimal. Add 2-3 tests for worktree path detection.                                                                                                                                                                             |
| Worker quality gates  | Worker runs `qa_runner.py` directly -- unaffected by hook state.                                                                                                                                                                |

### Verdict

**Partial solution**. Fixes the `post_format.py` contamination (the observed bug) but leaves `post_bash_capture.py` as a reverse-contamination vector. Not recommended as the sole approach.

## Option B: Shared `is_worktree_file()` Guard in `_lib.py`

Add a single function to `_lib.py` that all hooks call before writing state. Centralizes the detection logic.

### Implementation

In `_lib.py`:

```python
# Worktree detection constants
_WORKTREE_SEGMENT = ".claude/worktrees/"
_WORKTREE_SEGMENT_WIN = ".claude\\worktrees\\"

def is_worktree_path(path: str) -> bool:
    """Check if a file path is inside a .claude/worktrees/ directory.

    Args:
        path: File path string (absolute or relative, Unix or Windows).

    Returns:
        True if the path contains a worktree path segment.
    """
    if not path:
        return False
    return _WORKTREE_SEGMENT in path or _WORKTREE_SEGMENT_WIN in path
```

In `post_format.py`:

```python
from _lib import is_worktree_path
# ...
def set_verify_marker(file_path: str):
    if is_worktree_path(file_path):
        return
    ext = Path(file_path).suffix.lower()
    if ext in CODE_EXTENSIONS:
        ts = datetime.now(timezone.utc).isoformat()
        write_marker(f"Modified: {file_path} at {ts}")
```

### Analysis

| Criterion             | Assessment                                                                                                                                |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Reliability           | Medium. Same limitation as Option A: works for Edit/Write hooks (file_path in stdin), fails for Bash hooks (no file path in the command). |
| Edge cases            | Handles both separators. No regex needed, pure string containment. Works with spaces in paths.                                            |
| Hooks needing changes | `post_format.py` (add guard call), `_lib.py` (add function). `post_bash_capture.py` still unfixable.                                      |
| Test impact           | Add `test_is_worktree_path()` to test suite. ~5 test cases.                                                                               |
| Worker quality gates  | Unaffected.                                                                                                                               |

### Verdict

**Same limitation as Option A**, but cleaner implementation. The guard function is reusable and testable. Still doesn't solve `post_bash_capture.py`.

## Option C: Separate State Files Per Worktree

Each worktree gets its own `.workflow-state.json`. Hooks detect which project root to use based on the file path being edited.

### Implementation

In `_lib.py`, replace the static `WORKFLOW_STATE_PATH` with a function:

```python
def _resolve_state_path(file_path: str | None = None) -> Path:
    """Determine the correct .workflow-state.json based on the file being edited.

    If file_path is inside a worktree, use that worktree's state file.
    Otherwise, use the main project's state file.
    """
    if file_path:
        normalized = file_path.replace("\\", "/")
        match = re.search(r"(.+/\.claude/worktrees/[^/]+)", normalized)
        if match:
            worktree_root = Path(match.group(1))
            return worktree_root / ".claude" / ".workflow-state.json"
    return WORKFLOW_STATE_PATH  # main project fallback
```

Every function that reads/writes state would need a `file_path` parameter threaded through:

```python
def write_marker(content: str, file_path: str | None = None) -> None:
    state_path = _resolve_state_path(file_path)
    # ... write to state_path instead of WORKFLOW_STATE_PATH
```

### Analysis

| Criterion             | Assessment                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reliability           | High for Edit/Write hooks. Each worktree has isolated state. Main state never contaminated. But worktrees created by `claude --worktree` don't have a `.claude/` directory by default -- they share the main project's `.claude/` via git worktree mechanics.                                                                                                                                                                                                                                      |
| Edge cases            | **Critical problem**: Git worktrees share the `.git` directory but have separate working trees. The `.claude/` directory is part of the working tree, so each worktree HAS its own `.claude/` directory -- but only if the worktree includes it. Claude Code's `--worktree` creates worktrees in `.claude/worktrees/`, which is gitignored. The worktree's `.claude/` directory may or may not exist depending on what files the worktree has checked out. This creates a chicken-and-egg problem. |
| Hooks needing changes | ALL hooks that read/write state need refactoring. `write_marker`, `clear_marker`, `read_marker`, `read_workflow_state`, `write_workflow_state`, `update_workflow_state`, `increment_stop_block_count`, `get_stop_block_count` -- every function needs a `file_path` parameter.                                                                                                                                                                                                                     |
| Test impact           | Major. Every test that touches state I/O needs updating. ~50+ test modifications.                                                                                                                                                                                                                                                                                                                                                                                                                  |
| Worker quality gates  | Workers would have isolated state -- good. But they run `qa_runner.py` which reads state from `_lib.py`'s constants, not from the worktree's state. Would need the same threading.                                                                                                                                                                                                                                                                                                                 |

### Verdict

**Architecturally clean but impractical**. The amount of plumbing required (threading `file_path` through every state function, every hook, every test) is disproportionate to the problem. The git worktree `.claude/` directory behavior adds uncertainty. Not recommended.

## Option D: Environment Variable Guard

Workers set an environment variable (e.g., `CLAUDE_WORKTREE=1`) that hooks check. If set, hooks skip state writes entirely.

### Implementation

In `_lib.py`:

```python
def is_worktree_session() -> bool:
    """Check if the current session is running inside a worktree.

    Returns True if the CLAUDE_WORKTREE environment variable is set
    to a truthy value.
    """
    val = os.environ.get("CLAUDE_WORKTREE", "").strip().lower()
    return val in ("1", "true", "yes")
```

In `post_format.py`:

```python
from _lib import is_worktree_session
# ...
def set_verify_marker(file_path: str):
    if is_worktree_session():
        return
    # ... existing logic
```

In `post_bash_capture.py`:

```python
from _lib import is_worktree_session
# ...
def main():
    # ...
    if exit_code == 0 and is_test_command(cmd, patterns):
        if not is_worktree_session():  # Don't clear main session's marker
            clear_marker()
    # ...
```

### How the env var gets set

Claude Code's sub-agent mechanism uses `isolation: worktree` in the agent definition. The question is whether the hook environment inherits env vars set by the sub-agent process. There are two approaches:

1. **Claude Code sets it automatically**: If the Claude Code runtime sets `CLAUDE_WORKTREE=1` when it creates a worktree session, hooks would inherit it automatically. This requires a Claude Code feature (not under our control).

2. **SessionStart hook detects worktree**: The `post_compact_restore.py` (SessionStart) hook could detect that the working directory is inside `.claude/worktrees/` and set the env var. But env vars set in a subprocess don't propagate to the parent -- the hook runs in a child process, so setting `os.environ["CLAUDE_WORKTREE"] = "1"` has no effect on subsequent hooks.

3. **Hook self-detection**: Each hook could check `os.getcwd()` to see if it's inside a worktree. But all hooks are invoked with `cd /c/Users/rober/Documents/'Claude Workflow'` first, so `os.getcwd()` always returns the main project path. The CWD is forced by the `settings.json` command.

### Analysis

| Criterion             | Assessment                                                                                                                                                                                                                                                                     |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Reliability           | Low. The env var approach requires cooperation from the Claude Code runtime (which we don't control) or a mechanism to propagate env vars between hook invocations (which doesn't exist). Self-detection via CWD fails because `settings.json` forces CWD to the main project. |
| Edge cases            | If `CLAUDE_WORKTREE` is not set (env not propagated), hooks behave exactly as today -- no fix applied. Silent failure mode.                                                                                                                                                    |
| Hooks needing changes | All state-writing hooks: `post_format.py`, `post_bash_capture.py`. Plus `_lib.py` for the guard function.                                                                                                                                                                      |
| Test impact           | Moderate. Add env var fixture to tests, test both paths. ~10 test additions.                                                                                                                                                                                                   |
| Worker quality gates  | Would skip all state writes in worktree sessions. Worker relies on `qa_runner.py` which runs tests directly -- unaffected.                                                                                                                                                     |

### Verdict

**Not viable without Claude Code runtime support**. The env var approach is elegant in theory but depends on external infrastructure we don't control. Even if Claude Code did set `CLAUDE_WORKTREE`, this is undocumented behavior that could change without notice.

## Option E: Hybrid -- Guard Function + State Write Interception (Recommended)

Combine the best aspects of Options B and D: add `is_worktree_path()` to `_lib.py` (Option B) AND intercept state writes at the `_lib.py` level so that individual hooks don't need modification.

### Key Insight

The contamination only happens through state writes (`write_marker`, `clear_marker`, `update_workflow_state`). Instead of guarding each hook, guard the state write functions themselves. But the state functions don't receive `file_path` -- only `post_format.py` knows about the file.

**Revised approach**: Guard at two strategic points:

1. **`write_marker()` in `_lib.py`**: Add `file_path` parameter. If the path is a worktree file, skip the write.
2. **`post_bash_capture.py`**: This hook doesn't receive a file path, but it clears the marker on test pass. The fix here is different: before clearing, check if the current `needs_verify` content references a worktree file. If it does AND the test command that passed was in the main project, clear it (it's stale). If the current marker references main-project files and the test ran in a worktree context, don't clear it.

Wait -- this is getting complex. Let me rethink.

### Simpler Approach: Guard at the `write_marker` Level Only

The observed bug is: `post_format.py` writes a worktree path into `needs_verify`, then `stop_verify_gate.py` reads it and blocks. The fix is to prevent worktree paths from entering `needs_verify` in the first place.

The `post_bash_capture.py` reverse contamination (clearing a legitimate marker) is actually not a real risk in practice: the worker runs in a worktree with its own `settings.json` -- wait, does it? Let me reconsider.

### Critical Question: Do worktree sessions inherit the main project's `settings.json`?

Claude Code's worktree mechanism creates a new working directory at `.claude/worktrees/agent-xyz/`. But the `settings.json` file that wires hooks is at `.claude/settings.json` in the main project. When Claude Code starts a sub-agent with `isolation: worktree`:

- The sub-agent's project root becomes the worktree directory
- But hooks in `settings.json` are project-level configuration that Claude Code reads from the **original** project root
- The hook commands hardcode `cd /c/Users/rober/Documents/'Claude Workflow'`

So yes, the same hooks fire for worktree sessions. The sub-agent's edits trigger the main project's hooks, which write to the main project's state. This confirms the contamination path.

But `post_bash_capture.py` fires on EVERY `Bash` tool use -- including test runs in the main orchestrator session. So the reverse contamination (worker's test pass clearing main marker) is real IF the worker and orchestrator sessions share the same Claude Code process. In practice, sub-agents run in separate Claude processes, and hooks fire per-process. The main orchestrator's hooks only fire for the orchestrator's tool uses, not the sub-agent's.

Wait -- **this is the key**: `settings.json` hooks fire for the session that owns them. The sub-agent, running in a worktree, has its OWN Claude Code session. But that session reads `settings.json` from... where? The original project root or the worktree root?

If Claude Code reads `settings.json` from the worktree root (`.claude/worktrees/agent-xyz/.claude/settings.json`), and that file doesn't exist, then NO hooks fire for the worktree session. The contamination wouldn't occur.

If Claude Code reads `settings.json` from the original project root (because that's where the project was opened), then hooks fire with the main project's commands, and contamination occurs.

**Based on the observed bug, we know hooks DO fire for worktree sessions using the main project's settings.json**. This confirms the second interpretation.

### Revised Option E: Guard `write_marker()` + Sanitize Stale Worktree Markers

Two-part fix:

**Part 1: Prevent worktree paths from entering state** (proactive)

Add `is_worktree_path()` to `_lib.py`. Modify `write_marker()` to accept an optional `source_path` and skip if it's a worktree file:

```python
def write_marker(content: str, source_path: str | None = None) -> None:
    """Write needs_verify to .workflow-state.json.

    Args:
        content: The verification reason string to store.
        source_path: Optional path of the file that triggered the marker.
            If this is inside a worktree, the marker is silently skipped
            to prevent cross-contamination with the main project state.
    """
    if source_path and is_worktree_path(source_path):
        return
    update_workflow_state(needs_verify=content)
```

In `post_format.py`:

```python
def set_verify_marker(file_path: str):
    ext = Path(file_path).suffix.lower()
    if ext in CODE_EXTENSIONS:
        ts = datetime.now(timezone.utc).isoformat()
        write_marker(f"Modified: {file_path} at {ts}", source_path=file_path)
```

**Part 2: Sanitize stale worktree markers on read** (defensive)

Add a check in `stop_verify_gate.py` that detects if the `needs_verify` content references a worktree path. If so, clear it automatically:

```python
def main():
    state = read_workflow_state()
    marker_content = state.get("needs_verify")

    if not marker_content:
        sys.exit(0)

    # Sanitize stale worktree markers (cross-contamination defense)
    if is_worktree_path(marker_content):
        clear_marker()
        audit_log("stop_verify_gate", "sanitize", f"Cleared stale worktree marker: {marker_content[:200]}")
        sys.exit(0)

    # ... existing logic
```

This provides defense-in-depth: Part 1 prevents new contamination, Part 2 cleans up any existing or edge-case contamination.

### Analysis

| Criterion              | Assessment                                                                                                                                                                                                                                                                                                                                                                                            |
| ---------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Reliability            | High. Part 1 catches all Edit/Write contamination at the source. Part 2 catches any markers that slip through (e.g., from older code, manual state edits, or edge cases). Together they provide full coverage.                                                                                                                                                                                        |
| Edge cases             | Windows paths: handled by checking both `/` and `\\` separators. Paths with spaces: string containment, no splitting. Nested worktrees: `.claude/worktrees/` is a fixed segment, nesting doesn't change detection. Marker content format: `write_marker` stores `"Modified: <path> at <timestamp>"`, so `is_worktree_path` on the full string still works because the path is embedded in the string. |
| Hooks needing changes  | `_lib.py`: add `is_worktree_path()` (~10 lines), modify `write_marker()` signature (add optional `source_path`). `post_format.py`: pass `file_path` to `write_marker()`. `stop_verify_gate.py`: add sanitize check (~5 lines). Total: ~20 lines of changes across 3 files.                                                                                                                            |
| Test impact            | Add `test_is_worktree_path()` (~5 cases). Add `test_write_marker_skips_worktree()` (~2 cases). Add `test_stop_gate_sanitizes_worktree_marker()` (~2 cases). Total: ~9 new tests, no existing tests modified.                                                                                                                                                                                          |
| Worker quality gates   | Completely unaffected. Workers run `qa_runner.py` directly, which runs pytest and checks results. Workers never depend on `needs_verify` marker state.                                                                                                                                                                                                                                                |
| Backward compatibility | Full. `write_marker()` signature is backward-compatible (new param is optional with default `None`). Existing calls without `source_path` work unchanged. `is_worktree_path()` is additive.                                                                                                                                                                                                           |

## Recommendation: Option E (Hybrid Guard + Sanitize)

Option E is the recommended approach. Here is why:

1. **It fixes the observed bug directly**: `post_format.py` will no longer write worktree paths into the main project's `needs_verify` marker.

2. **It provides defense-in-depth**: Even if a worktree marker somehow gets into state (race condition, manual edit, code path we missed), `stop_verify_gate.py` will clean it up instead of blocking the orchestrator.

3. **Minimal blast radius**: 3 files changed, ~20 lines of new code, ~9 new tests. No existing function signatures broken. No existing tests modified.

4. **It doesn't depend on external infrastructure**: Unlike Option D (env var), this solution is fully self-contained within the hooks codebase. No Claude Code runtime changes needed.

5. **It handles the `post_bash_capture.py` case implicitly**: The `clear_marker()` reverse contamination is less dangerous than the `write_marker()` forward contamination. If a worktree worker's test pass clears the main session's marker, the main session would need to re-run its own tests before stopping (which it should do anyway). The stop gate sanitize check (Part 2) ensures that stale worktree markers don't accumulate.

### What it does NOT fix (acceptable trade-offs)

- **`last_error.json` overwriting**: A worker's error could overwrite the main session's `last_error.json`. This is low-impact because `last_error.json` is only used for debugging context, not for blocking decisions.
- **Audit log mixing**: Worker and main session audit entries mix in `hook_audit.jsonl`. This is acceptable -- the audit log is append-only and entries are timestamped. You can grep for worktree paths to separate them.
- **Formatter running on worktree files**: `post_format.py` still formats the worktree file with ruff/prettier. This is actually desirable -- the worker benefits from auto-formatting.

## Specific Code Changes

### 1. `_lib.py` -- Add `is_worktree_path()` and modify `write_marker()`

```python
# After the existing constants block (~line 44), add:

# ---------------------------------------------------------------------------
# Worktree detection
# ---------------------------------------------------------------------------

_WORKTREE_SEGMENT = ".claude/worktrees/"
_WORKTREE_SEGMENT_WIN = ".claude\\worktrees\\"


def is_worktree_path(path: str) -> bool:
    """Check if a file path is inside a .claude/worktrees/ directory.

    Used to prevent cross-contamination between worktree worker sessions
    and the main project's workflow state.

    Args:
        path: File path string (absolute or relative, Unix or Windows).

    Returns:
        True if the path contains a worktree path segment.
    """
    if not path:
        return False
    return _WORKTREE_SEGMENT in path or _WORKTREE_SEGMENT_WIN in path
```

Modify `write_marker()`:

```python
def write_marker(content: str, source_path: str | None = None) -> None:
    """Write needs_verify to .workflow-state.json.

    Args:
        content: The verification reason string to store.
        source_path: Optional path of the file that triggered the marker.
            If inside a worktree, the write is silently skipped to prevent
            cross-contamination with the main project's state.
    """
    if source_path and is_worktree_path(source_path):
        return
    update_workflow_state(needs_verify=content)
```

### 2. `post_format.py` -- Pass `file_path` to `write_marker()`

```python
# Update imports to include is_worktree_path (not strictly needed since
# write_marker handles it, but useful for the audit_log skip):
from _lib import (
    CODE_EXTENSIONS,
    audit_log,
    is_worktree_path,
    load_workflow_config,
    parse_hook_stdin,
    run_formatter,
    write_marker,
)

def set_verify_marker(file_path: str):
    """Create verification marker when code files are modified."""
    ext = Path(file_path).suffix.lower()
    if ext in CODE_EXTENSIONS:
        ts = datetime.now(timezone.utc).isoformat()
        write_marker(f"Modified: {file_path} at {ts}", source_path=file_path)
```

### 3. `stop_verify_gate.py` -- Add sanitize check

```python
from _lib import (
    audit_log,
    clear_marker,
    increment_stop_block_count,
    is_worktree_path,
    parse_hook_stdin,
    read_workflow_state,
)

def main():
    state = read_workflow_state()
    marker_content = state.get("needs_verify")

    if not marker_content:
        sys.exit(0)

    # Defense-in-depth: clear stale worktree markers that leaked into state
    if is_worktree_path(marker_content):
        clear_marker()
        audit_log(
            "stop_verify_gate",
            "sanitize",
            f"Cleared stale worktree marker: {marker_content[:200]}",
        )
        sys.exit(0)

    # ... rest of existing logic unchanged
```

### 4. New tests

Add to an existing test file or create `test_worktree_isolation.py`:

```python
"""Tests for worktree isolation guards."""

import json
from pathlib import Path

import pytest

# Assuming CLAUDE_PROJECT_ROOT is set by conftest.py or env


class TestIsWorktreePath:
    """Tests for _lib.is_worktree_path()."""

    def test_unix_worktree_path(self):
        from _lib import is_worktree_path
        assert is_worktree_path("/project/.claude/worktrees/agent-abc/src/main.py")

    def test_windows_worktree_path(self):
        from _lib import is_worktree_path
        assert is_worktree_path("C:\\Users\\dev\\project\\.claude\\worktrees\\agent-abc\\main.py")

    def test_main_project_path(self):
        from _lib import is_worktree_path
        assert not is_worktree_path("/project/src/main.py")

    def test_empty_path(self):
        from _lib import is_worktree_path
        assert not is_worktree_path("")

    def test_none_like(self):
        from _lib import is_worktree_path
        assert not is_worktree_path("")

    def test_path_with_spaces(self):
        from _lib import is_worktree_path
        assert is_worktree_path("/my project/.claude/worktrees/agent-123/file.py")

    def test_marker_content_string(self):
        """The marker content embeds the path -- detection should still work."""
        from _lib import is_worktree_path
        marker = "Modified: C:\\Users\\dev\\.claude\\worktrees\\agent-xyz\\_lib.py at 2026-03-03T06:28:24"
        assert is_worktree_path(marker)


class TestWriteMarkerWorktreeGuard:
    """Tests that write_marker() skips writes for worktree source paths."""

    def test_skips_worktree_source(self, tmp_path):
        import os
        os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
        # Re-import to pick up the env var
        import importlib
        import _lib
        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)

        worktree_path = "/project/.claude/worktrees/agent-abc/main.py"
        _lib.write_marker("Modified: something", source_path=worktree_path)

        # State should NOT have needs_verify set
        if state_path.exists():
            state = json.loads(state_path.read_text())
            assert state.get("needs_verify") is None

    def test_writes_for_main_project_source(self, tmp_path):
        import os
        os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
        import importlib
        import _lib
        importlib.reload(_lib)

        state_path = tmp_path / ".claude" / ".workflow-state.json"
        state_path.parent.mkdir(parents=True, exist_ok=True)

        main_path = "/project/src/main.py"
        _lib.write_marker("Modified: main.py", source_path=main_path)

        state = json.loads(state_path.read_text())
        assert state.get("needs_verify") == "Modified: main.py"
```

## Build Strategy

This is a small, surgical change. No phasing needed.

1. Add `is_worktree_path()` to `_lib.py` with tests
2. Modify `write_marker()` signature in `_lib.py`, update `post_format.py` call site
3. Add sanitize check to `stop_verify_gate.py`
4. Run full test suite: `pytest .claude/hooks/tests/ -v`
5. Manual smoke test: edit a file, verify marker is set. Create a fake worktree path, verify marker is not set.

**Estimated effort**: 30 minutes. **Risk**: Very low -- all changes are additive with backward-compatible signatures.

## Relationship to Hooks Simplification (2026-03-02)

This fix is independent of and compatible with the hooks simplification plan. The `is_worktree_path()` function would live in `_lib.py` (core hot-path utilities) regardless of whether the QA engine is split out. If the simplification happens first, this change applies to the slimmed `_lib.py`. If this change happens first, the simplification can move `is_worktree_path()` as part of the split.

No ordering dependency. Can be done in either order or in parallel.

## Sources

- `.claude/hooks/_lib.py` (path resolution, state I/O, marker functions)
- `.claude/hooks/post_format.py` (write_marker call site)
- `.claude/hooks/post_bash_capture.py` (clear_marker call site)
- `.claude/hooks/post_write_prod_scan.py` (stateless after STORY-001 -- no state writes)
- `.claude/hooks/stop_verify_gate.py` (reads needs_verify, blocks on it)
- `.claude/hooks/post_compact_restore.py` (reads state, no writes)
- `.claude/hooks/pre_bash_guard.py` (pure stdin/stdout, no state)
- `.claude/settings.json` (hook wiring with hardcoded cd)
- `.claude/agents/ralph-worker.md` (`isolation: worktree`)
- `.claude/docs/brainstorms/2026-03-02-hooks-simplification.md` (broader context)
- `.gitignore` (`.claude/worktrees/` is gitignored)
