# Brainstorm: State File Race Safety

**Date**: 2026-03-03
**Problem**: The unified state file `.claude/.workflow-state.json` uses an unprotected read-modify-write cycle in `update_workflow_state()`. Multiple hooks fire in rapid succession on the same tool call, creating a window for lost updates, stale reads, and Windows-specific `os.replace()` failures.

## Current Architecture

### State Access Pattern

All state mutations flow through a single code path in `_lib.py`:

```
write_marker()           --> update_workflow_state(needs_verify=...)
clear_marker()           --> update_workflow_state(needs_verify=None, stop_block_count=0)
increment_stop_block_count() --> get_stop_block_count() + update_workflow_state(stop_block_count=...)
clear_stop_block_count() --> update_workflow_state(stop_block_count=0)
```

`update_workflow_state()` itself does:

```python
state = read_workflow_state()       # 1. Read entire file
state[key] = value                  # 2. Modify in memory
write_workflow_state(state)         # 3. Write entire file (atomic replace)
```

### Hook Dispatch Model

From `.claude/settings.json`, the hooks are configured as:

| Event        | Matcher     | Hooks that fire                                                              |
| ------------ | ----------- | ---------------------------------------------------------------------------- |
| SessionStart | (all)       | `post_compact_restore.py` (reads state only)                                 |
| PreToolUse   | Bash        | `pre_bash_guard.py` (no state writes)                                        |
| PostToolUse  | Bash        | `post_bash_capture.py` (writes: `clear_marker`)                              |
| PostToolUse  | Edit\|Write | `post_format.py` (writes: `write_marker`)                                    |
|              |             | `post_write_prod_scan.py` (no state writes)                                  |
| Stop         | (all)       | `stop_verify_gate.py` (writes: `clear_marker`, `increment_stop_block_count`) |

**Key observation**: For an Edit|Write event, two hooks fire in the same matcher group:

- `post_format.py` -- calls `write_marker()` (state write)
- `post_write_prod_scan.py` -- no state writes (stateless after STORY-001 simplification)

### Who Actually Writes State?

After the STORY-001 dead code removal (commit `48257fa`), only three hooks write state:

| Hook                   | Function called                | Keys mutated                       |
| ---------------------- | ------------------------------ | ---------------------------------- |
| `post_format.py`       | `write_marker()`               | `needs_verify`                     |
| `post_bash_capture.py` | `clear_marker()`               | `needs_verify`, `stop_block_count` |
| `stop_verify_gate.py`  | `increment_stop_block_count()` | `stop_block_count`                 |
|                        | `clear_marker()`               | `needs_verify`, `stop_block_count` |

**Critical finding**: `post_write_prod_scan.py` is now stateless (its docstring confirms "Stateless: scan-and-print only, no state writes"). This means the Edit|Write PostToolUse group has only ONE state writer (`post_format.py`). The race window between hooks in the same matcher group is eliminated for state writes.

## Race Scenario Analysis

### Scenario 1: Lost Update (Same Matcher Group)

**Was**: post_format and post_write_prod_scan both writing to state file concurrently.
**Now**: Only post_format writes state in the Edit|Write group. post_write_prod_scan is stateless.
**Verdict**: Not a current risk for same-group hooks.

### Scenario 2: Lost Update (Cross-Event)

Could a rapid sequence of tool calls cause overlap?

Example: User does Edit (triggers post_format `write_marker`), then immediately runs Bash `pytest` (triggers post_bash_capture `clear_marker`).

Claude Code processes tool calls sequentially -- the model sends one tool call, hooks fire, result returns, then the model sends the next tool call. The gap between tool calls is at minimum the model's thinking time (hundreds of milliseconds). Hooks complete in <100ms. So cross-event overlap is not possible in single-agent mode.

**Sub-agent (worktree) mode**: Each sub-agent has its own `.claude/.workflow-state.json` in its own worktree directory. The worktree paths are isolated: `.claude/worktrees/agent-XXXX/.claude/.workflow-state.json`. No cross-agent contention.

**Verdict**: Not a current risk. Would only become a risk if Claude Code changed to parallel tool execution within a single agent.

### Scenario 3: Windows `os.replace()` Failure

`os.replace()` can fail with `PermissionError` on Windows if another process holds a read handle on the target file. The current code silently catches this and loses the update.

When could another process hold a read handle?

