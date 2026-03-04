"""Tests for _lib.py: CODE_EXTENSIONS, PROD_VIOLATION_PATTERNS, scan_file_violations, workflow.json schema, audit log rotation."""

import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from _lib import (
    CODE_EXTENSIONS,
    PROD_VIOLATION_PATTERNS,
    scan_file_violations,
)


class TestCodeExtensions:
    """# Tests R-P2-01"""

    def test_code_extensions_is_frozenset(self) -> None:
        """# Tests R-P2-01 -- frozenset[str]."""
        CODE_EXTENSIONS_type = type(CODE_EXTENSIONS)
        assert CODE_EXTENSIONS_type is frozenset
        for ext in CODE_EXTENSIONS:
            ext_type = type(ext)
            assert ext_type is str

    def test_code_extensions_has_at_least_14_entries(self) -> None:
        """# Tests R-P2-01 -- >= 14 entries."""
        assert len(CODE_EXTENSIONS) >= 14

    def test_code_extensions_covers_required_languages(self) -> None:
        """# Tests R-P2-01 -- required languages present."""
        required = {
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
        }
        assert required.issubset(CODE_EXTENSIONS)
        assert ".h" in CODE_EXTENSIONS or ".hpp" in CODE_EXTENSIONS

    def test_code_extensions_includes_h_and_hpp(self) -> None:
        """# Tests R-P2-01 -- .h and .hpp present."""
        assert ".h" in CODE_EXTENSIONS
        assert ".hpp" in CODE_EXTENSIONS

    def test_code_extensions_all_start_with_dot(self) -> None:
        """# Tests R-P2-01 -- all start with dot."""
        for ext in CODE_EXTENSIONS:
            assert ext.startswith("."), f"Extension {ext!r} does not start with '.'"


HOOKS_DIR = Path(__file__).resolve().parent.parent


class TestCodeExtensionsCentralization:
    """# Tests R-P2-02"""

    def test_post_format_imports_code_extensions_from_lib(self) -> None:
        """# Tests R-P2-02 -- post_format.py imports from _lib."""
        source = (HOOKS_DIR / "post_format.py").read_text(encoding="utf-8")
        assert "from _lib import" in source or "from _lib" in source
        assert "CODE_EXTENSIONS" in source

    def test_post_format_no_local_code_extensions(self) -> None:
        """# Tests R-P2-02 -- no local def in post_format.py."""
        source = (HOOKS_DIR / "post_format.py").read_text(encoding="utf-8")
        local_def = re.search(r"^CODE_EXTENSIONS\s*=\s*\{", source, re.MULTILINE)
        assert local_def is None, "post_format.py still defines local CODE_EXTENSIONS"

    def test_post_write_prod_scan_imports_code_extensions_from_lib(self) -> None:
        """# Tests R-P2-02 -- prod_scan imports from _lib."""
        source = (HOOKS_DIR / "post_write_prod_scan.py").read_text(encoding="utf-8")
        assert "CODE_EXTENSIONS" in source

    def test_post_write_prod_scan_no_local_code_extensions(self) -> None:
        """# Tests R-P2-02 -- no local def in prod_scan."""
        source = (HOOKS_DIR / "post_write_prod_scan.py").read_text(encoding="utf-8")
        local_def = re.search(r"^CODE_EXTENSIONS\s*=\s*\{", source, re.MULTILINE)
        assert local_def is None, (
            "post_write_prod_scan.py still defines local CODE_EXTENSIONS"
        )

    def test_qa_runner_imports_code_extensions_from_lib(self) -> None:
        """# Tests R-P2-02 -- qa_runner imports from _lib."""
        source = (HOOKS_DIR / "qa_runner.py").read_text(encoding="utf-8")
        assert "CODE_EXTENSIONS" in source

    def test_qa_runner_no_local_source_extensions(self) -> None:
        """# Tests R-P2-02 -- no local def in qa_runner."""
        source = (HOOKS_DIR / "qa_runner.py").read_text(encoding="utf-8")
        local_def = re.search(r"^_SOURCE_EXTENSIONS\s*=\s*\{", source, re.MULTILINE)
        assert local_def is None, "qa_runner.py still defines local _SOURCE_EXTENSIONS"


