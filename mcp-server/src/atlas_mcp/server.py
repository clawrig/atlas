"""Atlas MCP server — exposes project registry as MCP tools."""

import json
import os
import re
import shlex
import subprocess
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
    instructions=(
        "Project registry — list, search, and get project metadata managed by Atlas. "
        "Use atlas_query as the recommended entry point for cross-project code intelligence: "
        "it auto-selects the best tool (symbol lookup, grep, file read, overview) based on your query. "
        "Individual tools (atlas_find_symbol, atlas_grep, etc.) remain available for direct control."
    ),
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

    Returns JSON with all available fields:
      Registry: slug, path, repo
      Cache (from atlas.yaml): name, summary, tags, group, links, docs, notes, metadata
      Optional: autonomy_level (if configured in atlas.yaml)
      Enriched: provider-contributed fields (e.g., issue tracker data)

    Returns error JSON if project not found.
    """
    projects = get_all_projects()
    for p in projects:
        if p.get("slug") == slug:
            p.pop("additional_paths", None)
            p = enrich_project(p)
            p["serena_available"] = _has_serena(p.get("path", ""))
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


_MAX_OUTPUT_SIZE = 1_048_576  # 1 MB output limit for commands
_MAX_COMMAND_TIMEOUT = 120  # seconds

# Regex patterns for symbol extraction (fallback when Serena unavailable)
_SYMBOL_PATTERNS = {
    "python": [
        (re.compile(r"^(\s*)class\s+(\w+)"), "class"),
        (re.compile(r"^(\s*)(?:async\s+)?def\s+(\w+)"), "function"),
    ],
    "typescript": [
        (re.compile(r"^(\s*)(?:export\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
        (re.compile(r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("), "function"),
        (re.compile(r"^(\s*)(?:export\s+)?interface\s+(\w+)"), "interface"),
        (re.compile(r"^(\s*)(?:export\s+)?type\s+(\w+)\s*="), "type"),
    ],
    "javascript": [
        (re.compile(r"^(\s*)(?:export\s+)?class\s+(\w+)"), "class"),
        (re.compile(r"^(\s*)(?:export\s+)?(?:async\s+)?function\s+(\w+)"), "function"),
        (re.compile(r"^(\s*)(?:export\s+)?(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?\("), "function"),
    ],
}

_EXT_TO_LANG = {
    ".py": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
}


def _has_serena(project_path: str) -> bool:
    """Check if a project has Serena configured (.serena/project.yml exists)."""
    serena_config = Path(project_path).expanduser().resolve() / ".serena" / "project.yml"
    return serena_config.is_file()


def _extract_symbols_from_file(filepath: Path, project_root: Path) -> list[dict]:
    """Extract symbol definitions from a file using regex patterns."""
    ext = filepath.suffix.lower()
    lang = _EXT_TO_LANG.get(ext)
    if not lang:
        return []

    try:
        text = filepath.read_text(encoding="utf-8")
    except (UnicodeDecodeError, PermissionError):
        return []

    patterns = _SYMBOL_PATTERNS.get(lang, [])
    symbols = []
    lines = text.splitlines()

    for i, line in enumerate(lines, start=1):
        for pattern, symbol_type in patterns:
            m = pattern.match(line)
            if m:
                indent = m.group(1)
                name = m.group(2)
                # Determine depth by indentation
                depth = len(indent) // 4 if indent else 0
                symbols.append({
                    "name": name,
                    "type": symbol_type,
                    "file": str(filepath.relative_to(project_root)),
                    "line": i,
                    "depth": depth,
                })
                break

    return symbols


def _iter_source_files(root: Path, project_root: Path):
    """Yield source files under *root*, skipping non-source and _SKIP_DIRS."""
    for filepath in sorted(root.rglob("*")):
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in _EXT_TO_LANG:
            continue
        if any(part in _SKIP_DIRS for part in filepath.relative_to(project_root).parts):
            continue
        yield filepath


@mcp.tool()
def atlas_find_symbol(
    project: str,
    name: str,
    include_body: bool = False,
    depth: int = 0,
) -> str:
    """Find symbol definitions (classes, functions, types) in a registered project.

    Uses regex-based symbol extraction. Reports whether Serena is available
    for richer semantic analysis via its own MCP tools.

    Args:
        project: Project slug from the Atlas registry.
        name: Symbol name or substring to search for (case-sensitive).
        include_body: If true, include the symbol's source code body.
        depth: Maximum nesting depth to include (0 = top-level only).

    Returns JSON with matching symbols and approach used ('regex' or 'semantic').
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    serena = _has_serena(proj["path"])

    # Collect all source files
    matches = []
    files_scanned = 0

    for filepath in _iter_source_files(project_root, project_root):
        files_scanned += 1
        if files_scanned > _MAX_GREP_FILES:
            break

        symbols = _extract_symbols_from_file(filepath, project_root)
        for sym in symbols:
            if name in sym["name"] and sym["depth"] <= depth:
                if include_body:
                    sym["body"] = _extract_body(filepath, sym["line"])
                matches.append(sym)

    return json.dumps({
        "project": project,
        "symbols": matches,
        "approach": "regex",
        "serena_available": serena,
        "hint": "Use Serena MCP tools directly for richer semantic analysis"
        if serena else "Serena not configured for this project",
    })


