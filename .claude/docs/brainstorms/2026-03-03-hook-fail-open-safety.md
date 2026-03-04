# Brainstorm: Hook fail_open Safety Analysis

**Date**: 2026-03-03
**Problem**: Three hooks use `fail_open=False` in `parse_hook_stdin()`, which means malformed JSON on stdin causes `sys.exit(2)` -- silently blocking the tool call. Two of these hooks are **PostToolUse** hooks where blocking is counterproductive: the tool already executed, so exit 2 doesn't undo anything, it just hides the result from the agent.

## Current State

### How `parse_hook_stdin` Works

```python
def parse_hook_stdin(fail_open: bool = False) -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        if fail_open:
            return {}
        sys.exit(2)  # BLOCKS the tool call
```

Exit code 2 in Claude Code's hook protocol means "block this action." For PreToolUse hooks, this prevents the tool from executing. For PostToolUse hooks, the tool already ran -- exit 2 prevents the agent from seeing the result.

### Hook-by-Hook Analysis

| Hook                      | Type         | fail_open | On Bad stdin                 | Correct?  |
| ------------------------- | ------------ | --------- | ---------------------------- | --------- |
| `pre_bash_guard.py`       | PreToolUse   | `False`   | exit 2 (blocks bash command) | Debatable |
| `post_bash_capture.py`    | PostToolUse  | `False`   | exit 2 (hides result)        | **Wrong** |
| `post_format.py`          | PostToolUse  | `False`   | exit 2 (hides result)        | **Wrong** |
| `post_write_prod_scan.py` | PostToolUse  | `True`    | returns {} (allows)          | Correct   |
| `stop_verify_gate.py`     | Stop         | `True`    | returns {} (allows)          | Correct   |
| `post_compact_restore.py` | SessionStart | N/A       | No stdin parsed              | N/A       |

Two of three `fail_open=False` usages are PostToolUse hooks where blocking is strictly harmful.

### The Failure Cascade

When a PostToolUse hook exits 2 due to a stdin parse failure:

1. The tool (Edit, Write, or Bash) has **already executed successfully**
2. The hook's exit code 2 tells Claude Code to treat the action as "blocked"
3. The agent sees a failure message instead of the tool's actual output
4. The agent retries the same operation, which succeeds again, but the hook blocks again
5. After enough retries, the agent gives up or exhausts its turn budget

For a ralph-worker sub-agent with 150 max turns, this is catastrophic: a single malformed stdin event can burn all remaining turns on a loop of "edit file -> blocked -> retry -> blocked." The worker returns FAIL, Ralph retries (up to 4 attempts), all fail identically, the story is skipped, and subsequent stories hit the same issue if the cause persists.

### What Could Cause Malformed stdin?

While rare, there are plausible scenarios:

- **Claude Code framework bugs**: A regression in stdin serialization
- **Encoding issues**: Non-UTF-8 characters in tool input or response (file paths with unusual characters, binary content in stdout)
- **Payload truncation**: Very large bash outputs that exceed buffer limits, resulting in truncated JSON
- **Race conditions**: If hooks are invoked in rapid succession and stdin is somehow corrupted
- **Version mismatches**: A Claude Code update changes the stdin format

The key insight is that **all of these are transient, external failures** -- none of them indicate a problem with the code being written or the command being run. Blocking the agent's tool call is a disproportionate response.

## Analysis by Hook

### 1. `post_bash_capture.py` (PostToolUse, Bash)

**What it does**: Captures failed commands to `last_error.json` and clears the verification marker when tests pass.

**What blocking accomplishes**: Nothing useful. The bash command already ran. Whether it wrote files, modified state, or produced output -- that already happened. Exit 2 just means the agent cannot see the result. It cannot undo the command.

**What goes wrong if we fail open**: The hook runs with an empty dict. `tool_input` is `{}`, so `cmd` is `""`. `tool_response` is `{}`, so `exit_code` defaults to 0. The hook exits 0 without writing an error record and without clearing the verification marker. This means:

