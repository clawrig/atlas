"""Tests for cross-project file access tools: atlas_read_file, atlas_grep, atlas_glob."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

from atlas_mcp.registry import resolve_project_path
from atlas_mcp.server import atlas_glob, atlas_grep, atlas_read_file


@pytest.fixture
def fake_project(tmp_path):
    """Create a fake project directory with test files."""
    # Create files
    (tmp_path / "README.md").write_text("# Test Project\nHello world\n")
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "import os\n\ndef main():\n    print('hello')\n"
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def helper():\n    return 42\n\ndef other():\n    return helper()\n"
    )
    (tmp_path / "src" / "data.json").write_text('{"key": "value"}\n')
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_main.py").write_text(
        "def test_main():\n    assert True\n"
    )

    # Create a project registry entry
    project = {
        "slug": "test-project",
        "path": str(tmp_path),
        "repo": "",
        "name": "Test Project",
        "additional_paths": [],
    }
    return project, tmp_path


def _mock_projects(project_dict):
    """Helper to mock get_all_projects with a single project."""
    return patch(
        "atlas_mcp.registry.get_all_projects", return_value=[project_dict]
    )


# --- resolve_project_path tests ---


class TestResolveProjectPath:
    def test_valid_path(self, fake_project):
        proj, root = fake_project
        with _mock_projects(proj):
            result = resolve_project_path("test-project", "README.md")
            assert result == root / "README.md"

    def test_nested_path(self, fake_project):
        proj, root = fake_project
        with _mock_projects(proj):
            result = resolve_project_path("test-project", "src/main.py")
            assert result == root / "src" / "main.py"

    def test_unknown_slug(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            with pytest.raises(ValueError, match="not found in registry"):
                resolve_project_path("nonexistent", "README.md")

    def test_path_traversal_blocked(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            with pytest.raises(ValueError, match="escapes project boundary"):
                resolve_project_path("test-project", "../../../etc/passwd")

    def test_path_traversal_via_dotdot(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            with pytest.raises(ValueError, match="escapes project boundary"):
                resolve_project_path("test-project", "src/../../etc/passwd")


# --- atlas_read_file tests ---


class TestAtlasReadFile:
    def test_read_existing_file(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("test-project", "README.md"))
            assert "content" in result
            assert "# Test Project" in result["content"]
            assert result["path"] == "README.md"

    def test_read_nested_file(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("test-project", "src/main.py"))
            assert "import os" in result["content"]

    def test_read_missing_file(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("test-project", "nonexistent.txt"))
            assert "error" in result
            assert "not found" in result["error"].lower()

    def test_read_unregistered_project(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("unknown-project", "README.md"))
            assert "error" in result
            assert "not found" in result["error"]

    def test_read_path_traversal_blocked(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(
                atlas_read_file("test-project", "../../../etc/passwd")
            )
            assert "error" in result
            assert "escapes" in result["error"]

    def test_read_large_file(self, fake_project):
        proj, root = fake_project
        # Create a file larger than 1MB
        large_file = root / "large.txt"
        large_file.write_text("x" * 1_100_000)
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("test-project", "large.txt"))
            assert "error" in result
            assert "too large" in result["error"].lower()

    def test_read_binary_file(self, fake_project):
        proj, root = fake_project
        binary_file = root / "binary.dat"
        binary_file.write_bytes(b"\x00\x01\x02\xff\xfe\xfd")
        with _mock_projects(proj):
            result = json.loads(atlas_read_file("test-project", "binary.dat"))
            assert "error" in result
            assert "binary" in result["error"].lower() or "utf-8" in result["error"].lower()


# --- atlas_grep tests ---


class TestAtlasGrep:
    def test_grep_simple_pattern(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("test-project", "import"))
            assert "matches" in result
            matches = result["matches"]
            assert len(matches) >= 1
            assert any(m["content"] == "import os" for m in matches)

    def test_grep_regex_pattern(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("test-project", r"def \w+\(\)"))
            matches = result["matches"]
            assert len(matches) >= 2  # main(), helper(), other()

    def test_grep_with_glob_filter(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(
                atlas_grep("test-project", "def", glob="src/*.py")
            )
            matches = result["matches"]
            # Only src/*.py files, not tests/
            for m in matches:
                assert m["file"].startswith("src/")

    def test_grep_no_matches(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("test-project", "zzz_no_match_zzz"))
            assert result["matches"] == []
            assert result["truncated"] is False

    def test_grep_invalid_project(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("unknown-project", "import"))
            assert "error" in result

    def test_grep_invalid_regex(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("test-project", "[invalid"))
            assert "error" in result
            assert "regex" in result["error"].lower() or "pattern" in result["error"].lower()

    def test_grep_max_results(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_grep("test-project", ".", max_results=3))
            assert result["truncated"] is True
            assert len(result["matches"]) == 3

    def test_grep_returns_line_numbers(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(
                atlas_grep("test-project", "import os", glob="src/main.py")
            )
            matches = result["matches"]
            assert len(matches) == 1
            assert matches[0]["line"] == 1
            assert matches[0]["file"] == "src/main.py"


# --- atlas_glob tests ---


class TestAtlasGlob:
    def test_glob_all_python(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("test-project", "**/*.py"))
            assert "files" in result
            files = result["files"]
            assert "src/main.py" in files
            assert "src/utils.py" in files
            assert "tests/test_main.py" in files

    def test_glob_specific_dir(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("test-project", "src/*.py"))
            files = result["files"]
            assert "src/main.py" in files
            assert "src/utils.py" in files
            # tests/ should not appear
            assert all(not f.startswith("tests/") for f in files)

    def test_glob_markdown(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("test-project", "*.md"))
            assert "README.md" in result["files"]

    def test_glob_no_matches(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("test-project", "*.xyz"))
            assert result["files"] == []
            assert result["count"] == 0

    def test_glob_invalid_project(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("unknown-project", "*.py"))
            assert "error" in result

    def test_glob_count_matches(self, fake_project):
        proj, _ = fake_project
        with _mock_projects(proj):
            result = json.loads(atlas_glob("test-project", "**/*.py"))
            assert result["count"] == len(result["files"])
            assert result["count"] >= 3
