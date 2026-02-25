---
name: projects
description: "Manage the atlas project registry — add, list, show, edit, remove, link, and refresh projects. Use when registering projects, viewing project details, or managing the atlas registry."
metadata: {"openclaw":{"emoji":"🗺️"}}
---

# Atlas Project Management

Manage the central project registry and per-project configs.

## When to Use

- User wants to register a project, list registered projects, view details
- User wants to update project configs, add links, or refresh cache
- User asks about project structure or registry

## Parse Arguments

Parse `$ARGUMENTS` for subcommand and options:

- **No args or `list`**: List all projects
- **`add`**: Register a new project
- **`show [slug]`**: Show project details
- **`edit [slug]`**: Edit project config
- **`remove <slug>`**: Remove project from registry
- **`link <name> <url> [--project <slug>]`**: Add/update a link
- **`refresh [slug]`**: Refresh cache

Options:
- `--project <slug>` or positional slug: target a specific project
- `--group <name>`: filter by group (list only)
- `--tag <name>`: filter by tag (list only)

## File Paths

- Registry: `~/.claude/atlas/registry.yaml`
- Cache dir: `~/.claude/atlas/cache/projects/`
- Project config: `<project-path>/.claude/atlas.yaml`

## Subcommand: list (default)

1. Read `~/.claude/atlas/registry.yaml`
2. For each project, read its cached config from `~/.claude/atlas/cache/projects/<slug>.yaml`
3. If `--group` specified: filter to projects matching that group
4. If `--tag` specified: filter to projects with that tag
5. If cache is empty for all/most projects, suggest running `/projects refresh`

Output:
```
Atlas Projects (N registered):

  Slug                 Group              Tags                 Summary
  digital-web-sdk      digital-platform   sdk, typescript      Browser JS SDK
  digital-collector    digital-platform   scala, kafka         Event collector
  my-tool          —                  typescript, node     AI dev workflow
```

## Subcommand: add

1. Determine project path (`--path <path>` or cwd)
2. Verify path exists and contains `.git/`
3. Auto-detect repo URL from `.git/config` remote origin
4. Suggest slug from directory name (lowercase kebab-case), ask user to confirm
5. Check if slug already exists — warn if so
6. Append to `~/.claude/atlas/registry.yaml`:
   ```yaml
   <slug>:
     path: <path>
     repo: <repo-url>
   ```
7. Check for `.claude/atlas.yaml` in the project:
   - **Exists**: validate `summary` field (<100 chars), cache it
   - **Missing**: offer to create one with auto-detected name, summary, tags, links

Confirm: `Registered: <slug> → <path>`

## Subcommand: show

1. Resolve slug (from arg, or detect from cwd via registry path matching)
2. Read registry entry + cached config

Output:
```
Project: <name> (<slug>)
Path: <path>
Repo: <repo>
Group: <group>
Tags: <tags>

Links:
  docs    → <url>
  ci      → <url>

Notes:
  <notes content>
```

## Subcommand: edit

1. Resolve slug
2. Read `<project-path>/.claude/atlas.yaml` from disk (not cache)
3. Present current content, ask what to change
4. Apply edits
5. Refresh cache

## Subcommand: remove

1. Require slug argument
2. Confirm with user
3. Remove from `registry.yaml`
4. Delete cache file if it exists

## Subcommand: link

Syntax: `/projects link <name> <url> [--project <slug>]`

1. Resolve project slug
2. Read `.claude/atlas.yaml`
3. Add/update link under `links:` section
4. Refresh cache

## Subcommand: refresh

1. If specific slug, refresh only that project; otherwise walk all
2. For each project:
   - Check path exists on disk
   - Read `.claude/atlas.yaml`, update cache with `_cache_meta`
   - Warn on missing paths or configs

Output:
```
Refreshed N projects:
  digital-web-sdk      ✓ cached
  digital-collector    ✓ cached
  old-project          ⚠ path not found
```

## Schema Reference

### Registry (`~/.claude/atlas/registry.yaml`)

```yaml
projects:
  <slug>:
    path: <absolute-or-tilde-path>    # Required
    repo: <url>                        # Required
    additional_paths:                  # Optional
      - <path>
```

- **slug**: lowercase kebab-case, unique
- **path**: supports `~` expansion
- **repo**: HTTPS or SSH git remote URL
- **additional_paths**: monorepo child dirs or related directories

### Per-Project Config (`<project>/.claude/atlas.yaml`)

```yaml
name: <string>              # Required. Human-readable name
summary: <string>           # Required. One-liner <100 chars
tags: [<string>, ...]       # Optional. Categorization
group: <string>             # Optional. Logical grouping

links:                      # Optional. Quick-access URLs
  docs: <url>
  ci: <url>
  staging: <url>

docs:                       # Optional. Documentation sources
  context7_id: <string>
  local: <path>
  readme: <path>

notes: |                    # Optional. Free-form notes
  Build: npm run build

metadata:                   # Optional. Arbitrary key-value
  team: <string>
  language: <string>
```

### Cache (`~/.claude/atlas/cache/projects/<slug>.yaml`)

```yaml
_cache_meta:
  source: <absolute-path>
  cached_at: "<ISO-8601>"
  repo: <repo-url>

# ... copy of project's atlas.yaml fields
```

### Path Matching Rules (for project detection)

1. Exact match: `$PWD == project.path`
2. Child match: `$PWD` starts with `project.path/`
3. Additional paths: same rules
4. Deepest wins when multiple match
