"""Atlas MCP server — exposes project registry as MCP tools."""

import json
import os

from mcp.server.fastmcp import FastMCP

from atlas_mcp.registry import find_project_for_path, get_all_projects

mcp = FastMCP(
    "atlas",
    instructions="Project registry — list, search, and get project metadata managed by Atlas",
)


@mcp.tool()
def atlas_list_projects() -> str:
    """List all registered projects in the Atlas registry.

    Returns a JSON array of projects with fields: slug, path, repo, name, summary, tags, group.
    """
    projects = get_all_projects()
    # Return a clean subset of fields
    result = []
    for p in projects:
        result.append({
            "slug": p.get("slug", ""),
            "path": p.get("path", ""),
            "repo": p.get("repo", ""),
            "name": p.get("name", ""),
            "summary": p.get("summary", ""),
            "tags": p.get("tags", []),
            "group": p.get("group", ""),
        })
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
            # Remove internal fields
            p.pop("additional_paths", None)
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
        return json.dumps(project, indent=2)
    return json.dumps({"project": None})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
