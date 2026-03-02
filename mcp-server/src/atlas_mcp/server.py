"""Atlas MCP server — exposes project registry as MCP tools."""

import json
import os
import re
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from atlas_mcp.providers import enrich_project, list_providers
from atlas_mcp.registry import (
    find_project_by_slug,
    find_project_for_path,
    get_all_projects,
    resolve_project_path,
)

mcp = FastMCP(
    "atlas",
    instructions="Project registry — list, search, and get project metadata managed by Atlas",
)


@mcp.tool()
def atlas_list_projects(enrich: bool = False) -> str:
    """List all registered projects in the Atlas registry.

    Args:
        enrich: If true, include data from registered providers (e.g. issue trackers).
                This is heavier — reads per-project files for each provider.

    Returns a JSON array of projects with fields: slug, path, repo, name, summary, tags, group.
    """
    projects = get_all_projects()
    result = []
    for p in projects:
        if enrich:
            p = enrich_project(p)
        entry = {
            "slug": p.get("slug", ""),
            "path": p.get("path", ""),
            "repo": p.get("repo", ""),
            "name": p.get("name", ""),
            "summary": p.get("summary", ""),
            "tags": p.get("tags", []),
            "group": p.get("group", ""),
        }
        # Include provider fields when enriched
        if enrich:
            for prov in list_providers():
                field = prov["field_name"]
                if field in p:
                    entry[field] = p[field]
        result.append(entry)
    return json.dumps(result, indent=2)


@mcp.tool()
def atlas_get_project(slug: str) -> str:
    """Get full metadata for a project by its slug.

    Args:
        slug: The project slug (e.g., 'digital-web-sdk')

    Returns JSON with all fields from atlas.yaml + registry (path, repo).
    Returns error JSON if project not found.
    """
    projects = get_all_projects()
    for p in projects:
        if p.get("slug") == slug:
            p.pop("additional_paths", None)
            p = enrich_project(p)
            return json.dumps(p, indent=2)
    return json.dumps({"error": f"Project '{slug}' not found"})


@mcp.tool()
def atlas_search_projects(query: str = "", tag: str = "", group: str = "") -> str:
    """Search projects by name/slug, tag, or group.

    Args:
        query: Text to match against slug, name, or summary (case-insensitive substring)
        tag: Filter to projects with this tag
        group: Filter to projects in this group

    At least one parameter should be provided. Returns a JSON array of matching projects.
    """
    projects = get_all_projects()
    results = []

    for p in projects:
        # Apply filters (all specified filters must match)
        if query:
            q = query.lower()
            searchable = f"{p.get('slug', '')} {p.get('name', '')} {p.get('summary', '')}".lower()
            if q not in searchable:
                continue

        if tag:
            tags = p.get("tags", [])
            if isinstance(tags, list) and tag.lower() not in [t.lower() for t in tags]:
                continue

        if group:
            if p.get("group", "").lower() != group.lower():
                continue

        results.append({
            "slug": p.get("slug", ""),
            "path": p.get("path", ""),
            "repo": p.get("repo", ""),
            "name": p.get("name", ""),
            "summary": p.get("summary", ""),
            "tags": p.get("tags", []),
            "group": p.get("group", ""),
        })

    return json.dumps(results, indent=2)


@mcp.tool()
def atlas_get_current_project(path: str = "") -> str:
    """Detect which project a given filesystem path belongs to.

    Args:
        path: Filesystem path to check. Defaults to the server's working directory.

    Uses Atlas path matching: exact match > child match (deepest wins) > additional paths.
    Returns JSON with project data, or {"project": null} if no match.
    """
    target = path if path else os.getcwd()
    project = find_project_for_path(target)
    if project:
        project.pop("additional_paths", None)
        project = enrich_project(project)
        return json.dumps(project, indent=2)
    return json.dumps({"project": None})