- An antivirus scanner indexing the file
- Windows Search indexer
- A user's editor with the file open

This is a real (if rare) risk. The current silent catch means the update is lost with no indication.

**Verdict**: Low probability but real. The silent failure is concerning -- at minimum we should log it.

### Scenario 4: Corrupted Read

If the file is momentarily empty during `os.replace()`, `read_workflow_state()` returns defaults. This is handled correctly -- the reader gets a valid state (just stale). Since we established that concurrent read-write between hooks is not currently possible (sequential dispatch), this is only a risk from external processes reading the file.

**Verdict**: Not a current risk for hooks. External readers (like the model reading `.workflow-state.json` directly) would see valid defaults on the rare miss.

## Option Analysis

### Option A: File Locking (msvcrt / fcntl)

**Implementation**:

```python
import sys

if sys.platform == "win32":
    import msvcrt
    def _lock(f):
        msvcrt.locking(f.fileno(), msvcrt.LK_LOCK, 1)
    def _unlock(f):
        f.seek(0)
        msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
else:
    import fcntl
    def _lock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_EX)
    def _unlock(f):
        fcntl.flock(f.fileno(), fcntl.LOCK_UN)

def update_workflow_state_locked(**kwargs) -> dict:
    lock_path = WORKFLOW_STATE_PATH.with_suffix(".json.lock")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with open(lock_path, "w") as lock_file:
        _lock(lock_file)
        try:
            state = read_workflow_state()
            for key, value in kwargs.items():
                if key == "ralph" and isinstance(value, dict):
                    ralph_section = state.get("ralph", {})
                    ralph_section.update(value)
                    state["ralph"] = ralph_section
                else:
                    state[key] = value
            write_workflow_state(state)
            return state
        finally:
            _unlock(lock_file)
```

| Criterion                 | Assessment                                                                             |
| ------------------------- | -------------------------------------------------------------------------------------- |
| Implementation complexity | Medium -- ~30 lines, but platform-specific branching                                   |
| Race prevention           | Complete -- serializes all read-modify-write cycles                                    |
| Cross-platform            | Requires dual code paths (`msvcrt` vs `fcntl`)                                         |
| Performance               | ~1-2ms overhead for lock acquisition. Well within 100ms budget                         |
| Test impact               | Moderate -- tests need to handle lock file cleanup. Lock file in tmp_path during tests |
| Changes to `_lib.py`      | Add `_lock`/`_unlock` helpers, modify `update_workflow_state()`                        |

**Pros**:

- Gold standard for preventing concurrent access
- Protects against future architectural changes (parallel hook dispatch, parallel tool execution)
- Well-understood pattern

**Cons**:

- Solves a problem that does not currently exist (hooks are sequential)
- `msvcrt.locking()` operates on byte ranges, not whole files -- need a separate lock file
- Lock file can become stale if a hook crashes mid-lock (orphaned `.json.lock`)
- On Windows, `msvcrt.LK_LOCK` blocks for up to 1 second by default before raising; need `LK_NBLCK` with retry logic or accept blocking

### Option B: Retry Loop on Write Failure

**Implementation**:

```python
def write_workflow_state(state: dict, max_retries: int = 3) -> None:
    for attempt in range(max_retries):
        try:
            WORKFLOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
            tmp_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
            os.replace(str(tmp_path), str(WORKFLOW_STATE_PATH))
            return  # Success
        except PermissionError:
            if attempt < max_retries - 1:
                import time
                time.sleep(0.01 * (attempt + 1))  # 10ms, 20ms, 30ms
            else:
                audit_log("_lib", "state_write_fail",
                          f"Failed after {max_retries} attempts")
        except (OSError, TypeError, ValueError):
            break  # Non-retryable errors
    # Clean up temp file
    try:
        cleanup = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
        if cleanup.exists():
            cleanup.unlink(missing_ok=True)
    except OSError:
        pass
```

| Criterion                 | Assessment                                                             |
| ------------------------- | ---------------------------------------------------------------------- |
| Implementation complexity | Low -- ~10 lines added to existing function                            |
| Race prevention           | Partial -- handles Windows `os.replace()` failure but not lost updates |
| Cross-platform            | No platform branching needed                                           |
| Performance               | 0ms normally, 10-60ms on retry (rare). Acceptable                      |
| Test impact               | Minimal -- existing tests still pass, add one test for retry           |
| Changes to `_lib.py`      | Modify `write_workflow_state()` only                                   |

