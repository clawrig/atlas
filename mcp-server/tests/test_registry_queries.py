"""Tests for project registry query tools: atlas_list_projects, atlas_get_project, atlas_search_projects.

Story 3.2 verification — these tools pre-existed; tests confirm AC compliance.
"""

import json
from unittest.mock import patch

import pytest

from atlas_mcp.server import atlas_get_project, atlas_list_projects, atlas_search_projects


def _make_project(slug, path="/tmp/test", **kwargs):
    """Create a project dict with defaults."""
    base = {
        "slug": slug,
        "path": path,
        "repo": kwargs.get("repo", ""),
        "name": kwargs.get("name", slug.title()),
        "summary": kwargs.get("summary", f"Summary for {slug}"),
        "tags": kwargs.get("tags", []),
        "group": kwargs.get("group", ""),
        "additional_paths": [],
    }
    # Add any extra fields (autonomy_level, links, docs, etc.)
    for k, v in kwargs.items():
        if k not in base:
            base[k] = v
    return base


def _mock_projects(*projects):
    """Mock get_all_projects where it's imported in server.py."""
    return patch("atlas_mcp.server.get_all_projects", return_value=list(projects))


def _mock_providers(providers=None):
    return patch("atlas_mcp.server.list_providers", return_value=providers or [])


def _mock_enrich():
    return patch("atlas_mcp.server.enrich_project", side_effect=lambda p: p)


# --- atlas_list_projects tests (AC#1) ---


class TestAtlasListProjects:
    def test_returns_required_fields(self):
        """AC#1: all projects returned with slug, name, path, summary."""
        proj = _make_project("myapp", name="My App", summary="A test app", path="/projects/myapp")
        with _mock_projects(proj), _mock_providers():
            result = json.loads(atlas_list_projects())
            assert len(result) == 1
            entry = result[0]
            assert entry["slug"] == "myapp"
            assert entry["name"] == "My App"
            assert entry["path"] == "/projects/myapp"
            assert entry["summary"] == "A test app"

    def test_multiple_projects(self):
        """AC#1: ALL registered projects returned."""
        p1 = _make_project("alpha", name="Alpha")
        p2 = _make_project("beta", name="Beta")
        p3 = _make_project("gamma", name="Gamma")
        with _mock_projects(p1, p2, p3), _mock_providers():
            result = json.loads(atlas_list_projects())
            assert len(result) == 3
            slugs = {p["slug"] for p in result}
            assert slugs == {"alpha", "beta", "gamma"}

    def test_includes_tags_and_group(self):
        proj = _make_project("web-sdk", tags=["frontend", "sdk"], group="digital")
        with _mock_projects(proj), _mock_providers():
            result = json.loads(atlas_list_projects())
            entry = result[0]
            assert entry["tags"] == ["frontend", "sdk"]
            assert entry["group"] == "digital"

    def test_empty_registry(self):
        with _mock_projects(), _mock_providers():
            result = json.loads(atlas_list_projects())
            assert result == []


# --- atlas_get_project tests (AC#2) ---


class TestAtlasGetProject:
    def test_returns_full_metadata(self):
        """AC#2: full metadata including autonomy_level, links, docs."""
        proj = _make_project(
            "myapp",
            name="My App",
            repo="https://github.com/test/myapp",
            tags=["python"],
            group="tools",
            autonomy_level="supervised",
            links={"repo": "https://github.com/test/myapp"},
            docs={"readme": "docs/README.md"},
        )
        with _mock_projects(proj), _mock_enrich():
            result = json.loads(atlas_get_project("myapp"))
            assert result["slug"] == "myapp"
            assert result["name"] == "My App"
            assert result["path"] == "/tmp/test"
            assert result["repo"] == "https://github.com/test/myapp"
            assert result["tags"] == ["python"]
            assert result["group"] == "tools"
            assert result["autonomy_level"] == "supervised"
            assert result["links"] == {"repo": "https://github.com/test/myapp"}
            assert result["docs"] == {"readme": "docs/README.md"}

    def test_project_not_found(self):
        proj = _make_project("other")
        with _mock_projects(proj):
            result = json.loads(atlas_get_project("nonexistent"))
            assert "error" in result

    def test_minimal_project_still_works(self):
        """AC#4: only slug and path required — no language-specific fields."""
        proj = {
            "slug": "minimal",
            "path": "/tmp/minimal",
            "repo": "",
            "additional_paths": [],
        }
        with _mock_projects(proj), _mock_enrich():
            result = json.loads(atlas_get_project("minimal"))
            assert result["slug"] == "minimal"
            assert result["path"] == "/tmp/minimal"
            assert "error" not in result


# --- atlas_search_projects tests (AC#3) ---


class TestAtlasSearchProjects:
    def test_search_by_keyword(self):
        """AC#3: search by keyword matches slug/name/summary."""
        p1 = _make_project("web-sdk", name="Web SDK", summary="Browser client")
        p2 = _make_project("api-server", name="API Server", summary="Backend REST")
        with _mock_projects(p1, p2):
            result = json.loads(atlas_search_projects(query="web"))
            assert len(result) == 1
            assert result[0]["slug"] == "web-sdk"

    def test_search_by_tag(self):
        p1 = _make_project("frontend", tags=["ui", "react"])
        p2 = _make_project("backend", tags=["api", "python"])
        with _mock_projects(p1, p2):
            result = json.loads(atlas_search_projects(tag="react"))
            assert len(result) == 1
            assert result[0]["slug"] == "frontend"

    def test_search_by_group(self):
        p1 = _make_project("sdk", group="digital")
        p2 = _make_project("docs", group="marketing")
        with _mock_projects(p1, p2):
            result = json.loads(atlas_search_projects(group="digital"))
            assert len(result) == 1
            assert result[0]["slug"] == "sdk"

    def test_search_case_insensitive(self):
        proj = _make_project("MyApp", name="My Application")
        with _mock_projects(proj):
            result = json.loads(atlas_search_projects(query="MYAPP"))
            assert len(result) == 1

    def test_search_no_matches(self):
        proj = _make_project("test")
        with _mock_projects(proj):
            result = json.loads(atlas_search_projects(query="zzz_nothing"))
            assert result == []

    def test_search_combined_filters(self):
        """Multiple filters must all match."""
        p1 = _make_project("web-sdk", tags=["sdk"], group="digital")
        p2 = _make_project("api", tags=["sdk"], group="tools")
        with _mock_projects(p1, p2):
            result = json.loads(atlas_search_projects(tag="sdk", group="digital"))
            assert len(result) == 1
            assert result[0]["slug"] == "web-sdk"


# --- Minimal project tests (AC#4) ---


class TestMinimalProject:
    def test_list_with_minimal_fields(self):
        """AC#4: no language-specific metadata required."""
        proj = {
            "slug": "bare",
            "path": "/tmp/bare",
            "repo": "",
            "additional_paths": [],
        }
        with _mock_projects(proj), _mock_providers():
            result = json.loads(atlas_list_projects())
            assert len(result) == 1
            entry = result[0]
            assert entry["slug"] == "bare"
            assert entry["path"] == "/tmp/bare"
            # Missing fields should default to empty, not error
            assert entry["name"] == ""
            assert entry["summary"] == ""
            assert entry["tags"] == []
