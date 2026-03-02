"""Registry and cache reading logic for Atlas project registry.

Reuses the minimal YAML parsing approach from session-start.py —
stdlib-only, no external YAML library needed.
"""

import re
from pathlib import Path

ATLAS_DIR = Path.home() / ".claude" / "atlas"
REGISTRY = ATLAS_DIR / "registry.yaml"
CACHE_DIR = ATLAS_DIR / "cache" / "projects"


def parse_yaml_value(line: str) -> str:
    """Extract value from a simple 'key: value' YAML line, stripping quotes."""
    _, _, val = line.partition(":")
    val = val.strip().strip('"').strip("'")
    return val


def expand_path(p: str) -> Path:
    """Expand ~ and resolve to absolute Path."""
    if p.startswith("~/") or p == "~":
        return Path(p).expanduser()
    return Path(p)


def parse_registry() -> list[dict]:
    """Parse registry.yaml into a list of project dicts.

    Returns list of: {slug, path, repo, additional_paths: []}
    """
    if not REGISTRY.is_file():
        return []

    text = REGISTRY.read_text(encoding="utf-8")
    projects: list[dict] = []
    current: dict | None = None
    in_additional = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        if line == "projects:":
            continue

        if not line.strip() or line.strip().startswith("#"):
            in_additional = False
            continue

        m = re.match(r"^  ([a-zA-Z0-9_-]+):\s*$", line)
        if m:
            if current:
                projects.append(current)
            current = {
                "slug": m.group(1),
                "path": "",
                "repo": "",
                "additional_paths": [],
            }
            in_additional = False
            continue

        if not current:
            continue

        if line.startswith("    path:"):
            current["path"] = parse_yaml_value(line)
            in_additional = False
        elif line.startswith("    repo:"):
            current["repo"] = parse_yaml_value(line)
            in_additional = False
        elif line.strip() == "additional_paths:":
            in_additional = True
        elif in_additional and line.startswith("      - "):
            current["additional_paths"].append(line.strip().removeprefix("- ").strip())
        elif re.match(r"^    [a-z]", line):
            in_additional = False

    if current:
        projects.append(current)

    return projects


def read_project_cache(slug: str) -> dict | None:
    """Read cached project metadata from ~/.claude/atlas/cache/projects/<slug>.yaml.

    Returns a dict with all fields from the cached atlas.yaml, or None if not found.
    Fields: name, summary, tags, group, links, docs, notes, metadata, _cache_meta.
    """
    cache_file = CACHE_DIR / f"{slug}.yaml"
    if not cache_file.is_file():
        return None

    text = cache_file.read_text(encoding="utf-8")
    return _parse_project_yaml(text)


def _parse_project_yaml(text: str) -> dict:
    """Parse a project's atlas.yaml (or cached copy) into a dict.

    Handles: scalar fields, simple lists (tags), simple maps (links, docs, metadata),
    and multiline strings (notes).
    """
    result: dict = {}
    current_key = ""
    current_map: dict | None = None
    current_list: list | None = None
    in_multiline = False
    multiline_lines: list[str] = []

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # Multiline string continuation (indented under a key with `|`)
        if in_multiline:
            if line.startswith("  ") or not line.strip():
                multiline_lines.append(line[2:] if line.startswith("  ") else "")
                continue
            else:
                result[current_key] = "\n".join(multiline_lines).rstrip("\n")
                in_multiline = False
                multiline_lines = []

        # Flush any open map/list before a new top-level key
        if current_map is not None and line and not line.startswith(" "):
            result[current_key] = current_map
            current_map = None
        if current_list is not None and line and not line.startswith(" "):
            result[current_key] = current_list
            current_list = None

        # Blank / comment
        if not line.strip() or line.strip().startswith("#"):
            continue

        # Map entry (2-space indent, key: value)
        if current_map is not None and re.match(r"^  [a-zA-Z_]", line):
            k, _, v = line.strip().partition(":")
            current_map[k.strip()] = v.strip().strip('"').strip("'")
            continue

        # List entry (2-space indent, - value)
        if current_list is not None and line.startswith("  - "):
            current_list.append(line.strip().removeprefix("- ").strip().strip('"').strip("'"))
            continue

        # Top-level key: value or key:
        m = re.match(r"^([a-zA-Z_][a-zA-Z0-9_]*)\s*:\s*(.*)", line)
        if m:
            key = m.group(1)
            val = m.group(2).strip()
            current_key = key

            if val == "|":
                in_multiline = True
                multiline_lines = []
            elif not val:
                # Could be a map or list — peek logic handled by next iteration
                # Start as map by default; if we see `- ` entries, switch to list
                current_map = {}
                current_list = None
            elif val.startswith("[") and val.endswith("]"):
                # Inline list: [tag1, tag2]
                items = val[1:-1].split(",")
                result[key] = [i.strip().strip('"').strip("'") for i in items if i.strip()]
            else:
                result[key] = val.strip('"').strip("'")
            continue

        # Detect list under a map-initialized key
        if current_map is not None and not current_map and line.startswith("  - "):
            current_list = []
            current_map = None
            current_list.append(line.strip().removeprefix("- ").strip().strip('"').strip("'"))

    # Flush trailing state
    if in_multiline:
        result[current_key] = "\n".join(multiline_lines).rstrip("\n")
    if current_map is not None:
        result[current_key] = current_map
    if current_list is not None:
        result[current_key] = current_list

    return result


