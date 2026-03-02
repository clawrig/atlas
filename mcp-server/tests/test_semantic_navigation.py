"""Tests for semantic code navigation tools: atlas_find_symbol, atlas_symbols_overview,
atlas_find_references, atlas_run_command, and Serena availability detection.

Story 3.3 implementation — regex-based symbol extraction with Serena availability hints.
"""

import json
from unittest.mock import patch

import pytest

from atlas_mcp.server import (
    _extract_body,
    _extract_symbols_from_file,
    _has_serena,
    atlas_find_references,
    atlas_find_symbol,
    atlas_get_project,
    atlas_run_command,
    atlas_symbols_overview,
)


@pytest.fixture
def project_dir(tmp_path):
    """Create a fake project with source files for testing."""
    # Python file
    py_file = tmp_path / "src" / "main.py"
    py_file.parent.mkdir(parents=True)
    py_file.write_text(
        "class UserService:\n"
        "    def __init__(self, db):\n"
        "        self.db = db\n"
        "\n"
        "    def get_user(self, user_id):\n"
        "        return self.db.find(user_id)\n"
        "\n"
        "    async def delete_user(self, user_id):\n"
        "        pass\n"
        "\n"
        "def helper_function():\n"
        "    return UserService(None)\n"
    )

    # TypeScript file
    ts_file = tmp_path / "src" / "client.ts"
    ts_file.write_text(
        "export class ApiClient {\n"
        "    constructor(private baseUrl: string) {}\n"
        "\n"
        "    async fetchData(): Promise<any> {\n"
        "        return fetch(this.baseUrl);\n"
        "    }\n"
        "}\n"
        "\n"
        "export interface Config {\n"
        "    url: string;\n"
        "}\n"
        "\n"
        "export type Handler = (req: Request) => Response;\n"
        "\n"
        "export const createClient = (config: Config) => {\n"
        "    return new ApiClient(config.url);\n"
        "};\n"
    )

    # Non-source file (should be ignored)
    readme = tmp_path / "README.md"
    readme.write_text("# Test Project\n")

    return tmp_path


@pytest.fixture
def project_with_serena(project_dir):
    """Add a .serena config to the project."""
    serena_dir = project_dir / ".serena"
    serena_dir.mkdir()
    (serena_dir / "project.yml").write_text("project_name: test\n")
    return project_dir


def _make_project(slug, path, **kwargs):
    base = {
        "slug": slug,
        "path": str(path),
        "repo": "",
        "name": kwargs.get("name", slug.title()),
        "summary": kwargs.get("summary", ""),
        "tags": [],
        "group": "",
        "additional_paths": [],
    }
    for k, v in kwargs.items():
        if k not in base:
            base[k] = v
    return base


def _mock_projects(*projects):
    return patch("atlas_mcp.server.get_all_projects", return_value=list(projects))


def _mock_find(proj_dict):
    """Mock find_project_by_slug to return a specific project for any slug."""
    return patch("atlas_mcp.server.find_project_by_slug", return_value=proj_dict)


def _mock_find_none():
    """Mock find_project_by_slug to return None (project not found)."""
    return patch("atlas_mcp.server.find_project_by_slug", return_value=None)


def _mock_enrich():
    return patch("atlas_mcp.server.enrich_project", side_effect=lambda p: p)


# --- Serena availability detection (Task 1) ---


class TestSerenaDetection:
    def test_has_serena_true(self, project_with_serena):
        assert _has_serena(str(project_with_serena)) is True

    def test_has_serena_false(self, project_dir):
        assert _has_serena(str(project_dir)) is False

    def test_has_serena_nonexistent_path(self):
        assert _has_serena("/nonexistent/path") is False

    def test_get_project_includes_serena_field(self, project_with_serena):
        proj = _make_project("test", project_with_serena)
        with _mock_projects(proj), _mock_enrich():
            result = json.loads(atlas_get_project("test"))
            assert result["serena_available"] is True

    def test_get_project_serena_false(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_projects(proj), _mock_enrich():
            result = json.loads(atlas_get_project("test"))
            assert result["serena_available"] is False


# --- Symbol extraction helpers ---


class TestSymbolExtraction:
    def test_extract_python_symbols(self, project_dir):
        filepath = project_dir / "src" / "main.py"
        symbols = _extract_symbols_from_file(filepath, project_dir)
        names = [s["name"] for s in symbols]
        assert "UserService" in names
        assert "helper_function" in names

    def test_extract_python_types(self, project_dir):
        filepath = project_dir / "src" / "main.py"
        symbols = _extract_symbols_from_file(filepath, project_dir)
        by_name = {s["name"]: s for s in symbols}
        assert by_name["UserService"]["type"] == "class"
        assert by_name["helper_function"]["type"] == "function"

    def test_extract_typescript_symbols(self, project_dir):
        filepath = project_dir / "src" / "client.ts"
        symbols = _extract_symbols_from_file(filepath, project_dir)
        names = [s["name"] for s in symbols]
        assert "ApiClient" in names
        assert "Config" in names
        assert "Handler" in names
        assert "createClient" in names

    def test_extract_typescript_types(self, project_dir):
        filepath = project_dir / "src" / "client.ts"
        symbols = _extract_symbols_from_file(filepath, project_dir)
        by_name = {s["name"]: s for s in symbols}
        assert by_name["ApiClient"]["type"] == "class"
        assert by_name["Config"]["type"] == "interface"
        assert by_name["Handler"]["type"] == "type"
        assert by_name["createClient"]["type"] == "function"

    def test_extract_ignores_non_source(self, project_dir):
        filepath = project_dir / "README.md"
        symbols = _extract_symbols_from_file(filepath, project_dir)
        assert symbols == []

    def test_extract_body(self, project_dir):
        filepath = project_dir / "src" / "main.py"
        # Line 1 is "class UserService:", body should include the methods
        body = _extract_body(filepath, 1)
        assert "class UserService:" in body
        assert "def __init__" in body

    def test_extract_body_function(self, project_dir):
        # helper_function is at line 11
        filepath = project_dir / "src" / "main.py"
        body = _extract_body(filepath, 11)
        assert "def helper_function" in body
        assert "return UserService" in body


# --- atlas_find_symbol tests (Task 2) ---


class TestAtlasFindSymbol:
    def test_find_by_name(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "UserService"))
            assert result["approach"] == "regex"
            symbols = result["symbols"]
            assert len(symbols) >= 1
            assert symbols[0]["name"] == "UserService"
            assert symbols[0]["type"] == "class"

    def test_find_by_substring(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "helper"))
            symbols = result["symbols"]
            assert any(s["name"] == "helper_function" for s in symbols)

    def test_find_with_body(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "helper_function", include_body=True))
            symbols = result["symbols"]
            assert len(symbols) >= 1
            assert "body" in symbols[0]
            assert "return UserService" in symbols[0]["body"]

    def test_find_no_matches(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "NonexistentSymbol"))
            assert result["symbols"] == []

    def test_find_invalid_project(self):
        with _mock_find_none():
            result = json.loads(atlas_find_symbol("nonexistent", "Foo"))
            assert "error" in result

    def test_serena_hint_when_available(self, project_with_serena):
        proj = _make_project("test", project_with_serena)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "UserService"))
            assert result["serena_available"] is True
            assert "Serena MCP tools" in result["hint"]

    def test_serena_hint_when_unavailable(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_symbol("test", "UserService"))
            assert result["serena_available"] is False
            assert "not configured" in result["hint"]


