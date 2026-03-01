# Famdeck Atlas

Project registry and cross-project awareness for Claude Code. Maps project slugs to filesystem paths, caches per-project metadata, and provides session context so Claude always knows which project you're in and what other projects exist.

Part of the [Famdeck](https://github.com/famdeck/famdeck) autonomous development toolkit.

## Installation

```bash
git clone https://github.com/famdeck/famdeck-atlas.git
```

Requires: Python >= 3.10, [uv](https://docs.astral.sh/uv/).

Initialize atlas in any Claude Code session:

```bash
/atlas:init
```

This creates `~/.claude/atlas/`, registers the SessionStart hook, scans for projects, and adds them to the registry.

## How It Works

Atlas has three layers:

1. **SessionStart Hook** — runs at the start of every Claude Code session. Detects the current project from `$PWD`, lists all registered projects with summaries, and checks Agent Mail inbox. Output goes into Claude's context.

2. **MCP Server** — a Python server (FastMCP) that exposes the registry as structured tools. Other plugins and agents query it to find project paths, search by tag/group, and get enriched metadata.

3. **Skills** — slash commands for humans to manage the registry interactively.

### Session Context

Every session starts with a project index:

```
[atlas] Current: my-project — AI dev workflow toolkit
[atlas] Projects:
  my-project           AI dev workflow toolkit
  digital-web-sdk      Browser JS SDK for content personalization
  digital-collector    Snowplow event collector service
```

When you `cd` to a workspace root containing multiple repos, Atlas switches to workspace mode — showing which local repos are registered and which aren't.

## Skills

| Command | What it does |
|---------|-------------|
| `/atlas:init` | First-time setup — directories, hook registration, project scanning |
| `/atlas:projects` | List all registered projects |
| `/atlas:projects add` | Register the current directory as a project |
| `/atlas:projects show [slug]` | Show full project details |
| `/atlas:projects edit [slug]` | Edit a project's atlas.yaml config |
| `/atlas:projects remove <slug>` | Unregister a project |
| `/atlas:projects link <name> <url>` | Add a quick-access link to a project |
| `/atlas:projects refresh` | Rebuild cache from project configs |
| `/atlas:context [--project slug]` | Show detailed project metadata (links, tags, docs, notes) |

## MCP Server Tools

The MCP server exposes five tools:

| Tool | Description |
|------|-------------|
| `atlas_list_projects` | List all registered projects (optional enrichment from providers) |
| `atlas_get_project` | Get full metadata for a project by slug |
| `atlas_search_projects` | Search by name/slug, tag, or group |
| `atlas_get_current_project` | Detect which project a filesystem path belongs to |
| `atlas_list_providers` | List registered data providers |

### Providers

Providers are plugins that contribute extra per-project data. Two types:

- **file** — reads a per-project YAML file (e.g., Relay reads `.claude/relay.yaml` to report tracker config)
- **mcp_query** — queries an HTTP endpoint for live data (e.g., Agent Mail inbox count)

Provider definitions live in `~/.claude/atlas/providers/<plugin>.yaml`.

## Configuration

### Registry: `~/.claude/atlas/registry.yaml`

Maps project slugs to filesystem paths:

```yaml
projects:
  my-project:
    path: ~/dev/personal/my-project
    repo: https://github.com/user/my-project

  web-sdk:
    path: ~/dev/digital/clients/web-sdk
    repo: https://git.example.com/digital/web-sdk
    additional_paths:
      - ~/dev/digital/clients/web-demo
```

### Per-Project Config: `<project>/.claude/atlas.yaml`

Lives in the project repo, version-controlled:

```yaml
name: My Project
summary: AI dev workflow toolkit
tags: [python, ai, automation]
group: famdeck

links:
  docs: https://docs.example.com
  ci: https://github.com/user/my-project/actions

docs:
  context7_id: "/npm/my-lib"
  local: docs/

notes: |
  Build: pip install -e ".[dev]"
  Test: python -m pytest tests/ -q

metadata:
  language: python
  framework: fastmcp
```

### Path Matching

Atlas detects the current project using path matching:

1. **Exact match** — `$PWD == project.path` (highest priority)
2. **Child match** — `$PWD` is inside `project.path/` (deepest wins)
3. **Additional paths** — same rules applied to `additional_paths` entries

## Project Structure

```
famdeck-atlas/
  skills/
    context/SKILL.md        # /atlas:context — show project details
    init/SKILL.md           # /atlas:init — first-time setup
    projects/SKILL.md       # /atlas:projects — registry management
  mcp-server/
    src/atlas_mcp/
      server.py             # FastMCP server with 5 tools
      registry.py           # Registry parsing, cache reading, path matching
      providers.py          # Provider system (file + mcp_query)
    pyproject.toml          # Python package config (requires mcp[cli])
  hooks/
    hooks.json              # SessionStart hook definition
    scripts/session-start.py  # Project detection, index generation
  knowledge/
    schema.md               # Registry and config schema reference
  openclaw.plugin.json      # Plugin manifest
  package.json              # npm package metadata
  index.ts                  # Plugin entry point
```

## License

MIT
