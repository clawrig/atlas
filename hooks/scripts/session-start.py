#!/usr/bin/env python3
"""Atlas SessionStart hook: detect current project, discover children, output project index.

Output format: JSON with hookSpecificOutput.additionalContext and hookEventName.
"""
import json
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

ATLAS_DIR = Path.home() / ".claude" / "atlas"
REGISTRY = ATLAS_DIR / "registry.yaml"
CACHE_DIR = ATLAS_DIR / "cache" / "projects"
MAX_PROJECTS_OUTPUT = 30


def parse_yaml_value(line: str) -> str:
    """Extract value from a simple 'key: value' YAML line, stripping quotes."""
    _, _, val = line.partition(":")
    val = val.strip().strip('"').strip("'")
    return val


def parse_registry() -> list[dict]:
    """Parse registry.yaml into a list of project dicts.

    Returns list of: {slug, path, repo, additional_paths: []}
    """
    if not REGISTRY.is_file():
        return []

    text = REGISTRY.read_text(encoding="utf-8")
    projects = []
    current = None
    in_additional = False

    for raw_line in text.splitlines():
        line = raw_line.rstrip()

        # Top-level 'projects:' marker
        if line == "projects:":
            continue

        # Blank or comment
        if not line.strip() or line.strip().startswith("#"):
            in_additional = False
            continue

        # Top-level key under projects (2-space indent, ends with colon)
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

        # 4-space indent fields
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


def expand_path(p: str) -> Path:
    """Expand ~ and resolve to absolute Path."""
    if p.startswith("~/") or p == "~":
        return Path(p).expanduser()
    return Path(p)


def read_summary(filepath: Path) -> str:
    """Read the 'summary' field from a YAML file."""
    if not filepath.is_file():
        return ""
    for raw_line in filepath.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if line.startswith("summary:"):
            return parse_yaml_value(line)
    return ""


def refresh_cache(slug: str, project_path: Path, repo: str) -> str:
    """Copy project's .claude/atlas.yaml to cache, return summary."""
    src = project_path / ".claude" / "atlas.yaml"
    if not src.is_file():
        return ""

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    meta = (
        f"_cache_meta:\n"
        f"  source: {src}\n"
        f'  cached_at: "{now}"\n'
        f"  repo: {repo}\n\n"
    )
    content = src.read_text(encoding="utf-8")
    (CACHE_DIR / f"{slug}.yaml").write_text(meta + content, encoding="utf-8")
    return read_summary(src)