**Pros**:

- Simplest change
- Directly addresses the one real risk (Windows `os.replace()` failure)
- No platform-specific code
- No lock files to manage

**Cons**:

- Does not prevent lost updates from concurrent read-modify-write (but we established this is not currently possible)
- Adds `time.sleep()` to a hot-path function (only on failure path, so acceptable)

### Option C: Atomic Compare-and-Swap

**Implementation**:

```python
import hashlib

def update_workflow_state_cas(**kwargs) -> dict:
    max_retries = 5
    for attempt in range(max_retries):
        raw = ""
        try:
            if WORKFLOW_STATE_PATH.exists():
                raw = WORKFLOW_STATE_PATH.read_text(encoding="utf-8")
        except OSError:
            pass

        before_hash = hashlib.sha256(raw.encode()).hexdigest()

        state = _parse_state(raw)  # Parse or return defaults
        for key, value in kwargs.items():
            if key == "ralph" and isinstance(value, dict):
                ralph_section = state.get("ralph", {})
                ralph_section.update(value)
                state["ralph"] = ralph_section
            else:
                state[key] = value

        # Verify file hasn't changed since we read it
        try:
            current_raw = WORKFLOW_STATE_PATH.read_text(encoding="utf-8") if WORKFLOW_STATE_PATH.exists() else ""
        except OSError:
            current_raw = ""

        current_hash = hashlib.sha256(current_raw.encode()).hexdigest()

        if current_hash == before_hash:
            write_workflow_state(state)
            return state
        else:
            # File changed between read and write -- retry
            audit_log("_lib", "cas_retry", f"Attempt {attempt + 1}")
            continue

    # Exhausted retries -- write anyway (best-effort)
    write_workflow_state(state)
    return state
```

| Criterion                 | Assessment                                                                        |
| ------------------------- | --------------------------------------------------------------------------------- |
| Implementation complexity | High -- ~40 lines, CAS loop with hash comparison                                  |
| Race prevention           | Good for read-modify-write races, but has TOCTOU gap between hash check and write |
| Cross-platform            | No platform-specific code                                                         |
| Performance               | Two file reads per update (read + verify). ~2ms extra I/O normally                |
| Test impact               | Significant -- need tests for retry behavior, hash mismatch                       |
| Changes to `_lib.py`      | Replace `update_workflow_state()`, add `_parse_state()` helper                    |

**Pros**:

- Detects concurrent modification (if it ever happens)
- No platform-specific code
- No lock files

**Cons**:

- TOCTOU gap: the file can change between the hash verification read and the write. This is the fundamental flaw of userspace CAS without kernel-level support
- Doubles the number of file reads (performance regression on the hot path)
- Over-engineered for a problem that does not currently exist
- hashlib import already present in `_lib.py` but adds cognitive complexity

### Option D: Single-Writer Architecture (Flag Files)

**Implementation**: Each hook writes its own flag file instead of modifying the shared state file. A reader merges them on demand.

```
.claude/
  .state-flags/
    needs_verify.flag    # Written by post_format.py
    stop_block_count     # Written by stop_verify_gate.py (contains int)
    ralph.json           # Written by ralph-worker (contains ralph sub-state)
  .workflow-state.json   # Removed or becomes read-only cache
```

```python
def write_needs_verify(content: str) -> None:
    flag = _CLAUDE_DIR / ".state-flags" / "needs_verify.flag"
    flag.parent.mkdir(parents=True, exist_ok=True)
    flag.write_text(content, encoding="utf-8")

def clear_needs_verify() -> None:
    flag = _CLAUDE_DIR / ".state-flags" / "needs_verify.flag"
    try:
        flag.unlink(missing_ok=True)
    except OSError:
        pass

def read_merged_state() -> dict:
    state = copy.deepcopy(DEFAULT_WORKFLOW_STATE)
    # Merge needs_verify
    nv_flag = _CLAUDE_DIR / ".state-flags" / "needs_verify.flag"
    if nv_flag.exists():
        state["needs_verify"] = nv_flag.read_text(encoding="utf-8").strip() or None
    # Merge stop_block_count
    sbc_flag = _CLAUDE_DIR / ".state-flags" / "stop_block_count"
    if sbc_flag.exists():
        try:
            state["stop_block_count"] = int(sbc_flag.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    # Merge ralph
    ralph_flag = _CLAUDE_DIR / ".state-flags" / "ralph.json"
    if ralph_flag.exists():
        try:
            state["ralph"] = json.loads(ralph_flag.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, ValueError):
            pass
    return state
```