def get_all_projects() -> list[dict]:
    """Get all registered projects with their cached metadata merged in.

    Returns list of dicts with registry fields (slug, path, repo) + cached fields
    (name, summary, tags, group, etc.).
    """
    projects = parse_registry()
    for proj in projects:
        cache = read_project_cache(proj["slug"])
        if cache:
            # Remove internal cache metadata from the merged result
            cache.pop("_cache_meta", None)
            proj.update(cache)
    return projects


def find_project_by_slug(slug: str) -> dict | None:
    """Find a project by its slug. Returns project dict or None."""
    for p in get_all_projects():
        if p.get("slug") == slug:
            return p
    return None


def resolve_project_path(slug: str, relative_path: str) -> Path:
    """Resolve a relative file path within a registered project.

    Validates that the slug exists in the registry and that the resolved
    path does not escape the project root (prevents path traversal).

    Args:
        slug: Project slug from the registry.
        relative_path: Path relative to the project root.

    Returns:
        Resolved absolute Path within the project.

    Raises:
        ValueError: If slug not found or path escapes project boundary.
    """
    project = find_project_by_slug(slug)
    if not project:
        raise ValueError(f"Project '{slug}' not found in registry")

    project_path = project.get("path", "")
    if not project_path:
        raise ValueError(f"Project '{slug}' has no path configured")

    project_root = expand_path(project_path).resolve()
    if not project_root.is_dir():
        raise ValueError(f"Project path does not exist: {project_root}")

    target = (project_root / relative_path).resolve()

    if not target.is_relative_to(project_root):
        raise ValueError(
            f"Path '{relative_path}' escapes project boundary for '{slug}'"
        )

    return target


def find_project_for_path(target_path: str) -> dict | None:
    """Find the project that matches a given filesystem path.

    Uses the same matching logic as session-start.py:
    1. Exact match (highest priority)
    2. Child match (deeper path wins)
    3. Additional paths
    """
    projects = get_all_projects()
    if not projects:
        return None

    target = Path(target_path).resolve()
    best_match: dict | None = None
    best_depth = -1

    for proj in projects:
        if not proj.get("path"):
            continue
        p = expand_path(proj["path"]).resolve()

        # Exact match
        if target == p:
            return proj

        # Child match
        try:
            target.relative_to(p)
            depth = len(p.parts)
            if depth > best_depth:
                best_match = proj
                best_depth = depth
        except ValueError:
            pass

        # Additional paths
        for ap_str in proj.get("additional_paths", []):
            ap = expand_path(ap_str).resolve()
            if target == ap:
                return proj
            try:
                target.relative_to(ap)
                depth = len(ap.parts)
                if depth > best_depth:
                    best_match = proj
                    best_depth = depth
            except ValueError:
                pass

    return best_match