# --- atlas_symbols_overview tests (Task 3) ---


class TestAtlasSymbolsOverview:
    def test_overview_whole_project(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_symbols_overview("test"))
            assert result["approach"] == "regex"
            files = result["files"]
            # Should have 2 files with symbols (main.py and client.ts)
            assert len(files) == 2

    def test_overview_specific_file(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_symbols_overview("test", "src/main.py"))
            files = result["files"]
            assert len(files) == 1
            assert files[0]["file"] == "src/main.py"
            names = [s["name"] for s in files[0]["symbols"]]
            assert "UserService" in names

    def test_overview_specific_directory(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_symbols_overview("test", "src"))
            files = result["files"]
            assert len(files) == 2

    def test_overview_invalid_project(self):
        with _mock_find_none():
            result = json.loads(atlas_symbols_overview("nonexistent"))
            assert "error" in result

    def test_overview_path_traversal(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_symbols_overview("test", "../../etc"))
            assert "error" in result

    def test_overview_serena_available(self, project_with_serena):
        proj = _make_project("test", project_with_serena)
        with _mock_find(proj):
            result = json.loads(atlas_symbols_overview("test"))
            assert result["serena_available"] is True


# --- atlas_find_references tests (Task 4) ---


class TestAtlasFindReferences:
    def test_find_references_class(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_references("test", "UserService"))
            refs = result["references"]
            # UserService should appear in main.py (definition + usage in helper_function)
            assert len(refs) >= 2
            assert result["approach"] == "text-based"

    def test_find_references_no_matches(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_references("test", "ZzzNonexistent"))
            assert result["references"] == []
            assert result["truncated"] is False

    def test_find_references_max_results(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_references("test", "UserService", max_results=1))
            refs = result["references"]
            assert len(refs) == 1
            assert result["truncated"] is True

    def test_find_references_invalid_project(self):
        with _mock_find_none():
            result = json.loads(atlas_find_references("nonexistent", "Foo"))
            assert "error" in result

    def test_find_references_content_truncated(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_find_references("test", "UserService"))
            for ref in result["references"]:
                assert len(ref["content"]) <= 200


# --- atlas_run_command tests (Task 5) ---


class TestAtlasRunCommand:
    def test_run_simple_command(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", "echo hello"))
            assert result["exit_code"] == 0
            assert "hello" in result["stdout"]
            assert result["timed_out"] is False

    def test_run_command_in_project_root(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", "pwd"))
            assert str(project_dir) in result["stdout"]

    def test_run_command_stderr(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", "ls /nonexistent_path_12345"))
            assert result["exit_code"] != 0
            assert result["stderr"] != ""

    def test_run_command_invalid_project(self):
        with _mock_find_none():
            result = json.loads(atlas_run_command("nonexistent", "echo test"))
            assert "error" in result

    def test_run_command_not_found(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", "nonexistent_command_xyz"))
            assert "error" in result

    def test_run_command_timeout_enforced(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", "sleep 10", timeout=1))
            assert result["timed_out"] is True

    def test_run_command_timeout_clamped(self, project_dir):
        """Timeout should be clamped to MAX_COMMAND_TIMEOUT."""
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            # Just verify it doesn't error with large timeout
            result = json.loads(atlas_run_command("test", "echo ok", timeout=999))
            assert result["exit_code"] == 0

    def test_run_command_empty(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_run_command("test", ""))
            assert "error" in result