@mcp.tool()
def atlas_list_providers() -> str:
    """List all registered Atlas providers.

    Providers are plugins that contribute extra per-project data (e.g. issue trackers).
    Returns a JSON array of provider definitions with: name, description, version,
    project_file, field_name.
    """
    providers = list_providers()
    return json.dumps(providers, indent=2)


_MAX_FILE_SIZE = 1_048_576  # 1 MB
_MAX_GREP_FILES = 10_000  # Safety limit for recursive file enumeration
_SKIP_DIRS = frozenset({
    ".git", "node_modules", "__pycache__", ".venv", "venv", ".tox",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", "dist", "build",
})


@mcp.tool()
def atlas_read_file(project: str, path: str) -> str:
    """Read a file from a registered project.

    Args:
        project: Project slug from the Atlas registry.
        path: File path relative to the project root.

    Returns JSON with 'content' on success or 'error' on failure.
    """
    try:
        target = resolve_project_path(project, path)
    except ValueError as e:
        return json.dumps({"error": str(e)})

    if not target.is_file():
        return json.dumps({"error": f"File not found: {path}"})

    size = target.stat().st_size
    if size > _MAX_FILE_SIZE:
        return json.dumps({
            "error": f"File too large ({size} bytes, max {_MAX_FILE_SIZE})",
            "size": size,
        })

    try:
        content = target.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return json.dumps({"error": f"Binary or non-UTF-8 file: {path}"})

    return json.dumps({"content": content, "path": path, "size": size})


@mcp.tool()
def atlas_grep(
    project: str,
    pattern: str,
    file_glob: str = "",
    max_results: int = 100,
) -> str:
    """Search file contents in a registered project using a regex pattern.

    Args:
        project: Project slug from the Atlas registry.
        pattern: Regular expression pattern to search for.
        file_glob: Optional glob pattern to filter files (e.g., '*.py', 'src/**/*.ts').
        max_results: Maximum number of matching lines to return (default 100).

    Returns JSON with matches (file, line, content) and project slug.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    try:
        regex = re.compile(pattern)
    except re.error as e:
        return json.dumps({"error": f"Invalid regex pattern: {e}"})

    # Collect files to search
    if file_glob:
        files = sorted(project_root.glob(file_glob))
    else:
        files = sorted(f for f in project_root.rglob("*") if f.is_file())

    matches = []
    files_scanned = 0

    for filepath in files:
        if not filepath.is_file():
            continue
        if any(part in _SKIP_DIRS for part in filepath.relative_to(project_root).parts):
            continue

        files_scanned += 1
        if files_scanned > _MAX_GREP_FILES:
            return json.dumps({
                "matches": matches,
                "truncated": True,
                "reason": f"File scan limit reached ({_MAX_GREP_FILES} files). Use file_glob to narrow search.",
            })

        try:
            text = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            if regex.search(line):
                matches.append({
                    "file": str(filepath.relative_to(project_root)),
                    "line": i,
                    "content": line.rstrip(),
                })
                if len(matches) >= max_results:
                    return json.dumps({
                        "project": project,
                        "matches": matches,
                        "truncated": True,
                        "max_results": max_results,
                    })

    return json.dumps({"project": project, "matches": matches, "truncated": False})


@mcp.tool()
def atlas_glob(project: str, pattern: str) -> str:
    """List files in a registered project matching a glob pattern.

    Args:
        project: Project slug from the Atlas registry.
        pattern: Glob pattern to match (e.g., 'src/**/*.ts', '*.py').

    Returns JSON array of relative file paths sorted alphabetically.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    files = sorted(project_root.glob(pattern))

    results = []
    for f in files:
        if not f.is_file():
            continue
        rel = f.relative_to(project_root)
        if any(part in _SKIP_DIRS for part in rel.parts):
            continue
        if not f.resolve().is_relative_to(project_root):
            continue
        results.append(str(rel))

    return json.dumps({"project": project, "files": results, "count": len(results)})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
