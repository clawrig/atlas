# Atlas — Data Model

## Two-Layer Storage

Atlas uses a **split model**: minimal central registry + rich per-project configs that live in each project's repo.

### Layer 1: Central Registry (Atlas owns)

```
~/.claude/atlas/
├── registry.yaml              # Minimal: slug → path + repo
└── cache/
    ├── projects/
    │   └── digital-web-sdk.yaml   # Cached project config (from repo)
    └── context7-ids.yaml          # Cached context7 library ID resolutions
```

**`registry.yaml`** — The only thing atlas manages centrally:

```yaml
# ~/.claude/atlas/registry.yaml
# This file answers ONE question: "What projects am I working on and where are they?"

projects:
  digital-web-sdk:
    path: ~/dev/digital/clients/digital-personalization-web-sdk
    repo: https://git.angara.cloud/digital/web-sdk

  clawrig:
    path: ~/dev/personal/clawrig
    repo: https://github.com/iVintik/clawrig

  digital-collector:
    path: ~/dev/digital/digital-collector
    repo: https://git.angara.cloud/digital/digital-collector

  # Additional paths for cwd matching (e.g., monorepo child dirs)
  # If cwd is inside any of these, atlas resolves to this project
  digital-web-sdk:
    path: ~/dev/digital/clients/digital-personalization-web-sdk
    repo: https://git.angara.cloud/digital/web-sdk
    additional_paths:
      - ~/dev/digital/clients/digital-personalization-tags
```

That's it. No links, no tags, no notes, no issue trackers. Those live in the project repo.

### Layer 2: Per-Project Config (Lives in the repo)

Each project repo contains a `.claude/atlas.yaml` describing itself:

```yaml
# <project-root>/.claude/atlas.yaml
# This file travels with the repo. Team members share it.

name: "Digital Personalization Web SDK"

# REQUIRED — one-liner (<100 chars) used in the project index.
# This is what every Claude session sees for this project.
# Think of it like an MCP tool description — enough to know
# when the project is relevant, without loading full details.
summary: "Browser JS SDK for content personalization — TypeScript, Vite"

tags:
  - sdk
  - typescript
  - frontend

group: digital-platform

links:
  docs: https://docs.example.com/web-sdk
  ci: https://git.angara.cloud/digital/web-sdk/-/pipelines
  staging: https://staging.example.com
  figma: https://figma.com/file/abc123
  confluence: https://confluence.example.com/display/SDK

docs:
  context7_id: "/npm/digital-web-sdk"
  context7_query: "digital personalization sdk"
  local: ./docs/
  readme: ./README.md

notes: |
  Core JS SDK for the Digital Personalization Platform.
  Uses TypeScript, builds with Vite.
  Test: npm run test
  Build: npm run build

metadata:
  team: platform
  language: typescript
  framework: vanilla
```

### Why This Split

| Concern | Where | Why |
|---|---|---|
| "Where is this project?" | `registry.yaml` (central) | Machine-specific (paths differ per machine) |
| "What is this project?" | `.claude/atlas.yaml` (in repo) | Portable, team-shared, version-controlled |
| Issue tracker config | `.claude/relay.yaml` (in repo) | Relay's concern, not atlas's |

**Benefits:**
- Clone a repo → atlas can pick up its config immediately
- Team members share project metadata via git
- Central registry stays tiny and fast to parse
- No stale central config that drifts from reality

## Cache Layer