| Criterion                 | Assessment                                                              |
| ------------------------- | ----------------------------------------------------------------------- |
| Implementation complexity | High -- complete rewrite of state layer, new directory structure        |
| Race prevention           | Eliminates lost updates entirely -- each writer owns its key            |
| Cross-platform            | No platform-specific code                                               |
| Performance               | Multiple file reads on read, single file write per update. Net neutral  |
| Test impact               | Major -- every state test needs rewriting for new API                   |
| Changes to `_lib.py`      | Replace all state functions. New `read_merged_state()`, per-key writers |

**Pros**:

- Eliminates the race condition by design -- no shared mutable file
- Each key is independently writable without read-modify-write
- `increment_stop_block_count()` still needs read-modify-write on its own file, but the blast radius is limited to that one counter
- Conceptually clean: the filesystem IS the state store, one file per key

**Cons**:

- Massive change to a working system for a problem that does not currently exist
- Multiple small files instead of one consolidated file -- more filesystem overhead
- Ralph state is a nested dict, so `ralph.json` still has the same read-modify-write issue internally
- Breaks the `.gitignore` pattern (currently ignores `.workflow-state.json`; would need to ignore `.state-flags/`)
- The model reads `.workflow-state.json` directly in some prompts -- would need to update those references
- Highest risk of introducing regressions

### Option E: Accept the Risk

**Implementation**: No code changes. Document the risk and add logging.

The only concrete change:

```python
def write_workflow_state(state: dict) -> None:
    try:
        WORKFLOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
        tmp_path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")
        os.replace(str(tmp_path), str(WORKFLOW_STATE_PATH))
    except (OSError, PermissionError, TypeError, ValueError) as exc:
        # Log the failure instead of silently swallowing
        audit_log("_lib", "state_write_fail", f"{type(exc).__name__}: {exc}")
        try:
            tmp_path_cleanup = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
            if tmp_path_cleanup.exists():
                tmp_path_cleanup.unlink(missing_ok=True)
        except OSError:
            pass
```

| Criterion                 | Assessment                                 |
| ------------------------- | ------------------------------------------ |
| Implementation complexity | Trivial -- one line added (audit_log call) |
| Race prevention           | None -- accepts the risk                   |
| Cross-platform            | N/A                                        |
| Performance               | Zero impact                                |
| Test impact               | None                                       |
| Changes to `_lib.py`      | Add `audit_log` call in except block       |

**Pros**:

- Zero risk of regression
- The race conditions identified in the problem statement do not occur in practice:
  - Same-group races: post_write_prod_scan is stateless (no state writes)
  - Cross-event races: Claude Code dispatches tool calls sequentially
  - Cross-agent races: worktrees isolate state files
- If a write does fail (Windows antivirus/indexer), the state self-heals: the next Edit sets `needs_verify` again, the next test pass clears it
- Follows YAGNI -- does not add complexity for a theoretical problem

**Cons**:

- Does not protect against future architecture changes
- The silent failure of `os.replace()` remains (though now logged)
- Feels like deferring a known issue

## Recommendation: Option B+E Hybrid (Retry with Logging)

**Rationale**: The analysis reveals that the scary-looking race conditions from the problem statement do not occur in the current architecture:

1. **Same-group lost update**: Eliminated by STORY-001 (post_write_prod_scan is now stateless)
2. **Cross-event lost update**: Prevented by Claude Code's sequential tool dispatch
3. **Cross-agent contention**: Prevented by worktree isolation

The only real risk is **Windows `os.replace()` failure** when an external process (antivirus, search indexer, editor) holds a read handle. This is best addressed by retry-with-backoff plus audit logging.

### Specific Code Changes

Replace the current `write_workflow_state()` in `_lib.py` (lines 152-173):