def _extract_body(filepath: Path, start_line: int, max_lines: int = 50) -> str:
    """Extract the body of a symbol starting at the given line."""
    try:
        lines = filepath.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, PermissionError):
        return ""

    if start_line < 1 or start_line > len(lines):
        return ""

    # Get starting indentation
    start_idx = start_line - 1
    start_text = lines[start_idx]
    base_indent = len(start_text) - len(start_text.lstrip())

    body_lines = [lines[start_idx]]
    for i in range(start_idx + 1, min(start_idx + max_lines, len(lines))):
        line = lines[i]
        # Empty lines are part of the body
        if line.strip() == "":
            body_lines.append(line)
            continue
        # Line at same or lesser indentation (and non-empty) means end of body
        current_indent = len(line) - len(line.lstrip())
        if current_indent <= base_indent:
            break
        body_lines.append(line)

    return "\n".join(body_lines)


@mcp.tool()
def atlas_symbols_overview(project: str, path: str = "") -> str:
    """Get an overview of symbols (classes, functions, types) in a project or file.

    Uses regex-based extraction. Reports whether Serena is available
    for richer semantic analysis via its own MCP tools.

    Args:
        project: Project slug from the Atlas registry.
        path: Relative file or directory path within the project. Empty for project root.

    Returns JSON with symbol overview grouped by file.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    serena = _has_serena(proj["path"])

    target = (project_root / path).resolve() if path else project_root
    if not target.is_relative_to(project_root):
        return json.dumps({"error": f"Path '{path}' escapes project boundary"})

    files_with_symbols = []
    files_scanned = 0

    if target.is_file():
        file_list = [target] if target.suffix.lower() in _EXT_TO_LANG else []
    else:
        file_list = _iter_source_files(target, project_root)

    for filepath in file_list:
        files_scanned += 1
        if files_scanned > _MAX_GREP_FILES:
            break

        symbols = _extract_symbols_from_file(filepath, project_root)
        if symbols:
            files_with_symbols.append({
                "file": str(filepath.relative_to(project_root)),
                "symbols": symbols,
            })

    return json.dumps({
        "project": project,
        "path": path or ".",
        "files": files_with_symbols,
        "approach": "regex",
        "serena_available": serena,
        "hint": "Use Serena MCP tools directly for richer semantic analysis"
        if serena else "Serena not configured for this project",
    })


@mcp.tool()
def atlas_find_references(project: str, symbol: str, max_results: int = 50) -> str:
    """Find references to a symbol across a registered project's codebase.

    Falls back to text-based grep when Serena is not available.
    Reports whether Serena is available for richer semantic reference finding.

    Args:
        project: Project slug from the Atlas registry.
        symbol: Symbol name to search references for.
        max_results: Maximum number of references to return (default 50).

    Returns JSON with reference locations and approach used.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    serena = _has_serena(proj["path"])

    # Text-based reference finding using word boundary matching
    try:
        pattern = re.compile(r"\b" + re.escape(symbol) + r"\b")
    except re.error:
        return json.dumps({"error": f"Invalid symbol name for pattern: {symbol}"})

    references = []
    files_scanned = 0

    for filepath in _iter_source_files(project_root, project_root):
        files_scanned += 1
        if files_scanned > _MAX_GREP_FILES:
            break

        try:
            text = filepath.read_text(encoding="utf-8")
        except (UnicodeDecodeError, PermissionError):
            continue

        for i, line in enumerate(text.splitlines(), start=1):
            if pattern.search(line):
                references.append({
                    "file": str(filepath.relative_to(project_root)),
                    "line": i,
                    "content": line.rstrip()[:200],
                })
                if len(references) >= max_results:
                    return json.dumps({
                        "project": project,
                        "symbol": symbol,
                        "references": references,
                        "truncated": True,
                        "approach": "text-based",
                        "serena_available": serena,
                        "hint": "Use Serena MCP tools for semantic reference finding"
                        if serena else "Serena not configured — results are text-based matches",
                    })

    return json.dumps({
        "project": project,
        "symbol": symbol,
        "references": references,
        "truncated": False,
        "approach": "text-based",
        "serena_available": serena,
        "hint": "Use Serena MCP tools for semantic reference finding"
        if serena else "Serena not configured — results are text-based matches",
    })


