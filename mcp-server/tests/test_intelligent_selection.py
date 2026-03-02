"""Tests for intelligent tool selection: atlas_query and query classification.

Story 3.4 implementation — heuristic query classification with tool routing.
"""

import json
from unittest.mock import patch

import pytest

from atlas_mcp.server import (
    _classify_query,
    _extract_file_path,
    _extract_symbol_name,
    _looks_like_file_path,
    _looks_like_symbol_name,
    atlas_query,
)


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


def _mock_find(proj_dict):
    return patch("atlas_mcp.server.find_project_by_slug", return_value=proj_dict)


def _mock_find_none():
    return patch("atlas_mcp.server.find_project_by_slug", return_value=None)


# --- Helper function tests ---


class TestLooksLikeFilePath:
    def test_slash_path(self):
        assert _looks_like_file_path("read src/main.py") is True

    def test_extension(self):
        assert _looks_like_file_path("show config.yaml") is True

    def test_no_path(self):
        assert _looks_like_file_path("find UserService class") is False

    def test_backslash(self):
        assert _looks_like_file_path("read src\\main.py") is True


class TestLooksLikeSymbolName:
    def test_pascal_case(self):
        assert _looks_like_symbol_name("find UserService") is True

    def test_snake_case(self):
        assert _looks_like_symbol_name("find get_user") is True

    def test_single_word(self):
        assert _looks_like_symbol_name("hello") is False

    def test_all_lowercase(self):
        assert _looks_like_symbol_name("find all imports") is False

    def test_pascal_with_punctuation(self):
        assert _looks_like_symbol_name("what is ApiClient?") is True


# --- Query classification tests (Task 2) ---


class TestClassifyQuery:
    def test_file_path(self):
        assert _classify_query("read src/main.py") == "file"

    def test_file_extension(self):
        assert _classify_query("show config.yaml") == "file"

    def test_file_read_keyword(self):
        assert _classify_query("read the configuration file") == "file"

    def test_file_contents_keyword(self):
        assert _classify_query("contents of README") == "file"

    def test_overview(self):
        assert _classify_query("overview of the project") == "overview"

    def test_list_symbols(self):
        assert _classify_query("list symbols in src/") == "overview"

    def test_symbol_class(self):
        assert _classify_query("find the class UserService") == "symbol"

    def test_symbol_function(self):
        assert _classify_query("function get_all_projects") == "symbol"

    def test_symbol_pascal_case(self):
        assert _classify_query("find ApiClient") == "symbol"

    def test_symbol_snake_case(self):
        assert _classify_query("find extract_body") == "symbol"

    def test_pattern_import(self):
        assert _classify_query("find all files importing os") == "pattern"

    def test_pattern_grep(self):
        assert _classify_query("grep for TODO comments") == "pattern"

    def test_pattern_search(self):
        assert _classify_query("search for error handling") == "pattern"

    def test_default_is_pattern(self):
        assert _classify_query("something ambiguous here") == "pattern"

    def test_priority_file_over_symbol(self):
        # A path with an extension should be "file" even if it contains a symbol-like name
        assert _classify_query("UserService.py") == "file"

    def test_priority_file_over_pattern(self):
        assert _classify_query("search in src/main.py") == "file"


class TestExtractSymbolName:
    def test_pascal_case(self):
        assert _extract_symbol_name("find UserService class") == "UserService"

    def test_snake_case(self):
        assert _extract_symbol_name("find get_user function") == "get_user"

    def test_fallback_last_token(self):
        assert _extract_symbol_name("find the foobar") == "foobar"

    def test_strips_punctuation(self):
        assert _extract_symbol_name("what is ApiClient?") == "ApiClient"


class TestExtractFilePath:
    def test_slash_path(self):
        assert _extract_file_path("read src/main.py") == "src/main.py"

    def test_extension(self):
        assert _extract_file_path("show config.yaml") == "config.yaml"

    def test_no_path(self):
        assert _extract_file_path("find all classes") is None


# --- atlas_query integration tests (Task 1 & 4) ---


class TestAtlasQuery:
    def test_invalid_project(self):
        with _mock_find_none():
            result = json.loads(atlas_query("nonexistent", "find Foo"))
            assert "error" in result

    def test_symbol_query_routes_to_find_symbol(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_query("test", "find UserService"))
            assert result["query_type"] == "symbol"
            assert result["tool_used"] == "atlas_find_symbol"
            assert "results" in result
            # Should find the symbol
            symbols = result["results"].get("symbols", [])
            assert any(s["name"] == "UserService" for s in symbols)

    def test_pattern_query_routes_to_grep(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_query("test", "search for db"))
            assert result["query_type"] == "pattern"
            assert result["tool_used"] == "atlas_grep"

    def test_file_query_routes_to_read_file(self, project_dir):
        proj = _make_project("test", project_dir)
        target = project_dir / "src" / "main.py"
        with _mock_find(proj), \
             patch("atlas_mcp.server.resolve_project_path", return_value=target):
            result = json.loads(atlas_query("test", "read src/main.py"))
            assert result["query_type"] == "file"
            assert result["tool_used"] == "atlas_read_file"
            assert "content" in result["results"]

    def test_overview_query_routes_to_symbols_overview(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_query("test", "overview of symbols"))
            assert result["query_type"] == "overview"
            assert result["tool_used"] == "atlas_symbols_overview"

    def test_serena_available_field(self, project_with_serena):
        proj = _make_project("test", project_with_serena)
        with _mock_find(proj):
            result = json.loads(atlas_query("test", "find ApiClient"))
            assert result["serena_available"] is True
            assert result["fallback_used"] is True  # regex-based, not real Serena

    def test_serena_unavailable(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            result = json.loads(atlas_query("test", "find ApiClient"))
            assert result["serena_available"] is False

    def test_fallback_used_only_for_symbol(self, project_dir):
        proj = _make_project("test", project_dir)
        with _mock_find(proj):
            # "grep for TODO" is pattern, not symbol
            result = json.loads(atlas_query("test", "grep for TODO"))
            assert result["query_type"] == "pattern"
            assert result["fallback_used"] is False


# --- Fixtures (reused from test_semantic_navigation) ---


@pytest.fixture
def project_dir(tmp_path):
    """Create a fake project with source files for testing."""
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
    )

    return tmp_path


@pytest.fixture
def project_with_serena(project_dir):
    """Add a .serena config to the project."""
    serena_dir = project_dir / ".serena"
    serena_dir.mkdir()
    (serena_dir / "project.yml").write_text("project_name: test\n")
    return project_dir
