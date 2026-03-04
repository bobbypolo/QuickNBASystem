"""Shared fixtures for hook tests."""

import json
from pathlib import Path

import pytest


@pytest.fixture()
def tmp_dir(tmp_path: Path) -> Path:
    """Provide a clean temporary directory for each test."""
    return tmp_path


@pytest.fixture()
def sample_violation_file(tmp_path: Path) -> Path:
    """Create a Python file with known production violations."""
    code = tmp_path / "bad_code.py"
    code.write_text(
        "# TODO: fix this later\n"
        'password = "hunter2"\n'
        "except:\n"
        '    print("oops")\n'
        "import pdb; pdb.set_trace()\n"
        'query = "SELECT * FROM users WHERE id=" + user_id\n',
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_clean_file(tmp_path: Path) -> Path:
    """Create a Python file with no violations."""
    code = tmp_path / "clean_code.py"
    code.write_text(
        "def add(a: int, b: int) -> int:\n"
        '    """Add two numbers."""\n'
        "    return a + b\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_test_good(tmp_path: Path) -> Path:
    """Create a well-formed test file."""
    code = tmp_path / "test_good.py"
    code.write_text(
        "def test_addition():\n"
        '    """# Tests R-P1-01"""\n'
        "    result = 1 + 1\n"
        "    assert result == 2\n"
        "\n"
        "def test_subtraction():\n"
        '    """# Tests R-P1-02"""\n'
        "    result = 3 - 1\n"
        "    assert result == 2\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_test_no_assertions(tmp_path: Path) -> Path:
    """Create a test file with assertion-free tests."""
    code = tmp_path / "test_no_assert.py"
    code.write_text(
        "def test_does_nothing():\n"
        "    x = 1 + 1\n"
        "\n"
        "def test_also_nothing():\n"
        "    pass\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_test_self_mock(tmp_path: Path) -> Path:
    """Create a test file with self-mocking anti-pattern."""
    code = tmp_path / "test_self_mock.py"
    code.write_text(
        "from unittest.mock import patch\n"
        "\n"
        "def test_my_func():\n"
        '    with patch("module.my_func") as mock_func:\n'
        "        mock_func.return_value = 42\n"
        "        result = mock_func()\n"
        "        assert result == 42\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_test_mock_only(tmp_path: Path) -> Path:
    """Create a test file with mock-only assertions."""
    code = tmp_path / "test_mock_only.py"
    code.write_text(
        "from unittest.mock import MagicMock\n"
        "\n"
        "def test_mock_only():\n"
        "    mock = MagicMock()\n"
        "    mock.do_thing()\n"
        "    mock.do_thing.assert_called_once()\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_test_class_based(tmp_path: Path) -> Path:
    """Create a test file using class-based test methods."""
    code = tmp_path / "test_class_based.py"
    code.write_text(
        "class TestMathOps:\n"
        "    def test_addition(self):\n"
        '        """# Tests R-P1-01"""\n'
        "        assert 1 + 1 == 2\n"
        "\n"
        "    def test_subtraction(self):\n"
        '        """# Tests R-P1-02"""\n'
        "        assert 3 - 1 == 2\n"
        "\n"
        "    def test_multiply(self):\n"
        "        assert 2 * 3 == 6\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_prd(tmp_path: Path) -> Path:
    """Create a minimal prd.json for marker validation."""
    prd = tmp_path / "prd.json"
    prd.write_text(
        json.dumps(
            {
                "version": "2.0",
                "stories": [
                    {
                        "id": "STORY-001",
                        "acceptanceCriteria": [
                            {"id": "R-P1-01"},
                            {"id": "R-P1-02"},
                            {"id": "R-P1-03"},
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return prd


@pytest.fixture()
def sample_subprocess_injection_file(tmp_path: Path) -> Path:
    """Create a Python file with subprocess shell=True injection."""
    code = tmp_path / "subprocess_inject.py"
    code.write_text(
        'import subprocess\nsubprocess.run(cmd, shell=True)\n',
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_os_exec_injection_file(tmp_path: Path) -> Path:
    """Create a Python file with os.popen/exec injection."""
    code = tmp_path / "os_exec_inject.py"
    code.write_text(
        'import os\nos.popen("ls -la")\n',
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_raw_sql_fstring_file(tmp_path: Path) -> Path:
    """Create a Python file with f-string SQL injection."""
    code = tmp_path / "raw_sql_fstring.py"
    code.write_text(
        'cursor.execute(f"SELECT * FROM users WHERE id={user_id}")\n',
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_broad_except_file(tmp_path: Path) -> Path:
    """Create a Python file with broad except Exception."""
    code = tmp_path / "broad_except.py"
    code.write_text(
        "try:\n    do_thing()\nexcept Exception:\n    pass\n",
        encoding="utf-8",
    )
    return code


@pytest.fixture()
def sample_expanded_secret_file(tmp_path: Path) -> Path:
    """Create a Python file with expanded secret pattern."""
    code = tmp_path / "expanded_secret.py"
    code.write_text(
        'oauth = "my_oauth_token_123"\n',
        encoding="utf-8",
    )
    return code