```python
def write_workflow_state(state: dict) -> None:
    """Atomically write state to .claude/.workflow-state.json.

    Uses write-to-tmp-then-replace pattern with retry on PermissionError
    (common on Windows when antivirus/indexer holds a read handle).

    Args:
        state: The full workflow state dict to persist.
    """
    WORKFLOW_STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = WORKFLOW_STATE_PATH.with_suffix(".json.tmp")
    max_retries = 3

    for attempt in range(max_retries):
        try:
            tmp_path.write_text(
                json.dumps(state, indent=2) + "\n", encoding="utf-8"
            )
            os.replace(str(tmp_path), str(WORKFLOW_STATE_PATH))
            return  # Success
        except PermissionError:
            if attempt < max_retries - 1:
                import time
                time.sleep(0.01 * (attempt + 1))  # 10ms, 20ms backoff
            else:
                audit_log(
                    "_lib",
                    "state_write_fail",
                    f"PermissionError after {max_retries} retries",
                )
        except (OSError, TypeError, ValueError) as exc:
            audit_log("_lib", "state_write_fail", f"{type(exc).__name__}: {exc}")
            break  # Non-retryable

    # Clean up temp file on failure
    try:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
    except OSError:
        pass
```

### What This Changes

1. **Retry on PermissionError**: Up to 3 attempts with 10ms/20ms backoff. Handles the Windows antivirus/indexer case.
2. **Audit logging on failure**: No longer silent. Failed writes appear in `hook_audit.jsonl` for debugging.
3. **Non-retryable errors break immediately**: TypeError/ValueError (serialization bugs) and non-permission OSError are not retried.
4. **Performance**: Zero impact on success path. 10-30ms on failure (rare). Well within 100ms hook budget.
5. **Test changes**: One new test for retry behavior. Existing tests pass unchanged.
6. **No platform branching**: `time.sleep()` and `os.replace()` are cross-platform.

### What This Does NOT Change

- No locking mechanism (not needed with sequential dispatch)
- No changes to `update_workflow_state()` or `read_workflow_state()`
- No new files or directory structure
- No changes to hook scripts
- No import additions to `_lib.py` (`time` is imported lazily in the failure path only)

### Why Not Full Locking?

File locking (Option A) would be the "proper" solution if we had concurrent writers. But we do not:

- Claude Code hooks fire sequentially within a matcher group
- Tool calls are dispatched sequentially by the model
- Sub-agents are isolated in worktrees

Adding locking would introduce:

- Platform-specific code (`msvcrt` vs `fcntl`)
- Lock file management (stale lock cleanup, timeout handling)
- Test complexity (lock cleanup in fixtures)
- A solution searching for a problem

If Claude Code ever introduces parallel hook dispatch or parallel tool execution, we should revisit this decision and add `filelock` (cross-platform library) or `msvcrt`/`fcntl` locking. That change would be additive and backward-compatible.

### Test Plan for the Change

```python
class TestWriteRetry:
    def test_retry_on_permission_error(self, tmp_path, monkeypatch):
        """write_workflow_state retries on PermissionError."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        call_count = 0
        original_replace = os.replace

        def flaky_replace(src, dst):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise PermissionError("File in use")
            return original_replace(src, dst)

        monkeypatch.setattr(os, "replace", flaky_replace)
        lib.write_workflow_state({"needs_verify": "retry-test", "stop_block_count": 0})

        state = lib.read_workflow_state()
        assert state["needs_verify"] == "retry-test"
        assert call_count == 2  # First attempt failed, second succeeded

    def test_exhausted_retries_logs_audit(self, tmp_path, monkeypatch):
        """write_workflow_state logs after exhausting retries."""
        _setup_project(tmp_path)
        lib = _get_lib(tmp_path)

        def always_fail(src, dst):
            raise PermissionError("Persistent lock")

        monkeypatch.setattr(os, "replace", always_fail)
        monkeypatch.setattr("time.sleep", lambda _: None)  # Skip delays

        lib.write_workflow_state({"needs_verify": "fail-test", "stop_block_count": 0})

        # Verify audit log was written
        audit_log = tmp_path / ".claude" / "errors" / "hook_audit.jsonl"
        assert audit_log.exists()
        content = audit_log.read_text()
        assert "state_write_fail" in content
```

## Future Considerations

If the architecture evolves to need true concurrency protection:

1. **Best option**: Use the `filelock` PyPI package (cross-platform, handles stale locks, widely used). It is a single-file dependency with no transitive dependencies.
2. **Alternative**: Move state to SQLite with WAL mode -- built-in concurrency, atomic transactions, no lock files. Overkill for current needs but would scale to any concurrency model.
3. **Architecture signal**: If we find ourselves needing locking, that is a signal that the state file should perhaps be replaced with a message-passing architecture (hooks emit events, a coordinator processes them).
