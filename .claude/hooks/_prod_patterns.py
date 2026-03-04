"""Production violation patterns and file scanning."""

import re
from pathlib import Path

# Each entry: (regex_pattern, violation_id, human_message, severity)
# severity: "block" = security issue, "warn" = hygiene
PROD_VIOLATION_PATTERNS: list[tuple[str, str, str, str]] = [
    (
        r"\b(TODO|HACK|FIXME|XXX)\b",
        "todo-comment",
        "TODO/HACK/FIXME/XXX comment found in production code",
        "warn",
    ),
    (
        r"^\s*except\s*:",
        "bare-except",
        "Bare except block catches all exceptions including SystemExit and KeyboardInterrupt",
        "warn",
    ),
    (
        r"\bprint\s*\(|console\.log\s*\(",
        "debug-print",
        "Debug print/console.log statement found in production code",
        "warn",
    ),
    (
        r"""(?:password|passwd|api_key|apikey|secret|token)\s*=\s*(['"])(?!$)""",
        "hardcoded-secret",
        "Potential hardcoded secret or credential",
        "block",
    ),
    (
        r"""(?:SELECT|INSERT|UPDATE|DELETE)\s+.*\+\s*(?:\w+|['"])""",
        "sql-injection",
        "String concatenation in SQL query (use parameterized queries)",
        "block",
    ),
    (
        r"\bimport\s+pdb\b|\bpdb\.set_trace\s*\(|\bbreakpoint\s*\(|\bdebugger\b|\bbinding\.pry\b",
        "debugger-stmt",
        "Debugger statement found in production code",
        "warn",
    ),
    (
        r"^\s*import\s+(?:pprint|icecream)\b",
        "debug-import",
        "Debug-only import found in production code",
        "warn",
    ),
    (
        r"""os\.system\s*\(\s*(?:f['"]|['"].*\+)""",
        "shell-injection",
        "Potential shell injection via os.system with string formatting",
        "block",
    ),
    (
        r"""subprocess\.(?:run|call|Popen|check_output|check_call)\s*\(.*shell\s*=\s*True""",
        "subprocess-shell-injection",
        "subprocess with shell=True (use shell=False with list args)",
        "block",
    ),
    (
        r"""os\.(?:popen|execl|execle|execlp|execlpe|execv|execve|execvp|execvpe)\s*\(""",
        "os-exec-injection",
        "os.popen/exec call (use subprocess with shell=False)",
        "block",
    ),
    (
        r"""\.(?:execute|executemany|raw)\s*\(\s*f['"]""",
        "raw-sql-fstring",
        "f-string in SQL execute (use parameterized queries)",
        "block",
    ),
    (
        r"""^\s*except\s+Exception\s*:""",
        "broad-except",
        "except Exception catches SystemExit and KeyboardInterrupt",
        "warn",
    ),
    (
        r"""(?:oauth|credential|jwt|private_key|access_key|auth_token)\s*=\s*(['"])(?!$)""",
        "expanded-secret",
        "Potential hardcoded credential (use environment variables)",
        "block",
    ),
]


def scan_file_violations(
    filepath: Path, exclude_patterns: list[str] | None = None
) -> list[dict]:
    """Scan a source file for production-code violations.

    Returns list of violation dicts with keys: line, violation_id, message, text.
    Returns [] if the file does not exist or cannot be read.
    """
    if exclude_patterns is None:
        exclude_patterns = []

    try:
        content = filepath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, ValueError):
        return []

    violations: list[dict] = []
    for line_num, line_text in enumerate(content.splitlines(), start=1):
        if any(ep in line_text for ep in exclude_patterns):
            continue

        for pattern, violation_id, message, severity in PROD_VIOLATION_PATTERNS:
            if re.search(pattern, line_text):
                violations.append(
                    {
                        "line": line_num,
                        "violation_id": violation_id,
                        "message": message,
                        "severity": severity,
                        "text": line_text.rstrip()[:200],
                    }
                )
    return violations
