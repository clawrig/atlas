# Atlas — Integration Points

## Context7 Integration

Atlas bridges projects to their documentation via Context7 MCP server.

### Flow

```
User: /atlas:docs "how does token refresh work"
  │
  ├─ 1. Atlas resolves current project (from cwd or --project flag)
  ├─ 2. Reads project's docs.context7_id or docs.context7_query
  ├─ 3. If context7_id not cached:
  │     └─ Calls mcp__context7__resolve-library-id with query
  │        Caches result in ~/.claude/atlas/cache/context7-ids.yaml
  ├─ 4. Calls mcp__context7__query-docs with resolved ID + user query
  └─ 5. Returns documentation results in session context
```

### Configuration

```yaml
# In project definition:
docs:
  context7_id: "/npm/digital-web-sdk"    # Known ID — skip resolution
  context7_query: "digital personalization"  # Fallback for resolution
```

### Cache

```yaml
# ~/.claude/atlas/cache/context7-ids.yaml
resolved:
  digital-web-sdk:
    context7_id: "/npm/digital-web-sdk"
    resolved_at: "2026-02-22T10:00:00Z"
    query_used: "digital personalization sdk"
```

## Relay Plugin Integration

Atlas provides the **project metadata** that relay consumes:

| Atlas Provides | Relay Uses For |
|---|---|
| `issue_trackers[]` | Routing issues to correct tracker |
| `repo.type`, `repo.url` | Handoff envelope project section |
| `path` | Detecting which project a handoff targets |
| `links` | Including relevant links in handoff context |
| `notes` | Injecting project notes into handoff summary |

### API Contract

Relay reads atlas data by:
1. Parsing `~/.claude/atlas/projects.yaml` directly (YAML file)
2. Or invoking `/atlas:context --json` for current project info

Atlas does NOT depend on relay. Relay depends on atlas.

## Beads Integration

Atlas is aware of beads but does not depend on it:

- During `projects add`, atlas checks for `.beads/` and auto-configures a beads tracker entry
- Atlas project detection runs BEFORE beads' `bd prime` (hook ordering)
- Atlas injects project context that beads' task-agent can use

## ClawRig / OpenClaw Integration

### @clawrig/project-ref MCP Server

Atlas complements clawrig's project-ref MCP server:
- **project-ref** provides cross-project file read access to Claude Code
- **atlas** provides project metadata and discovery

Future: atlas could feed project-ref its project list, so project-ref doesn't need separate configuration.

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
    // Install from marketplace
    execSync('claude plugin install atlas --marketplace ivintik');
    // Initialize data directory
    execSync('mkdir -p ~/.claude/atlas');
  },
  recommended: true,
}
```

## Session Context Injection

### What Gets Injected

On SessionStart, if cwd matches a project, atlas outputs:

```
[Atlas] Project: Digital Personalization Web SDK (digital-web-sdk)
Repo: https://git.angara.cloud/digital/web-sdk (gitlab)
Links: docs=https://docs.example.com/web-sdk ci=https://git.angara.cloud/.../pipelines
Issue trackers: gitlab (default), beads (local)
Notes: Core JS SDK. Test: npm run test. Build: npm run build.
```

This appears in the session startup output, giving Claude immediate project awareness.

### What Doesn't Get Injected

- Full project registry (only current project)
- Issue tracker credentials (those live in MCP server configs)
- Other projects' details (available via /atlas:projects but not auto-injected)
