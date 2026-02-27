# Atlas — Integration Points

## Context7 Integration

Atlas bridges projects to their documentation via Context7 MCP server.

### Flow

```
User: /atlas:docs "how does token refresh work"
  │
  ├─ 1. Atlas resolves current project (from cwd or --project flag)
  ├─ 2. Reads project's docs.context7_id or docs.context7_query (from cached config)
  ├─ 3. If context7_id not cached:
  │     └─ Calls mcp__context7__resolve-library-id with query
  │        Caches result in ~/.claude/atlas/cache/context7-ids.yaml
  ├─ 4. Calls mcp__context7__query-docs with resolved ID + user query
  └─ 5. Returns documentation results in session context
```

### Configuration (in project's `.claude/atlas.yaml`)

```yaml
docs:
  context7_id: "/npm/digital-web-sdk"        # Known ID — skip resolution
  context7_query: "digital personalization"   # Fallback for resolution
  local: ./docs/                              # Local docs path
```

## Relay Plugin Integration

Atlas provides **project identity and metadata**. Relay provides **issue routing and handoff**.

| Atlas Provides | Relay Uses For |
|---|---|
| Project slug, path | Resolving which project the user is in |
| `repo.url`, repo type | Handoff envelope, cross-project references |
| Cached project config (links, notes) | Including in handoff context |

### Boundary

- Atlas does NOT know about issue trackers — that's relay's domain
- Relay reads atlas registry to resolve project, then reads its own `.claude/relay.yaml` from the project repo for tracker config
- Atlas does NOT depend on relay. Relay depends on atlas (for project resolution).

### API Contract

Relay resolves projects by:
1. Reading `~/.claude/atlas/registry.yaml` to find project path
2. Reading cached config from `~/.claude/atlas/cache/projects/<slug>.yaml`
3. Or invoking `/atlas:context --json` for current project info

## Beads Integration

Atlas is aware of beads but does not depend on it:

- During `projects add`, if `.beads/` exists, atlas notes it in session context
- Atlas project detection runs BEFORE beads' `bd prime` (hook ordering)
- Atlas injects project context that beads' task-agent can use for orientation

## OpenClaw Integration

### OpenClaw Skills

Atlas skills are pure markdown — they work in OpenClaw without modification.
The only Claude Code-specific part is the SessionStart hook, which OpenClaw would replace with its own session initialization.

## Toolkit Integration

Atlas should be added to the toolkit's tool registry (`setup.mjs`):

```javascript
{
  name: 'Atlas',
  description: 'Project registry & awareness across all sessions',
  deps: [],
  check: () => execSync('claude plugin list').toString().includes('atlas'),
  install: async () => {
    execSync('claude plugin install atlas --marketplace ivintik');
    execSync('mkdir -p ~/.claude/atlas/cache/projects');
  },
  recommended: true,
}
```

## Session Context Injection (Two-Tier Discovery)

Atlas uses the same pattern as MCP tools and skills: **always-loaded index + on-demand details**.

### Tier 1: Project Index (Always Injected)

On every SessionStart, atlas outputs a compact index of ALL registered projects:

```
[atlas] Current: digital-web-sdk — Browser JS SDK for content personalization
[atlas] Projects:
  digital-web-sdk *  Browser JS SDK for content personalization — TypeScript, Vite
  digital-collector  Snowplow event collector service — Scala, Kafka
  digital-enrich     Event enrichment pipeline — Scala, Kafka
  my-tool        AI dev workflow orchestration — TypeScript, Node
  famdeck-atlas  Project registry for Claude sessions — Claude plugin
```

Each line is a slug + the `summary` field from the project's `.claude/atlas.yaml`. This costs ~50 tokens per project — negligible for typical registries (5-30 projects).

This gives Claude enough cross-project awareness to:
- Know what other projects exist and what they do
- Recognize when a conversation touches another project
- Decide when to load full details via `/atlas:context --project <slug>`

### Tier 2: Full Details (On Demand)

When Claude needs more about a specific project, it calls:
```
/atlas:context --project digital-collector
```
This loads the full cached config: links, docs, tags, notes, metadata.

### What Doesn't Get Auto-Injected

- Full project configs (links, tags, docs, notes) — only loaded on demand
- Issue tracker info — relay's responsibility, loaded when `/relay:issue` is called
- Documentation content — loaded via `/atlas:docs` when needed

## Per-Project Config File (`.claude/atlas.yaml`)

Atlas defines the schema, projects provide the data:

```yaml
# <project-root>/.claude/atlas.yaml
name: "Digital Personalization Web SDK"
summary: "Browser JS SDK for content personalization — TypeScript, Vite"  # REQUIRED, <100 chars
tags: [sdk, typescript, frontend]
group: digital-platform
links:
  docs: https://docs.example.com/web-sdk
  ci: https://git.angara.cloud/digital/web-sdk/-/pipelines
docs:
  context7_id: "/npm/digital-web-sdk"
  local: ./docs/
notes: |
  Core JS SDK. Test: npm run test. Build: npm run build.
```

This file is:
- **Version-controlled** — travels with the repo
- **Team-shared** — everyone gets the same project metadata
- **Optional** — atlas works without it (just less context, no summary in index)
- **Managed by atlas** — `/atlas:projects edit` modifies this file in the repo

The `summary` field is the most important — it's what appears in the project index on every session start across all projects.
