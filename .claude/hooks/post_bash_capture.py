#!/usr/bin/env python3
"""Post-Bash Capture - Log errors and detect test runs.

Captures failed commands to .claude/errors/last_error.json.
Clears verification marker on successful test runs.
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _lib import (
    ERROR_DIR,
    audit_log,
    clear_marker,
    get_test_patterns,
    is_test_command,
    load_workflow_config,
    parse_hook_stdin,
)


def main():
    ERROR_DIR.mkdir(parents=True, exist_ok=True)

    data = parse_hook_stdin()

    tool_input = data.get("tool_input", {})
    tool_response = data.get("tool_response", {})

    # Get exit code — explicit None check (0 is falsy in Python)
    exit_code = tool_response.get("exitCode")
    if exit_code is None:
        exit_code = 0

    # Load configurable test patterns
    config = load_workflow_config()
    patterns = get_test_patterns(config)

    # Detect successful test runs and clear verification marker
    cmd = tool_input.get("command", "")
    if exit_code == 0 and is_test_command(cmd, patterns):
        clear_marker()  # Clears .needs_verify and .stop_block_count
        audit_log("post_bash_capture", "marker_cleared", f"Test passed: {cmd[:200]}")

    # Only capture failures
    if exit_code == 0:
        sys.exit(0)

    command = tool_input.get("command", "unknown")
    stdout = tool_response.get("stdout", "")
    stderr = tool_response.get("stderr", "")

    # Build error record
    error_data = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "exit_code": exit_code,
        "command": command[:1000],
        "stderr": stderr[-2000:] if stderr else "",
        "stdout_tail": stdout[-500:] if stdout else "",
        "cwd": str(Path.cwd()),
    }

    # Write last error
    last_error = ERROR_DIR / "last_error.json"
    last_error.write_text(json.dumps(error_data, indent=2))

    audit_log(
        "post_bash_capture",
        "error_captured",
        f"exit={exit_code} cmd={command[:200]}",
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