- A failed command's error record is not captured (minor -- the error is still visible in the agent's output)
- A successful test run does not clear the verification marker (the agent or user can clear it manually, or it clears on the next successful test run where stdin is well-formed)

**Verdict**: fail_open=True is clearly correct. The worst case is a missed error capture or a missed marker-clear, both of which are self-correcting on the next well-formed invocation.

### 2. `post_format.py` (PostToolUse, Edit|Write)

**What it does**: Auto-formats the file (ruff for Python, prettier for JS/TS/etc.) and sets the `.needs_verify` marker.

**What blocking accomplishes**: Nothing useful. The file was already written by the Edit or Write tool. Exit 2 just prevents the agent from seeing the result of its own edit. It does not undo the write.

**What goes wrong if we fail open**: The hook runs with an empty dict. `tool_input` is `{}`, so `file_path` is `None`. The hook hits the `if not file_path: sys.exit(0)` guard and exits cleanly. This means:

- The file is not auto-formatted (minor -- the next successful edit will format it, or the user can run ruff/prettier manually)
- The `.needs_verify` marker is not set (minor -- the next code edit with well-formed stdin will set it)

**Verdict**: fail_open=True is clearly correct. Missing one auto-format pass is far less harmful than blocking the agent from seeing its own edit result.

### 3. `pre_bash_guard.py` (PreToolUse, Bash)

**What it does**: Checks the command against deny patterns (rm -rf, git push --force, etc.) and blocks dangerous commands.

**What blocking accomplishes**: Prevents an unknown command from executing. This is a genuine security function -- if we cannot parse what the command is, the conservative choice is to not let it run.

**What goes wrong if we fail open**: The hook runs with an empty dict. `tool_input` is `{}`, so `cmd` is `""`. The hook hits the `if not cmd: sys.exit(0)` guard and allows the command. This means a command runs without being checked against deny patterns. If that command happened to be `rm -rf /`, it would execute unchecked.

**But how likely is this?** The stdin parse failure means Claude Code sent malformed JSON. If the JSON is malformed, the actual command content is already lost or garbled. The probability that the command is both (a) dangerous and (b) arrives with malformed stdin is extremely low. The much more likely scenario is a benign command (ls, git status, pytest) arriving with a transient encoding issue.

**The tradeoff**:

- fail_open=False (current): Blocks **all** bash commands when stdin is malformed, including safe ones. Agent gets stuck.
- fail_open=True: Allows **all** bash commands when stdin is malformed, including potentially dangerous ones. Agent proceeds.

This is a genuine tension. The question is: what is the blast radius of each failure mode?

**fail_open=False blast radius**: Agent is completely blocked from running any bash command until the stdin issue resolves. For a sub-agent, this is a guaranteed FAIL with no recovery path. The agent cannot run tests, cannot check git status, cannot do anything. This has **high probability of harm** (any bash command is blocked) with **low severity** (no destructive action, but no progress either).

**fail_open=True blast radius**: A dangerous command could execute unchecked. This has **extremely low probability** (requires both malformed stdin AND a dangerous command in the same invocation) but **high severity** (if it happens, the command runs unchecked).

## Ideas

### Idea A: Make All Post Hooks fail_open=True, Keep Pre Guard fail_closed

The simplest change. Change `post_bash_capture.py` and `post_format.py` to use `fail_open=True`. Leave `pre_bash_guard.py` as `fail_open=False`.

**Changes required**:

- `post_bash_capture.py` line 28: `parse_hook_stdin(fail_open=False)` -> `parse_hook_stdin(fail_open=True)`
- `post_format.py` line 36: `parse_hook_stdin(fail_open=False)` -> `parse_hook_stdin(fail_open=True)`

**Test impact**:

