#!/usr/bin/env python3
"""Stop hook: blocks completion if code changes are unverified.

Uses file-based 3-attempt counter for escape hatch:
  Attempt 1: Block — "Run tests or /verify."
  Attempt 2: Block — "Still unverified. Try once more to force-stop."
  Attempt 3: Allow — "Force-stopping with unverified code."

Stdin parsing always fails open — NEVER locks user in on parse errors.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    audit_log,
    clear_marker,
    increment_stop_block_count,
    is_worktree_path,
    parse_hook_stdin,
    read_workflow_state,
    update_workflow_state,
)


def main():
    state = read_workflow_state()
    marker_content = state.get("needs_verify")

    # Sanitize stale worktree markers -- auto-clear if marker references a worktree path
    if marker_content and is_worktree_path(marker_content):
        update_workflow_state(needs_verify=None)
        audit_log(
            "stop_verify_gate",
            "sanitize",
            f"Cleared worktree marker: {marker_content[:200]}",
        )
        marker_content = None

    if not marker_content:
        # No unverified changes — allow stop
        sys.exit(0)

    parse_hook_stdin()

    count = state.get("stop_block_count", 0)

    if count >= 2:
        # Third attempt: force-stop allowed — clear marker
        clear_marker()
        audit_log("stop_verify_gate", "force_stop", f"After {count + 1} attempts")
        print(
            json.dumps(
                {
                    "decision": "warn",
                    "reason": "Force-stopping with unverified code. All markers cleared.",
                }
            )
        )
        sys.exit(0)

    # Block and increment counter
    new_count = increment_stop_block_count()

    reason_detail = f"unverified code: {marker_content}"

    audit_log(
        "stop_verify_gate",
        "block",
        f"Attempt {new_count}, {reason_detail[:200]}",
    )

    if new_count == 1:
        msg = f"Blocked: {reason_detail}. Run tests or /verify before finishing."
    else:
        msg = f"Still blocked: {reason_detail}. Run tests, /verify, or try once more to force-stop."

    print(json.dumps({"decision": "block", "reason": msg}))
    sys.exit(0)


if __name__ == "__main__":
    try:
        main()
    except Exception:
        # NEVER lock user in — allow stop on any unhandled crash
        print(
            json.dumps(
                {
                    "decision": "warn",
                    "reason": "Stop hook crashed — allowing stop. Check .claude/errors/.",
                }
            )
        )
        sys.exit(0)
