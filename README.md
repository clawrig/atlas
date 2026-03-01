# Famdeck Atlas

Project registry and cross-project awareness for [Claude Code](https://claude.ai/claude-code). Every session starts knowing which project you're in and what other projects exist. Slash commands let you manage the registry; an MCP server lets other plugins query it programmatically.

Part of the [Famdeck](https://github.com/famdeck/famdeck) autonomous development toolkit.

## Installation

### Via Marketplace (recommended)

```bash
claude plugin marketplace add iVintik/private-claude-marketplace
claude plugin install famdeck-atlas@ivintik
```

Or install the full toolkit which includes Atlas:

```bash
claude plugin install famdeck-toolkit@ivintik
# then in Claude Code:
/toolkit:toolkit-setup
```

### First-Time Setup

After installing, run in any Claude Code session:

```
> /atlas:init

Creating ~/.claude/atlas/...
Registering SessionStart hook...
Scanning ~/dev for projects...

Found 8 git repos:
  Slug                 Path                              atlas.yaml?
  my-app               ~/dev/personal/my-app             yes
  web-sdk              ~/dev/digital/clients/web-sdk     yes
  collector            ~/dev/digital/collector            no
  ...

Register all, let me choose, or skip?
```

This creates the registry, installs the session hook, and discovers projects.

## How It Works

### Automatic Session Context

Every Claude Code session starts with a project index — injected automatically by the SessionStart hook:

```
[atlas] Current: my-app — AI dev workflow toolkit
[atlas] Projects:
  my-app               AI dev workflow toolkit
  web-sdk              Browser JS SDK for content personalization
  collector            Snowplow event collector service
```

Claude always knows which project you're in and what other projects exist. No need to explain your repo layout every session.

When you open a session in a workspace root containing multiple repos, Atlas switches to workspace mode — showing which local repos are registered and which aren't.

### Three Layers

1. **SessionStart Hook** — detects the current project from `$PWD`, lists all registered projects with summaries, injects into Claude's context
2. **MCP Server** — FastMCP server exposing the registry as structured tools for other plugins and agents
3. **Skills** — slash commands for humans to manage the registry interactively

## Skills

### `/atlas:projects` — Manage the Registry

```
> /atlas:projects

Slug                 Group      Tags                 Summary
my-app               famdeck    python, ai           AI dev workflow toolkit
web-sdk              digital    typescript, sdk      Browser JS SDK
collector            digital    scala, kafka         Snowplow event collector

> /atlas:projects add
Detected: my-new-repo at ~/dev/personal/my-new-repo
  Remote: https://github.com/user/my-new-repo
  Slug: my-new-repo
Registered. Created .claude/atlas.yaml with auto-detected metadata.

> /atlas:projects show web-sdk
Name: Digital Web SDK
Path: ~/dev/digital/clients/web-sdk
Repo: https://github.com/org/web-sdk
Group: digital
Tags: typescript, sdk, browser
Links:
  docs → https://docs.example.com/web-sdk
  ci   → https://github.com/org/web-sdk/actions
Notes: Build with npm run build. Test with npm test.

> /atlas:projects edit web-sdk        # interactive editing of atlas.yaml
> /atlas:projects remove old-project  # with confirmation
> /atlas:projects link docs https://docs.example.com  # quick-add link
> /atlas:projects refresh             # rebuild cache from project configs
```

Filter by group or tag:

```
> /atlas:projects list --group digital
> /atlas:projects list --tag python
```

### `/atlas:context` — Detailed Project Info

```
> /atlas:context

Project: My App (my-app)
Path: ~/dev/personal/my-app
Repo: https://github.com/user/my-app
Group: famdeck
Tags: python, ai, automation

Links:
  docs → https://docs.example.com
  ci   → https://github.com/user/my-app/actions

Docs:
  Context7: /npm/my-lib
  Local: docs/

Notes:
  Build: pip install -e ".[dev]"
  Test: python -m pytest tests/ -q

> /atlas:context --project web-sdk    # view another project
> /atlas:context --json               # machine-readable output
```

## MCP Server

The MCP server exposes five tools for programmatic access by other plugins and agents:

| Tool | Description |
|------|-------------|
| `atlas_list_projects` | List all registered projects (optional provider enrichment) |
| `atlas_get_project` | Get full metadata for a project by slug |
| `atlas_search_projects` | Search by name/slug, tag, or group |
| `atlas_get_current_project` | Detect which project a filesystem path belongs to |
| `atlas_list_providers` | List registered data providers |

### Providers

Providers are plugins that contribute extra per-project data:

- **file** — reads a per-project YAML file (e.g., Relay reads `.claude/relay.yaml` to report tracker config)
- **mcp_query** — queries an HTTP endpoint for live data (e.g., Agent Mail inbox count)

Provider definitions live in `~/.claude/atlas/providers/<plugin>.yaml`.

## Configuration

### Registry: `~/.claude/atlas/registry.yaml`

Maps project slugs to filesystem paths:

```yaml
projects:
  my-app:
    path: ~/dev/personal/my-app
    repo: https://github.com/user/my-app

  web-sdk:
    path: ~/dev/digital/clients/web-sdk
    repo: https://git.example.com/digital/web-sdk
    additional_paths:
      - ~/dev/digital/clients/web-demo
```

### Per-Project Config: `<project>/.claude/atlas.yaml`

Lives in the project repo, version-controlled:

```yaml
name: My App
summary: AI dev workflow toolkit
tags: [python, ai, automation]
group: famdeck

links:
  docs: https://docs.example.com
  ci: https://github.com/user/my-app/actions

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
    context/SKILL.md           # /atlas:context — show project details
    init/SKILL.md              # /atlas:init — first-time setup
    projects/SKILL.md          # /atlas:projects — registry management
  mcp-server/
    src/atlas_mcp/
      server.py                # FastMCP server with 5 tools
      registry.py              # Registry parsing, cache, path matching
      providers.py             # Provider system (file + mcp_query)
    pyproject.toml             # Python package config
  hooks/
    hooks.json                 # SessionStart hook definition
    scripts/session-start.py   # Project detection, index generation
  knowledge/
    schema.md                  # Registry and config schema reference
```

## License

MIT
