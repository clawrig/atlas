# Atlas — Skills Specification

## Skill: /atlas:projects

**Purpose**: Manage the project registry and per-project configs.

### Subcommands

#### `list` (default)

```
/atlas:projects
/atlas:projects list
/atlas:projects list --group digital-platform
/atlas:projects list --tag typescript
```

Output: table of registered projects with slug, path, repo, tags (from cache).

For `--group` and `--tag` filtering, atlas reads cached configs. If cache is empty, suggests running `refresh` first.

#### `add`

```
/atlas:projects add
/atlas:projects add --path /path/to/project
/atlas:projects add --slug my-project --path ~/dev/my-project
```

Interactive flow:
1. If no `--path`, use cwd
2. Auto-detect repo URL from `.git/config`
3. Ask for slug (suggest from directory name)
4. Add entry to `~/.claude/atlas/registry.yaml` (slug + path + repo)
5. Check if `.claude/atlas.yaml` exists in the project:
   - **Exists** → read it, validate `summary` field exists, cache it, show summary
   - **Missing** → offer to create one:
     - Auto-detect name from `package.json` / `Cargo.toml` / directory name
     - Ask for summary (<100 chars, one-liner — suggest based on name + language)
     - Auto-detect tags from language/framework
     - Guess CI link from repo URL
     - Write `.claude/atlas.yaml` to the project repo
6. Cache the project config (including summary for the project index)

#### `show`

```
/atlas:projects show digital-web-sdk
/atlas:projects show                       # Show current project (from cwd)
```

Output: full project details — registry info + config from cache.

#### `edit`

```
/atlas:projects edit digital-web-sdk
/atlas:projects edit                       # Edit current project
```

Interactive: opens the project's `.claude/atlas.yaml` for editing. Changes are made in the project repo (version-controlled). Cache is refreshed after edit.

#### `remove`

```
/atlas:projects remove digital-web-sdk
```

Confirmation required. Removes from `registry.yaml` and cache. Does NOT delete `.claude/atlas.yaml` from the project repo.

#### `link`

```
/atlas:projects link docs https://docs.example.com
/atlas:projects link ci https://ci.example.com/pipelines
/atlas:projects link --project digital-web-sdk figma https://figma.com/...
```

Quick way to add/update links in the project's `.claude/atlas.yaml`. Refreshes cache after.

#### `refresh`

```
/atlas:projects refresh                    # Refresh all project caches
/atlas:projects refresh digital-web-sdk    # Refresh specific project
```

Walks registry, reads each project's `.claude/atlas.yaml`, updates cache. Reports:
- Projects with missing paths (clone gone?)
- Projects without `.claude/atlas.yaml` (suggest creating)
- Projects with updated configs (diff since last cache)

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
Project: Digital Personalization Web SDK (digital-web-sdk)
Path: ~/dev/digital/clients/digital-personalization-web-sdk
Repo: gitlab — https://git.angara.cloud/digital/web-sdk
Group: digital-platform
Tags: sdk, typescript, frontend

Links:
  docs    → https://docs.example.com/web-sdk
  ci      → https://git.angara.cloud/.../pipelines
  staging → https://staging.example.com

Notes:
  Core JS SDK for the Digital Personalization Platform.
  Test: npm run test | Build: npm run build
```

### Output Format (JSON)

Merged view: registry entry + cached project config. Used by relay and other tools programmatically.

---

## Skill: /atlas:docs

**Purpose**: Query documentation for current or specified project via Context7.

```
/atlas:docs "how does token refresh work"
/atlas:docs --project digital-web-sdk "authentication flow"
```

### Flow

1. Resolve project (cwd or `--project`)
2. Load docs config from cached project config
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

**Purpose**: Initialize atlas for first-time use. Discovers and registers projects in the current directory.

```
/atlas:init
/atlas:init --scan ~/dev          # Scan a specific directory for projects
```

### Flow

1. Create `~/.claude/atlas/` directory structure
2. Create empty `registry.yaml`
3. **Scan cwd (or `--scan` path) for projects**:
   - Find all `.git/` directories up to 3 levels deep
   - For each: check if `.claude/atlas.yaml` exists
   - Present discovered projects as a list
   - Ask which ones to register (default: all)
4. For each selected project, run the `add` flow (auto-detect slug, repo, create config if missing)
5. Print summary + quick-start guide

---

## Hook: SessionStart — project-detect + discover + index

**Purpose**: Auto-detect current project, discover projects inside cwd, and output the project index.

### Behavior

1. Read `~/.claude/atlas/registry.yaml`
2. **Registry match**: Match `$PWD` against all project paths (exact, child, additional_paths)
3. If match found:
   a. Read project's `.claude/atlas.yaml` from disk (fresh read, updates cache)
   b. Mark as current project
4. **Child discovery**: If cwd is NOT an exact project match, scan for projects inside cwd:
   a. Find `.claude/atlas.yaml` files up to 3 levels deep
   b. Find `.git/` directories up to 2 levels deep (unregistered repos)
   c. Cross-reference with registry: mark as registered or discovered
5. **Output project index** — registered projects with summaries, discovered projects with registration prompt

### Output: Case 1 — Inside a registered project

```
[atlas] Current: digital-web-sdk — Browser JS SDK for content personalization
[atlas] Projects:
  digital-web-sdk *  Browser JS SDK for content personalization — TypeScript, Vite
  digital-collector  Snowplow event collector service — Scala, Kafka
  digital-enrich     Event enrichment pipeline — Scala, Kafka
  my-tool        AI dev workflow orchestration — TypeScript, Node
```

No child discovery needed — we're in a specific project.

### Output: Case 2 — In a workspace root (e.g., `~/dev/digital/`)

```
[atlas] Workspace: ~/dev/digital/
[atlas] Local projects:
  digital-web-sdk      Browser JS SDK for content personalization — TypeScript, Vite
  digital-collector    Snowplow event collector service — Scala, Kafka
  digital-enrich       Event enrichment pipeline — Scala, Kafka
  digital-router       (not registered — /atlas:projects add)
  digital-s3-loader    (not registered — /atlas:projects add)
[atlas] Other projects:
  my-tool          AI dev workflow orchestration — TypeScript, Node
  clawrig-atlas    Project registry for Claude sessions — Claude plugin
```

"Local projects" = found inside cwd (registered + discovered). "Other projects" = registered but elsewhere.

### Output: Case 3 — No match, no children

```
[atlas] Projects:
  digital-web-sdk    Browser JS SDK for content personalization — TypeScript, Vite
  my-tool        AI dev workflow orchestration — TypeScript, Node
  ...
```

Just the global index. No current project, no local discoveries.

### `*` marks and labels

- Registered projects with `.claude/atlas.yaml` → slug + summary
- Discovered but unregistered → slug + `(not registered — /atlas:projects add)`
- Discovered git repos without atlas config → dirname + `(git repo, not registered)`

### Scaling

- **< 30 projects**: Full index output (one line per project)
- **30+ projects**: Output 30 most recently accessed, append `... and N more`
- If no projects registered and none discovered: `[atlas] No projects found. Use /atlas:projects add`

### Performance

- Registry match: read YAML, string compare — fast
- Child discovery: `find` with `maxdepth 3-4`, bounded — target < 500ms
- Skip child discovery if cwd IS a registered project (already specific enough)
- Cache discovery results per directory to avoid redundant scans
- No network calls
- Skip entirely if `registry.yaml` doesn't exist (atlas not initialized)

### Context Cost

~50 tokens per project. For a typical working set of 5-20 projects: 250-1000 tokens. Discovered-but-unregistered projects add ~30 tokens each.