def find_files(directory: str, pattern: str, max_depth: int, timeout_sec: int = 2) -> list[str]:
    """Cross-platform file discovery with timeout."""
    try:
        # Use find on Unix, fallback to Python walk
        result = subprocess.run(
            ["find", directory, "-maxdepth", str(max_depth), "-path", pattern, "-type", "f"],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        return [l for l in result.stdout.splitlines() if l.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _python_find(directory, pattern, max_depth)


def find_dirs(directory: str, name: str, max_depth: int, timeout_sec: int = 2) -> list[str]:
    """Cross-platform directory discovery with timeout."""
    try:
        result = subprocess.run(
            ["find", directory, "-maxdepth", str(max_depth), "-name", name, "-type", "d"],
            capture_output=True, text=True, timeout=timeout_sec,
        )
        return [l for l in result.stdout.splitlines() if l.strip()]
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return _python_find_dirs(directory, name, max_depth)


def _python_find(directory: str, pattern: str, max_depth: int) -> list[str]:
    """Pure Python fallback for find -path pattern -type f."""
    # Convert glob pattern like "*/.claude/atlas.yaml" to suffix match
    suffix = pattern.lstrip("*")
    results = []
    base = Path(directory)
    try:
        for root, dirs, files in os.walk(base):
            depth = len(Path(root).relative_to(base).parts)
            if depth >= max_depth:
                dirs.clear()
                continue
            full = Path(root)
            for f in files:
                fp = full / f
                if str(fp).endswith(suffix):
                    results.append(str(fp))
    except OSError:
        pass
    return results


def _python_find_dirs(directory: str, name: str, max_depth: int) -> list[str]:
    """Pure Python fallback for find -name name -type d."""
    results = []
    base = Path(directory)
    try:
        for root, dirs, _files in os.walk(base):
            depth = len(Path(root).relative_to(base).parts)
            if depth >= max_depth:
                dirs.clear()
                continue
            for d in dirs:
                if d == name:
                    results.append(str(Path(root) / d))
    except OSError:
        pass
    return results


def fmt_line(slug: str, description: str, width: int = 20) -> str:
    """Format a project line: slug padded + description."""
    return f"  {slug:<{width}} {description}"


MAIL_SERVER_URL = os.environ.get("AGENT_MAIL_URL", "http://localhost:8765")
MAIL_TIMEOUT_SEC = 2


def check_mail_inbox() -> tuple[str | None, str | None]:
    """Check mcp_agent_mail unified inbox count.

    Returns (count_string, error_string). If server is down, returns (None, error).
    """
    try:
        req = urllib.request.Request(f"{MAIL_SERVER_URL}/health/liveness", method="GET")
        urllib.request.urlopen(req, timeout=MAIL_TIMEOUT_SEC)
    except (urllib.error.URLError, OSError):
        return None, "mail server not running (start with: /toolkit:toolkit-setup)"

    try:
        req = urllib.request.Request(f"{MAIL_SERVER_URL}/mail/api/unified-inbox", method="GET")
        resp = urllib.request.urlopen(req, timeout=MAIL_TIMEOUT_SEC)
        result = json.loads(resp.read())
        count = len(result.get("messages", []))
        return str(count), None
    except (urllib.error.URLError, OSError, json.JSONDecodeError, KeyError):
        return "0", None


def main():
    if not REGISTRY.is_file():
        return

    projects = parse_registry()
    if not projects:
        return

    cwd = Path.cwd().resolve()

    # Expand paths and build lookup
    for proj in projects:
        proj["abs_path"] = expand_path(proj["path"]).resolve()
        proj["abs_additional"] = [expand_path(p).resolve() for p in proj["additional_paths"]]

    # Load cached summaries
    summaries: dict[str, str] = {}
    for proj in projects:
        s = proj["slug"]
        cache_file = CACHE_DIR / f"{s}.yaml"
        summary = read_summary(cache_file)
        if summary:
            summaries[s] = summary

    # --- Match PWD against registry ---
    current_slug = ""
    current_depth = -1

    for proj in projects:
        p = proj["abs_path"]

        # Exact match
        if cwd == p:
            current_slug = proj["slug"]
            current_depth = 999
            break

        # Child match
        try:
            cwd.relative_to(p)
            depth = len(p.parts)
            if depth > current_depth:
                current_slug = proj["slug"]
                current_depth = depth
        except ValueError:
            pass

        # Additional paths
        for ap in proj["abs_additional"]:
            if cwd == ap:
                current_slug = proj["slug"]
                current_depth = 999
                break
            try:
                cwd.relative_to(ap)
                depth = len(ap.parts)
                if depth > current_depth:
                    current_slug = proj["slug"]
                    current_depth = depth
            except ValueError:
                pass

    # --- Refresh cache for current project ---
    if current_slug:
        for proj in projects:
            if proj["slug"] == current_slug:
                summary = refresh_cache(current_slug, proj["abs_path"], proj["repo"])
                if summary:
                    summaries[current_slug] = summary
                break

    # --- Check mail inbox ---
    mail_count, mail_error = check_mail_inbox()

    # --- Child discovery (only if NOT in a specific project) ---
    local_registered: list[str] = []  # slugs found locally
    local_unregistered_config: list[str] = []  # slugs discovered with atlas.yaml
    local_unregistered_git: list[str] = []  # slugs discovered via .git only

    registered_abs = {proj["abs_path"]: proj["slug"] for proj in projects}

    if not current_slug:
        cwd_str = str(cwd)

        # Find .claude/atlas.yaml files
        for cfg in find_files(cwd_str, "*/.claude/atlas.yaml", 4):
            proj_dir = Path(cfg).parent.parent.resolve()
            if proj_dir in registered_abs:
                local_registered.append(registered_abs[proj_dir])
            else:
                slug = proj_dir.name.lower().replace(" ", "-").replace("_", "-")
                local_unregistered_config.append(slug)

        # Find .git dirs
        for gitdir in find_dirs(cwd_str, ".git", 2):
            proj_dir = Path(gitdir).parent.resolve()
            if proj_dir == cwd:
                continue
            if proj_dir in registered_abs:
                slug = registered_abs[proj_dir]
                if slug not in local_registered:
                    local_registered.append(slug)
                continue
            slug = proj_dir.name.lower().replace(" ", "-").replace("_", "-")
            if slug not in local_unregistered_config:
                local_unregistered_git.append(slug)

    # --- Build output ---
    lines: list[str] = []
    has_local = local_registered or local_unregistered_config or local_unregistered_git

    if current_slug:
        # Case 1: Inside a registered project
        s = summaries.get(current_slug, "")
        if mail_error:
            mail_suffix = f" | ⚠ {mail_error}"
        elif mail_count and mail_count != "0":
            mail_suffix = f" | mail: {mail_count}"
        else:
            mail_suffix = ""
        if s:
            lines.append(f"[atlas] Current: {current_slug} — {s}{mail_suffix}")
        else:
            lines.append(f"[atlas] Current: {current_slug}{mail_suffix}")
        lines.append("[atlas] Projects:")

        # Current project first
        lines.append(fmt_line(current_slug, summaries.get(current_slug, "no summary")))
        for proj in projects:
            if proj["slug"] != current_slug:
                lines.append(fmt_line(proj["slug"], summaries.get(proj["slug"], "no summary")))

    elif has_local:
        # Case 2: Workspace root with child projects
        lines.append(f"[atlas] Workspace: {cwd}")
        lines.append("[atlas] Local projects:")

        for slug in local_registered:
            lines.append(fmt_line(slug, summaries.get(slug, "no summary")))
        for slug in local_unregistered_config:
            lines.append(fmt_line(slug, "(not registered — /atlas:projects add)"))
        for slug in local_unregistered_git:
            lines.append(fmt_line(slug, "(git repo, not registered)"))

        # Other projects (registered but not local)
        all_local = set(local_registered)
        others = [p for p in projects if p["slug"] not in all_local]
        if others:
            lines.append("[atlas] Other projects:")
            for proj in others:
                lines.append(fmt_line(proj["slug"], summaries.get(proj["slug"], "no summary")))

    else:
        # Case 3: No match, no children
        lines.append("[atlas] Projects:")
        for proj in projects:
            lines.append(fmt_line(proj["slug"], summaries.get(proj["slug"], "no summary")))

    # Cap output
    if len(lines) > MAX_PROJECTS_OUTPUT + 3:
        remaining = len(lines) - (MAX_PROJECTS_OUTPUT + 3)
        lines = lines[:MAX_PROJECTS_OUTPUT + 3]
        lines.append(f"  ... and {remaining} more (use /atlas:projects list for full list)")

    # Output JSON
    context = "\n".join(lines)
    output = {
        "hookSpecificOutput": {"additionalContext": context},
        "hookEventName": "SessionStart",
    }
    print(json.dumps(output))


if __name__ == "__main__":
    main()
