#!/usr/bin/env python3
"""SessionStart hook: reminds about rules, marker status, and state summary.

Fires on every session start (not just compaction).
Prints rules reminder, conditionally warns about unverified changes,
and emits a state summary with re-read reminder (R-P2-09).
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import PROJECT_ROOT, read_workflow_state


def _print_protocol_card():
    """Read and print PROTOCOL_CARD.md inline. Silent on any failure."""
    card_path = PROJECT_ROOT / ".claude" / "skills" / "ralph" / "PROTOCOL_CARD.md"
    try:
        content = card_path.read_text(encoding="utf-8").strip()
        if content:
            print("\n  PROTOCOL CARD (inline):")
            for line in content.splitlines():
                print(f"  {line}")
    except Exception:
        pass  # Must never crash the SessionStart hook


# Always print rules reminder (useful on every session start)
print("""WORKFLOW RULES REMINDER:
- Run tests after every code change. Never leave tests failing.
- Run /verify before completing any feature phase.
- The Stop hook will block you if code is unverified (force-stop after 3 attempts).
- Follow the plan in .claude/docs/PLAN.md. Do not add unplanned scope.""")

# Single state file read for all checks
state = read_workflow_state()
marker = state.get("needs_verify")

# Conditionally warn about existing markers
if marker:
    print(f"WARNING: Unverified code changes exist. {marker}")
    print("Run tests or /verify to clear the marker.")

# Emit state summary (R-P2-09)
ralph = state.get("ralph", {})
ralph_story = ralph.get("current_story_id", "")
ralph_attempt = ralph.get("current_attempt", 0)
ralph_skips = ralph.get("consecutive_skips", 0)
ralph_active = bool(ralph_story)

print(
    f"STATE SUMMARY: needs_verify={marker is not None}, "
    f"ralph_active={ralph_active}"
    + (
        f", story={ralph_story}, attempt={ralph_attempt}, skips={ralph_skips}"
        if ralph_active
        else ""
    )
)
print("MANDATORY: Re-read .workflow-state.json before continuing any loop.")

# Ralph context restore (R-P4-01 through R-P4-04)
if ralph_active and ralph_story:
    import json as _json

    prd_path = PROJECT_ROOT / ".claude" / "prd.json"
    try:
        prd = _json.loads(prd_path.read_text(encoding="utf-8"))
        stories = prd.get("stories", [])

        # Find remaining (unpassed) stories
        remaining = [s for s in stories if not s.get("passed")]
        remaining_ids = [s.get("id", "?") for s in remaining]

        # Find current story details
        current = next((s for s in stories if s.get("id") == ralph_story), None)

        print("\nRALPH CONTEXT RESTORE:")
        print(f"  Story: {ralph_story}, Attempt: {ralph_attempt}, Skips: {ralph_skips}")
        print(f"  Branch: {ralph.get('feature_branch', '(unknown)')}")
        print(f"  Remaining stories: {len(remaining)} ({', '.join(remaining_ids)})")

        if current:
            desc = current.get("description", "(no description)")
            print(f"  Current story: {desc}")
            criteria = current.get("acceptanceCriteria", [])
            if criteria:
                print("  Acceptance criteria:")
                for ac in criteria:
                    ac_id = ac.get("id", "?")
                    criterion = ac.get("criterion", "")
                    print(f"    - {ac_id}: {criterion[:120]}")

        # Step-aware resume instructions (R-P4B-04)
        current_step = ralph.get("current_step", "")
        if current_step:
            print(f"  Last step: {current_step}")
            if "STEP_5" in current_step or "STEP_6" in current_step:
                print(
                    f"  Resume: Re-read ralph/SKILL.md, resume from {current_step}. Check if worker result is pending."
                )
            elif "STEP_7" in current_step or "STEP_2" in current_step:
                print(
                    "  Resume: Re-read ralph/SKILL.md, continue from STEP 2 -- find next unpassed story."
                )
            else:
                print(
                    "  Resume: Re-read ralph/SKILL.md, continue from STEP 2 -- determine position from state."
                )
        else:
            print("  Resume: Re-read ralph/SKILL.md, continue from STEP 2.")
        _print_protocol_card()
    except (FileNotFoundError, _json.JSONDecodeError, OSError, KeyError, TypeError):
        # R-P4-02: graceful fallback on missing/corrupt prd.json
        print("\nRALPH CONTEXT RESTORE (partial -- prd.json unavailable):")
        print(f"  Story: {ralph_story}, Attempt: {ralph_attempt}")
        current_step = ralph.get("current_step", "")
        if current_step:
            print(f"  Last step: {current_step}")
        print("  Resume: Re-read ralph/SKILL.md, continue from STEP 2.")
        _print_protocol_card()

sys.exit(0)