- `test_post_bash_capture.py`: `test_malformed_json_exits_2` and `test_partial_json_exits_2` now expect exit 0 instead of 2. `test_exits_2_on_invalid_json_only` needs the same change.
- `test_post_format.py`: `test_exits_2_on_malformed_stdin` and `test_malformed_stdin_exits_2` now expect exit 0 instead of 2.

**Pros**: Fixes the two PostToolUse hooks immediately. Zero risk to security (pre-guard still blocks). Simple, small change.
**Cons**: Doesn't address the pre_bash_guard question. A stdin parse failure in pre_bash_guard still blocks all bash commands.

### Idea B: Make Everything fail_open=True, Add Audit Logging

Make all hooks fail_open=True, but add an audit log entry whenever stdin fails to parse. This way the failure is visible for debugging but never blocks the agent.

**Changes required**:

- Same two changes as Idea A
- `pre_bash_guard.py` line 77: `parse_hook_stdin(fail_open=False)` -> `parse_hook_stdin(fail_open=True)`
- `_lib.py` `parse_hook_stdin`: Add audit logging on parse failure before returning `{}`

New `parse_hook_stdin`:

```python
def parse_hook_stdin(fail_open: bool = False) -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        if fail_open:
            audit_log("parse_hook_stdin", "parse_error", str(exc)[:200])
            return {}
        sys.exit(2)
```

**Pros**: No hook can ever block due to stdin parse failure. Audit trail makes failures visible. The pre-bash guard becomes permissive on parse failure, but the probability of this masking a truly dangerous command is negligible.
**Cons**: Removes the fail-closed security property of pre_bash_guard. Purists would argue this is a downgrade.

### Idea C: Tiered fail_open Based on Hook Type

Encode the Pre/Post distinction directly in the function signature or calling convention:

- PreToolUse hooks: `fail_open=False` (fail-closed is appropriate -- block unknown actions before they execute)
- PostToolUse hooks: `fail_open=True` (fail-open is appropriate -- action already executed, don't hide the result)
- Stop hooks: `fail_open=True` (never lock user in)
- SessionStart hooks: N/A (don't parse stdin)

This is effectively what Idea A does, but framed as a policy rather than a one-off fix.

**Changes required**: Same as Idea A. The "policy" is documented as a code comment or in ARCHITECTURE.md.

**Pros**: Clear mental model. Easy to audit. New hooks automatically know which setting to use based on their type.
**Cons**: Same limitation as Idea A regarding pre_bash_guard. Doesn't address whether pre hooks should actually block on parse failure.

### Idea D: Remove fail_open Parameter, Always Fail Open + Audit

Eliminate the `fail_open` parameter entirely. `parse_hook_stdin` always returns `{}` on parse failure, always logs the failure, never calls `sys.exit(2)`. Individual hooks are responsible for their own "what if I have no data?" behavior.

New `parse_hook_stdin`:

```python
def parse_hook_stdin() -> dict:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        audit_log("parse_hook_stdin", "parse_error", str(exc)[:200])
        return {}
```

Each hook then decides what to do with an empty dict:

- `pre_bash_guard.py`: Gets `cmd = ""`, hits `if not cmd: sys.exit(0)` -- allows the command. **This is the same as Idea B.**
- `post_bash_capture.py`: Gets `exit_code = 0`, exits 0 -- no error capture. Fine.
- `post_format.py`: Gets `file_path = None`, exits 0 -- no formatting. Fine.
- `post_write_prod_scan.py`: Gets `file_path = None`, exits 0 -- no scan. Already does this.
- `stop_verify_gate.py`: Already doesn't use the parsed data for anything (it reads workflow state directly).

**Pros**: Simplest possible API. No parameter to get wrong. Every hook already handles the empty-dict case correctly (they all have early-exit guards for missing data). Removes a footgun from the shared library.
**Cons**: Removes the ability for any hook to fail-closed on parse errors, even if a future hook legitimately needs it. However, no current hook actually benefits from fail-closed parse behavior (see analysis above).

### Idea E: Separate Parse Failure from "No Data" with a Sentinel

Return a sentinel value on parse failure instead of either `{}` or `sys.exit(2)`. This lets each hook distinguish between "stdin was empty" (normal) and "stdin was malformed" (abnormal):

```python
PARSE_ERROR = object()  # sentinel

def parse_hook_stdin() -> dict | object:
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        audit_log("parse_hook_stdin", "parse_error", str(exc)[:200])
        return PARSE_ERROR
```

Each hook checks:

```python
data = parse_hook_stdin()
if data is PARSE_ERROR:
    # Hook-specific handling
    ...
```

**Pros**: Maximum flexibility. Each hook can make its own decision. Parse failures are never silent.
**Cons**: More complex API. Every caller must handle the sentinel. Risk of callers forgetting to check (and treating the sentinel as a dict, causing an AttributeError). Over-engineered for the current situation where every hook should just allow on parse failure.

### Idea F: Pre-Guard Gets Its Own Parse, Others Fail Open

Acknowledge that `pre_bash_guard.py` has genuinely different security requirements and give it its own inline parse logic:

```python
# In pre_bash_guard.py
def parse_stdin_strict() -> dict | None:
    """Parse stdin, returning None on failure (let caller decide)."""
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        return None

def main():
    data = parse_stdin_strict()
    if data is None:
        # Log but allow -- we can't determine if the command is safe,
        # but blocking all bash on a framework bug is worse.
        audit_log("pre_bash_guard", "warn", "stdin parse failure -- allowing command")
        sys.exit(0)
    ...
```

Meanwhile, change `parse_hook_stdin` in `_lib.py` to always fail open (Idea D).

**Pros**: Separates the security concern cleanly. The shared function is simple. The one hook with security requirements handles its own edge case.
**Cons**: Duplicates parse logic. If we decide pre_bash_guard should also just fail open (which the analysis suggests), this extra complexity is unnecessary.

## Evaluation Matrix

| Idea | Post hooks fixed? | Pre guard behavior | API complexity | Audit trail? | Lines changed |
| ---- | ----------------- | ------------------ | -------------- | ------------ | ------------- |
| A    | Yes               | Still blocks       | Same           | No           | ~4            |
| B    | Yes               | Allows + logs      | Same           | Yes          | ~8            |
| C    | Yes               | Still blocks       | Same (+ docs)  | No           | ~4            |
| D    | Yes               | Allows + logs      | Simpler        | Yes          | ~10           |
| E    | Yes               | Hook decides       | More complex   | Yes          | ~20           |
| F    | Yes               | Allows + logs      | Split          | Yes          | ~15           |

## Recommendation: Idea D (Remove fail_open, Always Fail Open + Audit)

### Why Idea D Is Best

**1. Every hook already handles the empty-dict case correctly.**

This is the decisive observation. Look at what each hook does when `parse_hook_stdin` returns `{}`:

- `pre_bash_guard.py`: `cmd = ""` -> `if not cmd: sys.exit(0)` -> allows. Safe because empty string matches no deny patterns.
- `post_bash_capture.py`: `exit_code = 0` -> `if exit_code == 0: sys.exit(0)` -> exits cleanly. Safe because no error to capture.
- `post_format.py`: `file_path = None` -> `if not file_path: sys.exit(0)` -> exits cleanly. Safe because no file to format.
- `post_write_prod_scan.py`: Already uses `fail_open=True`. Same behavior.
- `stop_verify_gate.py`: Already uses `fail_open=True`. Same behavior.

Every hook already has the correct "no data" code path. The `fail_open=False` parameter exists to handle a case that none of the hooks need to handle aggressively.

**2. The pre_bash_guard security argument doesn't hold up under scrutiny.**

The argument for fail-closed in pre_bash_guard is: "If we can't parse the command, we should block it to be safe." But:

- If stdin is malformed, the command content is already lost. We're not blocking a known-dangerous command -- we're blocking an unknown command.
- The base rate of commands is overwhelmingly safe (ls, git status, pytest, echo, cat). Blocking all of them because of a framework bug is disproportionate.
- The agent has no way to recover from a pre-bash guard that blocks everything. It cannot diagnose the problem, cannot run different commands, cannot even check what's wrong. It's a dead end.
- Claude Code itself has its own safety checks. The bash guard is a defense-in-depth layer, not the only barrier.

**3. Audit logging makes failures visible without making them blocking.**

Adding `audit_log("parse_hook_stdin", "parse_error", ...)` in the except clause means:

- Every parse failure is recorded in `hook_audit.jsonl`
- If the failures are systematic (framework bug), the pattern is visible in the log
- The log can be checked after a session to diagnose issues
- No agent is blocked from making progress

**4. Removing the parameter simplifies the API.**

`parse_hook_stdin()` with no arguments is a simpler, harder-to-misuse API than `parse_hook_stdin(fail_open=False)` where the default is the dangerous choice. Every future hook author gets the safe behavior automatically.

### Specific Code Changes

**File 1: `.claude/hooks/_lib.py`**

Change `parse_hook_stdin` to remove the `fail_open` parameter:

```python
def parse_hook_stdin() -> dict:
    """Parse JSON from stdin.

    Returns {} if stdin is a TTY, empty, or contains malformed JSON.
    Parse errors are logged to audit trail but never block the tool call.
    """
    if sys.stdin.isatty():
        return {}
    try:
        raw = sys.stdin.read().strip()
        if not raw:
            return {}
        return json.loads(raw)
    except (json.JSONDecodeError, ValueError) as exc:
        audit_log("parse_hook_stdin", "parse_error", str(exc)[:200])
        return {}
```

**File 2: `.claude/hooks/pre_bash_guard.py` (line 77)**

```python
# Before:
data = parse_hook_stdin(fail_open=False)  # exit 2 on malformed JSON
# After:
data = parse_hook_stdin()  # returns {} on malformed JSON (logged)
```

**File 3: `.claude/hooks/post_bash_capture.py` (line 28)**

```python
# Before:
data = parse_hook_stdin(fail_open=False)  # exit 2 on malformed JSON
# After:
data = parse_hook_stdin()  # returns {} on malformed JSON (logged)
```

**File 4: `.claude/hooks/post_format.py` (line 36)**

```python
# Before:
data = parse_hook_stdin(fail_open=False)  # exit 2 on malformed JSON
# After:
data = parse_hook_stdin()  # returns {} on malformed JSON (logged)
```

**File 5: `.claude/hooks/post_write_prod_scan.py` (line 82)**

```python
# Before:
data = parse_hook_stdin(fail_open=True)
# After:
data = parse_hook_stdin()
```

**File 6: `.claude/hooks/stop_verify_gate.py` (line 35)**

```python
# Before:
parse_hook_stdin(fail_open=True)
# After:
parse_hook_stdin()
```

### Test Impact

**`test_post_bash_capture.py`**:

- `test_malformed_json_exits_2`: Change assertion to `assert result.returncode == 0` (or rename to `test_malformed_json_allows_through`)
- `test_partial_json_exits_2`: Same change
- `test_exits_2_on_invalid_json_only`: Remove or rewrite -- invalid JSON no longer causes exit 2

**`test_post_format.py`**:

- `test_exits_2_on_malformed_stdin`: Change assertion to `assert result.returncode == 0`
- `test_malformed_stdin_exits_2`: Same change

**`test_pre_bash_guard.py`**:

- `test_malformed_stdin_exits_2`: Change assertion to `assert result.returncode == 0` (or rename to `test_malformed_stdin_allows_through`)

**`_lib.py` unit tests** (if any test `parse_hook_stdin` directly):

- Tests for `fail_open=False` -> `sys.exit(2)` should be removed
- Tests for `fail_open=True` -> `{}` should be kept but parameter removed
- Add test: malformed stdin produces an audit log entry

### Could This Mask Real Errors?

**Question**: If `parse_hook_stdin` always returns `{}`, could a real error be silently ignored?

**Answer**: No, for a specific reason: the parse failure is a failure of the **hook infrastructure**, not of the **user's code or command**. The hook's job is to provide a value-add service (formatting, error capture, safety checks). If the hook cannot receive its input, the correct response is to skip the service, not to block the agent.

The analogy: if a spell-checker crashes, you don't prevent the user from saving their document. You skip the spell-check and note that it failed.

**What about pre_bash_guard specifically?** The concern is that a dangerous command could slip through when the guard can't parse stdin. But consider:

1. The guard is one layer in a defense-in-depth stack. Claude Code itself refuses many dangerous operations. The user's OS permissions are another layer. The guard is a supplementary check, not the sole barrier.
2. If the guard is systematically failing to parse stdin, that is a framework-level issue that affects all commands, not just dangerous ones. The right response is to fix the framework issue, not to block all commands.
3. The audit log makes the parse failures visible, so the systematic issue will be noticed and addressed.

### Relationship to Existing Simplification Plan

This change aligns with the hooks simplification brainstorm (2026-03-02). Specifically:

- It reduces complexity in `_lib.py` (removes a parameter and a code path)
- It makes all hooks more resilient to transient failures
- It eliminates a class of "agent gets stuck" failure modes that are hard to diagnose
- It can be implemented as a standalone change or folded into Phase 1 of the simplification plan

If implemented alongside the simplification plan, this would be a natural part of the "core hook utilities cleanup" in Phase 1.

### Implementation Order

1. Change `parse_hook_stdin` in `_lib.py` (remove parameter, add audit logging)
2. Update all 5 callers (remove `fail_open=` argument)
3. Update tests (6-8 test functions change from asserting exit 2 to asserting exit 0)
4. Run full test suite to verify no regressions
5. Add one new test: verify that malformed stdin produces an audit log entry

Total estimated scope: ~30 lines of production code changed, ~20 lines of test code changed. Zero behavior change for well-formed stdin. Strictly improved behavior for malformed stdin.

## Appendix: What If We Want fail_closed Back Later?

If a future hook genuinely needs fail-closed behavior on parse failure (hard to imagine, but possible), the hook can implement it inline:

```python
data = parse_hook_stdin()
if not data:
    # This hook requires stdin data to function safely
    print("[BLOCKED] Hook received no input data")
    sys.exit(2)
```

This is explicit, visible, and per-hook rather than hidden behind a parameter default. It also distinguishes between "stdin was empty" (normal for manual runs) and "I need data to proceed" (hook-specific logic).

## Sources

- `.claude/hooks/_lib.py` lines 209-228: `parse_hook_stdin` implementation
- `.claude/hooks/pre_bash_guard.py`: PreToolUse hook, `fail_open=False`
- `.claude/hooks/post_bash_capture.py`: PostToolUse hook, `fail_open=False`
- `.claude/hooks/post_format.py`: PostToolUse hook, `fail_open=False`
- `.claude/hooks/post_write_prod_scan.py`: PostToolUse hook, `fail_open=True`
- `.claude/hooks/stop_verify_gate.py`: Stop hook, `fail_open=True`
- `.claude/hooks/post_compact_restore.py`: SessionStart hook, no stdin
- `.claude/settings.json`: Hook wiring configuration
- `.claude/docs/brainstorms/2026-03-02-hooks-simplification.md`: Related simplification plan
- `.claude/hooks/tests/test_post_bash_capture.py`: Tests affected by change
- `.claude/hooks/tests/test_post_format.py`: Tests affected by change
- `.claude/hooks/tests/test_pre_bash_guard.py`: Tests affected by change
