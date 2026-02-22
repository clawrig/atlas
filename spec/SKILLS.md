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
   - **Exists** → read it, cache it, show summary
   - **Missing** → offer to create one:
     - Auto-detect name from `package.json` / `Cargo.toml` / directory name
     - Auto-detect tags from language/framework
     - Guess CI link from repo URL
     - Write `.claude/atlas.yaml` to the project repo
6. Cache the project config

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

**Purpose**: Initialize atlas for first-time use.

```
/atlas:init
```

### Flow

1. Create `~/.claude/atlas/` directory structure
2. Create empty `registry.yaml`
3. Offer to register current directory as a project (runs `add` flow)
4. Print quick-start guide

---

## Hook: SessionStart — project-detect

**Purpose**: Auto-detect current project, refresh cache, inject context.

### Behavior

1. Read `~/.claude/atlas/registry.yaml`
2. Match `$PWD` against all project paths (exact, child, additional_paths)
3. If match found:
   a. Read project's `.claude/atlas.yaml` from disk (fresh read, updates cache)
   b. Output compact project summary
4. If no match: silent (no output, no error)

### Performance

- Pure bash: read YAML, pattern match, read project config, print
- No network calls
- Target: < 500ms execution
- Skip if `registry.yaml` doesn't exist (atlas not initialized)

### Output

Compact one-liner printed to stdout:

```
[atlas] digital-web-sdk | gitlab | tags: sdk, typescript | 3 links
```

Full details available via `/atlas:context`.
