# Atlas — Skills Specification

## Skill: /atlas:projects

**Purpose**: Manage the global project registry.

### Subcommands

#### `list` (default)

```
/atlas:projects
/atlas:projects list
/atlas:projects list --group digital-platform
/atlas:projects list --tag typescript
```

Output: table of registered projects with slug, name, path, repo type, tags.

#### `add`

```
/atlas:projects add
/atlas:projects add --path /path/to/project
/atlas:projects add --slug my-project --path ~/dev/my-project
```

Interactive flow:
1. If no `--path`, use cwd
2. Auto-detect repo info from `.git/config`
3. Auto-detect language/framework from project files
4. Check for `.beads/` → auto-add beads tracker
5. Ask for slug (suggest from directory name)
6. Ask for tags, group, notes
7. Ask about issue trackers (which external trackers to configure)
8. Write to `~/.claude/atlas/projects.yaml`

#### `show`

```
/atlas:projects show digital-web-sdk
/atlas:projects show                       # Show current project (from cwd)
```

Output: full project details including all links, trackers, notes.

#### `edit`

```
/atlas:projects edit digital-web-sdk
```

Interactive: show current values, allow editing any field.

#### `remove`

```
/atlas:projects remove digital-web-sdk
```

Confirmation required. Removes from registry only (doesn't touch project files).

#### `link`

```
/atlas:projects link docs https://docs.example.com
/atlas:projects link ci https://ci.example.com/pipelines
/atlas:projects link --project digital-web-sdk figma https://figma.com/...
```

Quick way to add/update links without full edit flow.

---

## Skill: /atlas:context

**Purpose**: Show what atlas knows about the current session's project.

```
/atlas:context
/atlas:context --json                     # Machine-readable output
/atlas:context --project digital-web-sdk  # Specific project
```

### Output Format (Human)

```
Project: Digital Personalization Web SDK
Slug: digital-web-sdk
Path: ~/dev/digital/clients/digital-personalization-web-sdk
Repo: gitlab — https://git.angara.cloud/digital/web-sdk
Group: digital-platform
Tags: sdk, typescript, frontend

Links:
  docs    → https://docs.example.com/web-sdk
  ci      → https://git.angara.cloud/.../pipelines
  staging → https://staging.example.com

Issue Trackers:
  gitlab (default) — project: digital/web-sdk
  beads (local)

Notes:
  Core JS SDK for the Digital Personalization Platform.
  Test: npm run test | Build: npm run build
```

### Output Format (JSON)

Full project definition as JSON — used by relay and other tools programmatically.

---

## Skill: /atlas:docs

**Purpose**: Query documentation for current or specified project via Context7.

```
/atlas:docs "how does token refresh work"
/atlas:docs --project digital-web-sdk "authentication flow"
```

### Flow

1. Resolve project (cwd or `--project`)
2. Load context7 config from project definition
3. If `context7_id` not set/cached → resolve via `mcp__context7__resolve-library-id`
4. Query docs via `mcp__context7__query-docs`
5. Return results

### Fallback

If Context7 MCP is not installed:
- Check for `docs.local` path in project config
- Search local docs directory with grep/glob
- Suggest installing Context7 via toolkit

---

## Skill: /atlas:init

**Purpose**: Initialize atlas for first-time use and register the current project.

```
/atlas:init
```

### Flow

1. Create `~/.claude/atlas/` directory if not exists
2. Create `projects.yaml` with empty projects map
3. Offer to register current directory as a project (runs `add` flow)
4. Print quick-start guide

---

## Hook: SessionStart — project-detect

**Purpose**: Auto-detect current project and inject context.

### Behavior

1. Read `~/.claude/atlas/projects.yaml`
2. Match `$PWD` against all project paths (exact, child, additional_paths)
3. If match found: output project summary (name, repo, links, notes)
4. If no match: silent (no output, no error)

### Performance

- Pure bash: read YAML, pattern match, print
- No network calls
- Target: < 500ms execution
- Skip if `projects.yaml` doesn't exist (atlas not initialized)

### Output

Printed to stdout during session startup. Claude sees this as session context.

```
[atlas] digital-web-sdk — gitlab — 2 trackers — 3 links
```

Compact one-liner. Full details available via `/atlas:context`.