Atlas caches per-project configs for cross-project queries (e.g., `/atlas:projects list --tag typescript` needs to read all projects' configs).

```yaml
# ~/.claude/atlas/cache/projects/digital-web-sdk.yaml
# Cached copy of <project-path>/.claude/atlas.yaml
# Refreshed on SessionStart when cwd matches this project
# Refreshed on explicit /atlas:projects refresh

_cache_meta:
  source: ~/dev/digital/clients/digital-personalization-web-sdk/.claude/atlas.yaml
  cached_at: "2026-02-22T10:00:00Z"
  repo: https://git.angara.cloud/digital/web-sdk

# ... rest is exact copy of the project's .claude/atlas.yaml
name: "Digital Personalization Web SDK"
tags: [sdk, typescript, frontend]
# ...
```

### Cache Refresh Strategy

| Trigger | What Refreshes |
|---|---|
| SessionStart (cwd matches project) | That project's cache entry |
| `/atlas:projects add` | New project's cache entry |
| `/atlas:projects refresh` | All projects (walks registry, reads each config) |
| `/atlas:projects refresh <slug>` | Specific project |

Cache is best-effort. If a project path doesn't exist (unmounted drive, deleted clone), cache serves stale data with a warning.

## Auto-Detection on `projects add`

When registering a new project, atlas auto-detects:

1. **Repo URL** — from `.git/config` remote origin
2. **Slug** — from directory name (sanitized to lowercase kebab-case)
3. **Existing `.claude/atlas.yaml`** — reads it immediately if present
4. **Missing `.claude/atlas.yaml`** — offers to create one with auto-detected values:
   - `name` from `package.json`, `Cargo.toml`, `build.gradle`, or directory name
   - `summary` auto-generated from name + detected language/framework (<100 chars)
   - `tags` from detected language/framework
   - `links.ci` guessed from repo URL (GitLab CI, GitHub Actions)

## Path Matching Rules

For SessionStart project detection:

1. Exact match: `cwd == project.path`
2. Child match: `cwd` is inside `project.path`
3. Additional paths: `cwd` matches any `additional_paths` entry
4. Deepest match wins (most specific project)
5. If no match: session runs without project context (atlas still available)

## Project Discovery (Two-Tier Index)

Atlas uses a **two-tier discovery model** — the same pattern as MCP tools, skills, and Context7:

| Tier | What | When Loaded | Context Cost |
|---|---|---|---|
| **Index** | Slug + summary (one-liner per project) | Always (SessionStart) | ~50 tokens/project |
| **Details** | Full config (links, docs, tags, notes) | On demand (`/atlas:context`) | ~200-500 tokens/project |

### Tier 1: Project Index (Always Loaded)

On every SessionStart, atlas outputs the full project index — one line per registered project:

```
[atlas] Current: digital-web-sdk
[atlas] Projects:
  digital-web-sdk    Browser JS SDK for content personalization — TypeScript, Vite
  digital-collector  Snowplow event collector service — Scala, Kafka
  digital-enrich     Event enrichment pipeline — Scala, Kafka
  clawrig            AI dev workflow orchestration — TypeScript, Node
  clawrig-atlas      Project registry for Claude sessions — Claude plugin
```

This gives Claude enough awareness to:
- Know what projects exist
- Recognize when a conversation touches another project
- Decide when to load full details

**Scaling**: At ~50 tokens per project, 20 projects = ~1000 tokens (negligible). For registries with 50+ projects, the hook caps output to the 30 most recently accessed and appends `... and N more (use /atlas:projects list for full list)`.

### Tier 2: Full Details (On Demand)

When Claude needs more about a project, it calls `/atlas:context --project <slug>`. This loads the full cached config: links, docs, tags, notes, metadata.

### Where Summaries Come From

The `summary` field in `.claude/atlas.yaml` is the source of truth. It's:
- **Required** — atlas warns if missing during `add` or `refresh`
- **Short** — must be <100 characters
- **Descriptive** — what the project IS, not what it does in detail
- **Cached** — stored in `~/.claude/atlas/cache/projects/<slug>.yaml` alongside full config

If a project has no `.claude/atlas.yaml` or no `summary` field, atlas falls back to: `<slug> (no summary — run /atlas:projects edit <slug>)`

## Data Integrity

- `registry.yaml` is the central source of truth for "what projects exist"
- Per-project `.claude/atlas.yaml` is the source of truth for project metadata
- Cache is derived, disposable, and auto-refreshed
- No database, no lock files
- Concurrent writes to registry: last-write-wins (acceptable for manual registry)
