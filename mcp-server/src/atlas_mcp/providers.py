"""Provider system for Atlas — plugins register data they contribute to project metadata.

Providers are YAML files in ~/.claude/atlas/providers/<plugin>.yaml that declare
what per-project file to read and under which key to expose the data.

Two provider types:
- file (default): reads a per-project file from the project directory
- mcp_query: queries an HTTP endpoint for live data (e.g., mcp_agent_mail inbox count)
"""

import json
import os
import urllib.request
import urllib.error
from pathlib import Path

from atlas_mcp.registry import _parse_project_yaml, expand_path

PROVIDERS_DIR = Path.home() / ".claude" / "atlas" / "providers"
MCP_QUERY_TIMEOUT_SEC = 2


def list_providers() -> list[dict]:
    """Read all provider definitions from PROVIDERS_DIR.

    Returns list of dicts with: name, description, version, project_file|endpoint, field_name.
    """
    if not PROVIDERS_DIR.is_dir():
        return []

    providers = []
    for f in sorted(PROVIDERS_DIR.glob("*.yaml")):
        text = f.read_text(encoding="utf-8")
        parsed = _parse_project_yaml(text)
        # Require essential fields
        if not parsed.get("name") or not parsed.get("field_name"):
            continue
        ptype = parsed.get("type", "file")
        if ptype == "file" and not parsed.get("project_file"):
            continue
        if ptype == "mcp_query" and not parsed.get("endpoint"):
            continue
        providers.append(parsed)
    return providers


def read_provider_data(provider: dict, project_path: Path) -> dict | list | None:
    """Read a provider's per-project file and return parsed content.

    Args:
        provider: Provider definition dict (must have 'project_file').
        project_path: Resolved path to the project root.

    Returns parsed YAML content or None if file doesn't exist.
    """
    project_file = project_path / provider["project_file"]
    if not project_file.is_file():
        return None

    text = project_file.read_text(encoding="utf-8")
    return _parse_project_yaml(text)


def query_mcp_provider(provider: dict, project_path: Path) -> str | int | None:
    """Query an MCP HTTP endpoint for live data.

    The provider's 'resource' field is a URL template with placeholders:
    - {project_path}: absolute path to the project
    - {agent}: current user name

    Returns the value or None if the server is unavailable.
    """
    endpoint = provider.get("endpoint", "")
    resource = provider.get("resource", "")

    if not endpoint or not resource:
        return None

    # Expand placeholders
    agent = os.environ.get("USER", "unknown")
    url = resource.replace("{agent}", agent).replace("{project_path}", str(project_path))

    # If resource is a relative path, prepend endpoint
    if not url.startswith("http"):
        url = f"{endpoint.rstrip('/')}/{url.lstrip('/')}"

    try:
        req = urllib.request.Request(url, method="GET")
        resp = urllib.request.urlopen(req, timeout=MCP_QUERY_TIMEOUT_SEC)
        result = json.loads(resp.read())
        # Return message count from various response formats
        if isinstance(result, dict):
            if "messages" in result:
                return len(result["messages"])
            return result.get("total", result.get("count", result))
        return result
    except (urllib.error.URLError, OSError, json.JSONDecodeError):
        return None


def enrich_project(project: dict) -> dict:
    """Enrich a project dict with data from all registered providers.

    For each provider, reads the provider's data source and adds it
    under the provider's field_name key.
    """
    providers = list_providers()
    if not providers:
        return project

    raw_path = project.get("path")
    if not raw_path:
        return project

    project_path = expand_path(raw_path).resolve()
    if not project_path.is_dir():
        return project

    for prov in providers:
        ptype = prov.get("type", "file")

        if ptype == "mcp_query":
            data = query_mcp_provider(prov, project_path)
            if data is not None:
                project[prov["field_name"]] = data
        else:
            # Default: file-based provider
            data = read_provider_data(prov, project_path)
            if data is not None:
                field = prov["field_name"]
                if isinstance(data, dict) and field in data:
                    project[field] = data[field]
                else:
                    project[field] = data

    return project