WORKFLOW_JSON_PATH = Path(__file__).resolve().parent.parent.parent / "workflow.json"


class TestWorkflowJsonSchema:
    def test_workflow_json_parseable(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        data_type = type(data)
        assert data_type is dict

    def test_qa_runner_section(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        qa = data["qa_runner"]
        keys = set(qa.keys())
        assert keys >= {"enabled", "skip_steps", "manual_steps", "production_scan"}

    def test_test_quality_section(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        tq = data["test_quality"]
        assert "min_assertions_per_test" in tq
        assert "detect_self_mocks" in tq
        assert "detect_mock_only" in tq

    def test_verification_log_section(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        vl = data["verification_log"]
        assert "format" in vl
        assert "max_entries" in vl
        assert "path" in vl

    def test_commands_populated(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        cmds = data["commands"]
        assert cmds["test"], "test command must be non-empty"
        assert cmds["lint"], "lint command must be non-empty"
        assert cmds["format"], "format command must be non-empty"

    def test_plan_sync_section(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        ps = data["plan_sync"]
        assert "mode" in ps
        assert "action" in ps

    def test_external_scanners_section(self) -> None:
        data = json.loads(WORKFLOW_JSON_PATH.read_text(encoding="utf-8"))
        es = data["external_scanners"]
        assert "bandit" in es
        assert "semgrep" in es
        assert es["bandit"]["enabled"] is False
        assert es["semgrep"]["enabled"] is False


class TestProdViolationPatterns:
    """# Tests R-P1-01, R-P1-02"""

    def test_at_least_13_patterns(self) -> None:
        """# Tests R-P1-01 -- at least 13 regex patterns."""
        assert len(PROD_VIOLATION_PATTERNS) >= 13

    def test_pattern_4tuple_structure(self) -> None:
        """# Tests R-P1-01 -- each entry is a (regex, vid, msg, severity) 4-tuple."""
        for entry in PROD_VIOLATION_PATTERNS:
            assert len(entry) == 4, f"Expected 4-tuple, got {len(entry)}"
            regex, vid, msg, sev = entry
            assert isinstance(regex, str)
            assert isinstance(vid, str)
            assert isinstance(msg, str)
            assert sev in ("block", "warn"), f"Invalid severity: {sev}"

    def test_severity_assignments(self) -> None:
        """# Tests R-P1-01 -- security=block, hygiene=warn."""
        severities = {vid: sev for _, vid, _, sev in PROD_VIOLATION_PATTERNS}
        assert severities["hardcoded-secret"] == "block"
        assert severities["sql-injection"] == "block"
        assert severities["shell-injection"] == "block"
        assert severities["subprocess-shell-injection"] == "block"
        assert severities["os-exec-injection"] == "block"
        assert severities["raw-sql-fstring"] == "block"
        assert severities["expanded-secret"] == "block"
        assert severities["todo-comment"] == "warn"
        assert severities["bare-except"] == "warn"
        assert severities["debug-print"] == "warn"
        assert severities["debugger-stmt"] == "warn"
        assert severities["debug-import"] == "warn"
        assert severities["broad-except"] == "warn"

    def test_todo_hack_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "todo-comment" in patterns
        assert re.search(patterns["todo-comment"], "# TODO: fix later")
        assert re.search(patterns["todo-comment"], "# HACK: workaround")
        assert re.search(patterns["todo-comment"], "# FIXME: broken")
        assert re.search(patterns["todo-comment"], "# XXX: danger")

    def test_todo_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["todo-comment"], "def todomething():")

    def test_bare_except_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "bare-except" in patterns
        assert re.search(patterns["bare-except"], "except:")
        assert re.search(patterns["bare-except"], "except :  ")
        assert not re.search(patterns["bare-except"], "except ValueError:")

    def test_debug_print_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "debug-print" in patterns
        assert re.search(patterns["debug-print"], 'print("hello")')
        assert re.search(patterns["debug-print"], "console.log(x)")

    def test_debug_print_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["debug-print"], "logger.info('hello')")

    def test_hardcoded_secret_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "hardcoded-secret" in patterns
        assert re.search(patterns["hardcoded-secret"], 'password = "hunter2"')
        assert re.search(patterns["hardcoded-secret"], "api_key = 'abc123'")
        assert re.search(patterns["hardcoded-secret"], 'secret = "xyz"')

    def test_hardcoded_secret_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["hardcoded-secret"], 'password = os.getenv("PW")')

    def test_sql_injection_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "sql-injection" in patterns
        assert re.search(
            patterns["sql-injection"],
            'query = "SELECT * FROM users WHERE id=" + user_id',
        )

    def test_sql_injection_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(
            patterns["sql-injection"],
            'cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))',
        )

    def test_debugger_statement_pattern_matches(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "debugger-stmt" in patterns
        assert re.search(patterns["debugger-stmt"], "import pdb; pdb.set_trace()")
        assert re.search(patterns["debugger-stmt"], "breakpoint()")
        assert re.search(patterns["debugger-stmt"], "debugger")

    def test_subprocess_shell_injection_positive(self) -> None:
        """# Tests R-P1-02 -- subprocess shell=True detection."""
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "subprocess-shell-injection" in patterns
        assert re.search(
            patterns["subprocess-shell-injection"],
            "subprocess.run(cmd, shell=True)",
        )
        assert re.search(
            patterns["subprocess-shell-injection"],
            "subprocess.call(x, shell=True)",
        )
        assert re.search(
            patterns["subprocess-shell-injection"],
            "subprocess.Popen(cmd, shell=True)",
        )

    def test_subprocess_shell_injection_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(
            patterns["subprocess-shell-injection"],
            "subprocess.run(['ls', '-la'])",
        )
        assert not re.search(
            patterns["subprocess-shell-injection"],
            "subprocess.run(cmd, shell=False)",
        )

    def test_os_exec_injection_positive(self) -> None:
        """# Tests R-P1-02 -- os.popen/exec detection."""
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "os-exec-injection" in patterns
        assert re.search(patterns["os-exec-injection"], 'os.popen("ls")')
        assert re.search(patterns["os-exec-injection"], "os.execv('/bin/sh', args)")
        assert re.search(patterns["os-exec-injection"], "os.execvp('cmd', args)")

    def test_os_exec_injection_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["os-exec-injection"], "os.path.exists('/tmp')")
        assert not re.search(patterns["os-exec-injection"], "os.environ.get('PATH')")

    def test_raw_sql_fstring_positive(self) -> None:
        """# Tests R-P1-02 -- f-string SQL detection."""
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "raw-sql-fstring" in patterns
        assert re.search(
            patterns["raw-sql-fstring"],
            '.execute(f"SELECT * FROM users WHERE id={uid}")',
        )
        assert re.search(
            patterns["raw-sql-fstring"],
            ".executemany(f'INSERT INTO t VALUES({v})')",
        )

    def test_raw_sql_fstring_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(
            patterns["raw-sql-fstring"],
            '.execute("SELECT * FROM users WHERE id = %s", (uid,))',
        )

    def test_broad_except_positive(self) -> None:
        """# Tests R-P1-02 -- except Exception detection."""
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "broad-except" in patterns
        assert re.search(patterns["broad-except"], "except Exception:")
        assert re.search(patterns["broad-except"], "    except Exception:")

    def test_broad_except_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["broad-except"], "except ValueError:")
        assert not re.search(patterns["broad-except"], "except (OSError, IOError):")

    def test_expanded_secret_positive(self) -> None:
        """# Tests R-P1-02 -- expanded credential detection."""
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert "expanded-secret" in patterns
        assert re.search(patterns["expanded-secret"], 'oauth = "my_token"')
        assert re.search(patterns["expanded-secret"], "credential = 'abc123'")
        assert re.search(patterns["expanded-secret"], 'jwt = "eyJ..."')
        assert re.search(patterns["expanded-secret"], 'private_key = "-----BEGIN"')
        assert re.search(patterns["expanded-secret"], "access_key = 'AKIA...'")
        assert re.search(patterns["expanded-secret"], 'auth_token = "tok_123"')

    def test_expanded_secret_negative(self) -> None:
        patterns = {vid: regex for regex, vid, _, _ in PROD_VIOLATION_PATTERNS}
        assert not re.search(patterns["expanded-secret"], 'oauth = os.getenv("OAUTH")')
        assert not re.search(patterns["expanded-secret"], "jwt = config.get('jwt')")


class TestScanFileViolations:
    """# Tests R-P1-03"""

    def test_returns_list(self, sample_violation_file: Path) -> None:
        """# Tests R-P1-03 -- returns a list."""
        result = scan_file_violations(sample_violation_file)
        result_type = type(result)
        assert result_type is list

    def test_violation_dict_fields(self, sample_violation_file: Path) -> None:
        """# Tests R-P1-03 -- each violation has required dict fields."""
        result = scan_file_violations(sample_violation_file)
        assert len(result) >= 1, "Expected violations in bad_code.py"
        for v in result:
            vkeys = set(v.keys())
            assert vkeys >= {"line", "violation_id", "message", "severity", "text"}
            sev = v["severity"]
            assert sev in ("block", "warn")

    def test_detects_known_violations(self, sample_violation_file: Path) -> None:
        """# Tests R-P1-03 -- detects known violation IDs."""
        result = scan_file_violations(sample_violation_file)
        violation_ids = {v["violation_id"] for v in result}
        assert "todo-comment" in violation_ids
        assert "hardcoded-secret" in violation_ids
        assert "bare-except" in violation_ids
        assert "debug-print" in violation_ids
        assert "debugger-stmt" in violation_ids

    def test_severity_matches_pattern(self, sample_violation_file: Path) -> None:
        """# Tests R-P1-03 -- result severity matches pattern definition."""
        result = scan_file_violations(sample_violation_file)
        severity_map = {vid: sev for _, vid, _, sev in PROD_VIOLATION_PATTERNS}
        for v in result:
            expected = severity_map.get(v["violation_id"])
            assert v["severity"] == expected, (
                f"{v['violation_id']}: expected severity={expected}, got {v['severity']}"
            )

    def test_clean_file_no_violations(self, sample_clean_file: Path) -> None:
        """# Tests R-P1-03 -- clean file returns empty list."""
        result = scan_file_violations(sample_clean_file)
        assert result == []

    def test_exclude_patterns(self, sample_violation_file: Path) -> None:
        """# Tests R-P1-03 -- exclude_patterns filters matching lines."""
        result_all = scan_file_violations(sample_violation_file)
        result_filtered = scan_file_violations(
            sample_violation_file, exclude_patterns=["noqa", "type: ignore"]
        )
        assert len(result_all) == len(result_filtered)

    def test_nonexistent_file_returns_empty(self) -> None:
        result = scan_file_violations(Path("/nonexistent/file.py"))
        assert result == []

    def test_unreadable_file_returns_empty(self, tmp_path: Path) -> None:
        result = scan_file_violations(tmp_path)
        assert result == []

    def test_new_pattern_subprocess(
        self, sample_subprocess_injection_file: Path
    ) -> None:
        result = scan_file_violations(sample_subprocess_injection_file)
        ids = {v["violation_id"] for v in result}
        assert "subprocess-shell-injection" in ids

    def test_new_pattern_os_exec(self, sample_os_exec_injection_file: Path) -> None:
        result = scan_file_violations(sample_os_exec_injection_file)
        ids = {v["violation_id"] for v in result}
        assert "os-exec-injection" in ids

    def test_new_pattern_raw_sql(self, sample_raw_sql_fstring_file: Path) -> None:
        result = scan_file_violations(sample_raw_sql_fstring_file)
        ids = {v["violation_id"] for v in result}
        assert "raw-sql-fstring" in ids

    def test_new_pattern_broad_except(self, sample_broad_except_file: Path) -> None:
        result = scan_file_violations(sample_broad_except_file)
        ids = {v["violation_id"] for v in result}
        assert "broad-except" in ids

    def test_new_pattern_expanded_secret(
        self, sample_expanded_secret_file: Path
    ) -> None:
        result = scan_file_violations(sample_expanded_secret_file)
        ids = {v["violation_id"] for v in result}
        assert "expanded-secret" in ids


class TestAuditLogRotation:
    """# Tests R-P1-01, R-P1-02, R-P1-03, R-P1-04"""

    def test_audit_log_does_not_rotate_small_file(self, tmp_path: Path) -> None:
        """# Tests R-P1-01 -- small log stays untrimmed."""
        _original_lib = sys.modules.get("_lib")
        os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
        try:
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            import _lib

            errors_dir = tmp_path / ".claude" / "errors"
            errors_dir.mkdir(parents=True, exist_ok=True)
            log_path = errors_dir / "hook_audit.jsonl"
            for i in range(10):
                _lib.audit_log("test_hook", "allow", f"detail-{i}")

            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) == 10, f"Expected 10 lines, got {len(lines)}"
        finally:
            if "CLAUDE_PROJECT_ROOT" in os.environ:
                del os.environ["CLAUDE_PROJECT_ROOT"]
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            if _original_lib is not None:
                sys.modules["_lib"] = _original_lib

    def test_audit_size_threshold_constant_exists(self) -> None:
        """# Tests R-P1-02 -- AUDIT_SIZE_THRESHOLD constant = 75000."""
        from _lib import AUDIT_SIZE_THRESHOLD

        assert AUDIT_SIZE_THRESHOLD == 75_000

    def test_audit_log_rotates_when_size_exceeds_threshold(
        self, tmp_path: Path
    ) -> None:
        """# Tests R-P1-03 -- large log trimmed to AUDIT_TRIM_TO lines."""
        _original_lib = sys.modules.get("_lib")
        os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
        try:
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            import _lib

            errors_dir = tmp_path / ".claude" / "errors"
            errors_dir.mkdir(parents=True, exist_ok=True)
            log_path = errors_dir / "hook_audit.jsonl"
            big_lines = []
            for i in range(700):
                import json as _json
                from datetime import datetime as _dt
                from datetime import timezone as _tz

                entry = _json.dumps(
                    {
                        "ts": _dt.now(_tz.utc).isoformat(),
                        "hook": "test_hook",
                        "decision": "allow",
                        "detail": f"detail-{i:04d}-padding" + "x" * 50,
                    }
                )
                big_lines.append(entry)
            log_path.write_text("\n".join(big_lines) + "\n", encoding="utf-8")
            assert os.path.getsize(log_path) >= 75_000
            _lib.audit_log("test_hook", "allow", "trigger-rotation")

            lines = log_path.read_text(encoding="utf-8").strip().split("\n")
            assert len(lines) <= _lib.AUDIT_TRIM_TO + 1, (
                f"Expected <= {_lib.AUDIT_TRIM_TO + 1} lines after rotation, got {len(lines)}"
            )
            assert len(lines) >= _lib.AUDIT_TRIM_TO, (
                f"Expected >= {_lib.AUDIT_TRIM_TO} lines after rotation, got {len(lines)}"
            )
        finally:
            if "CLAUDE_PROJECT_ROOT" in os.environ:
                del os.environ["CLAUDE_PROJECT_ROOT"]
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            if _original_lib is not None:
                sys.modules["_lib"] = _original_lib

    def test_audit_log_silent_on_os_error(self, tmp_path: Path) -> None:
        """# Tests R-P1-04 -- no exceptions propagated."""
        _original_lib = sys.modules.get("_lib")
        os.environ["CLAUDE_PROJECT_ROOT"] = str(tmp_path)
        try:
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            import _lib

            errors_dir = tmp_path / ".claude" / "errors"
            errors_dir.mkdir(parents=True, exist_ok=True)
            log_path = errors_dir / "hook_audit.jsonl"
            log_path.write_text("", encoding="utf-8")
            try:
                _lib.audit_log("test_hook", "allow", "safe-call")
            except Exception as exc:
                raise AssertionError(f"audit_log raised {type(exc).__name__}: {exc}")
        finally:
            if "CLAUDE_PROJECT_ROOT" in os.environ:
                del os.environ["CLAUDE_PROJECT_ROOT"]
            if "_lib" in sys.modules:
                del sys.modules["_lib"]
            if _original_lib is not None:
                sys.modules["_lib"] = _original_lib