# --- Query classification helpers for atlas_query (Story 3.4) ---

# File extensions that indicate a path-like token
_FILE_EXTENSIONS = frozenset({
    ".py", ".ts", ".tsx", ".js", ".jsx", ".mjs", ".json", ".yaml", ".yml",
    ".toml", ".md", ".txt", ".cfg", ".ini", ".env", ".sh", ".html", ".css",
})

# PascalCase: >=2 words starting with uppercase, e.g. UserService, ApiClient
_RE_PASCAL_CASE = re.compile(r"^[A-Z][a-z]+(?:[A-Z][a-z]+)+$")
# snake_case identifier with at least one underscore: get_user, my_func
_RE_SNAKE_CASE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)+$")


def _looks_like_file_path(query: str) -> bool:
    """Check if the query contains something that looks like a file path."""
    for token in query.split():
        if "/" in token or "\\" in token:
            return True
        if any(token.endswith(ext) for ext in _FILE_EXTENSIONS):
            return True
    return False


def _looks_like_symbol_name(query: str) -> bool:
    """Check if the query contains a PascalCase or snake_case identifier."""
    for token in query.split():
        clean = token.strip("\"'`,;:()[]{}?!")
        if _RE_PASCAL_CASE.match(clean) or _RE_SNAKE_CASE.match(clean):
            return True
    return False


def _classify_query(query: str) -> str:
    """Classify a natural-language query into a tool category.

    Returns one of: "file", "symbol", "overview", "pattern".
    """
    q = query.lower().strip()

    # Overview queries first — "list symbols in src/" should not be "file"
    if any(kw in q for kw in (
        "overview", "structure", "what's in", "list symbols", "symbols in",
    )):
        return "overview"

    # File queries — explicit paths or file-read intent
    if _looks_like_file_path(query):
        return "file"
    if any(kw in q for kw in ("read ", "show ", "contents of ", "cat ")):
        return "file"

    # Symbol queries — code structure terms or identifier-like tokens
    if any(kw in q for kw in (
        "class ", "function ", "def ", "method ", "constructor",
        "interface ", "type ",
    )):
        return "symbol"
    if _looks_like_symbol_name(query):
        return "symbol"

    # Pattern queries — search/grep intent
    if any(kw in q for kw in (
        "import", "find all", "grep", "search", "files containing",
        "where is", "usage", "references",
    )):
        return "pattern"

    # Default: pattern (safest fallback — always produces results)
    return "pattern"


def _extract_symbol_name(query: str) -> str:
    """Extract the most likely symbol name from a query string."""
    # Try PascalCase / snake_case tokens first
    for token in query.split():
        clean = token.strip("\"'`,;:()[]{}?!")
        if _RE_PASCAL_CASE.match(clean) or _RE_SNAKE_CASE.match(clean):
            return clean

    # Fall back to last meaningful token (skip common verbs)
    skip = {"find", "the", "class", "function", "def", "method", "constructor",
            "interface", "type", "of", "in", "for", "a", "an", "show", "get",
            "what", "is", "where", "how"}
    tokens = [t.strip("\"'`,;:()[]{}?!") for t in query.split()]
    for token in reversed(tokens):
        if token.lower() not in skip and len(token) > 1:
            return token
    return query.strip()


def _extract_file_path(query: str) -> str | None:
    """Extract a file path from a query string, if present."""
    for token in query.split():
        if "/" in token or "\\" in token:
            return token.strip("\"'`,;:()[]{}?!")
        if any(token.endswith(ext) for ext in _FILE_EXTENSIONS):
            return token.strip("\"'`,;:()[]{}?!")
    return None


@mcp.tool()
def atlas_query(project: str, query: str, max_results: int = 20) -> str:
    """Unified query entry point — automatically selects the best tool for your query.

    Classifies the query and routes to the appropriate Atlas tool:
    - Symbol queries → atlas_find_symbol (code structure, definitions)
    - Pattern queries → atlas_grep (text search across files)
    - File queries → atlas_read_file or atlas_glob
    - Overview queries → atlas_symbols_overview

    Falls back gracefully when Serena is unavailable.

    Args:
        project: Project slug from the Atlas registry.
        query: Natural-language query describing what you're looking for.
        max_results: Maximum number of results to return (default 20).

    Returns JSON with query_type, tool_used, results, and metadata.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    query_type = _classify_query(query)
    serena = _has_serena(proj.get("path", ""))

    if query_type == "file":
        file_path = _extract_file_path(query)
        if file_path:
            # Looks like a specific file — read it
            inner = atlas_read_file(project, file_path)
            tool_used = "atlas_read_file"
        else:
            # No clear path — return helpful error instead of expensive **/* glob
            inner = json.dumps({
                "error": "No file path detected in query. Use atlas_read_file with a specific path, "
                "or atlas_glob with a pattern like '*.py'.",
            })
            tool_used = "atlas_read_file"

    elif query_type == "symbol":
        symbol_name = _extract_symbol_name(query)
        inner = atlas_find_symbol(project, symbol_name, include_body=True)
        tool_used = "atlas_find_symbol"

    elif query_type == "overview":
        path = _extract_file_path(query) or ""
        inner = atlas_symbols_overview(project, path)
        tool_used = "atlas_symbols_overview"

    else:  # "pattern"
        # Use the query as the grep pattern, extracting a useful search term
        search_term = _extract_symbol_name(query)
        inner = atlas_grep(project, re.escape(search_term), max_results=max_results)
        tool_used = "atlas_grep"

    # Parse inner result and wrap
    try:
        results = json.loads(inner)
    except json.JSONDecodeError:
        results = {"raw": inner}

    return json.dumps({
        "project": project,
        "query": query,
        "query_type": query_type,
        "tool_used": tool_used,
        "results": results,
        "serena_available": serena,
        "fallback_used": query_type == "symbol",  # always regex-based (no direct Serena integration)
    })


@mcp.tool()
def atlas_run_command(project: str, command: str, timeout: int = 30) -> str:
    """Run a shell command in a registered project's root directory.

    Use when MCP and semantic tools are insufficient. The command runs
    with the project root as the working directory.

    Args:
        project: Project slug from the Atlas registry.
        command: Command to execute (split by shell, not passed to shell).
        timeout: Timeout in seconds (default 30, max 120).

    Returns JSON with stdout, stderr, exit_code, and timed_out status.
    """
    proj = find_project_by_slug(project)
    if not proj:
        return json.dumps({"error": f"Project '{project}' not found in registry"})

    project_root = Path(proj["path"]).expanduser().resolve()
    if not project_root.is_dir():
        return json.dumps({"error": f"Project path does not exist: {project_root}"})

    # Enforce timeout limits
    timeout = max(1, min(timeout, _MAX_COMMAND_TIMEOUT))

    try:
        args = shlex.split(command)
    except ValueError as e:
        return json.dumps({"error": f"Invalid command syntax: {e}"})

    if not args:
        return json.dumps({"error": "Empty command"})

    try:
        result = subprocess.run(
            args,
            cwd=str(project_root),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        stdout = result.stdout[:_MAX_OUTPUT_SIZE]
        stderr = result.stderr[:_MAX_OUTPUT_SIZE]
        return json.dumps({
            "project": project,
            "stdout": stdout,
            "stderr": stderr,
            "exit_code": result.returncode,
            "timed_out": False,
        })
    except subprocess.TimeoutExpired:
        return json.dumps({
            "project": project,
            "stdout": "",
            "stderr": "",
            "exit_code": -1,
            "timed_out": True,
            "timeout": timeout,
        })
    except FileNotFoundError:
        return json.dumps({"error": f"Command not found: {args[0]}"})
    except OSError as e:
        return json.dumps({"error": f"Command execution failed: {e}"})


def main():
    mcp.run()


if __name__ == "__main__":
    main()
