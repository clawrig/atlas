---
name: projects
description: Manage the atlas project registry — add, list, show, edit, remove, link, and refresh projects. Use when the user wants to register a project, list registered projects, view project details, update project configs, or manage the atlas registry.
argument-hint: "[list|add|show|edit|remove|link|refresh] [options]"
---

# Atlas Project Management

Manage the central project registry and per-project configs.

## Parse Arguments

Parse `$ARGUMENTS` for subcommand and options:

- **No args or `list`**: List all projects
- **`add`**: Register a new project
- **`show [slug]`**: Show project details
- **`edit [slug]`**: Edit project config
- **`remove <slug>`**: Remove project from registry
- **`link <name> <url> [--project <slug>]`**: Add/update a link
- **`refresh [slug]`**: Refresh cache

Options that apply across subcommands:
- `--project <slug>` or positional slug: target a specific project
- `--group <name>`: filter by group (list only)
- `--tag <name>`: filter by tag (list only)

## File Paths

- Registry: `~/.claude/atlas/registry.yaml`
- Cache dir: `~/.claude/atlas/cache/projects/`
- Project config: `<project-path>/.claude/atlas.yaml`

Refer to `knowledge/schema.md` for the full schema.

## Subcommand: list (default)

1. Read `~/.claude/atlas/registry.yaml`
2. For each project, read its cached config from `~/.claude/atlas/cache/projects/<slug>.yaml`
3. If `--group` specified: filter to projects matching that group
4. If `--tag` specified: filter to projects with that tag in their tags array
5. If cache is empty for all/most projects, suggest running `/atlas:projects refresh`

Output as a table:
```
Atlas Projects (N registered):

  Slug                 Group              Tags                 Summary
  digital-web-sdk      digital-platform   sdk, typescript      Browser JS SDK for content personalization
  digital-collector    digital-platform   scala, kafka         Snowplow event collector service
  fam              —                  typescript, node     AI dev workflow orchestration
```

## Subcommand: add

1. Determine project path:
   - If `--path <path>` given, use it
   - Otherwise use current working directory
2. Verify the path exists and contains a `.git/` directory
3. Auto-detect repo URL: read `.git/config`, extract `[remote "origin"]` url
4. Suggest slug from directory name (lowercase kebab-case). Ask user to confirm or change.
5. Check if slug already exists in registry — if so, warn and ask to overwrite or choose different slug.
6. Read current `~/.claude/atlas/registry.yaml` and append the new project:
   ```yaml
     <slug>:
       path: <path>
       repo: <repo-url>
   ```
   Use the Edit tool to append before the end of the `projects:` block, or Write if the file needs restructuring.

7. Check for `.claude/atlas.yaml` in the project:

   **If it exists:**
   - Read it
   - Validate that `summary` field exists and is <100 chars
   - If `summary` missing, warn and ask user to provide one
   - Cache it: write to `~/.claude/atlas/cache/projects/<slug>.yaml` with `_cache_meta` header

   **If it doesn't exist:**
   - Offer to create one. Auto-detect:
     - `name`: from `package.json` name, `Cargo.toml` package name, `build.gradle` project name, or directory name
     - `summary`: suggest based on name + detected language/framework. Must be <100 chars.
     - `tags`: from detected files (package.json → typescript/javascript, Cargo.toml → rust, etc.)
     - `links.ci`: guess from repo URL (gitlab → `<repo>/-/pipelines`, github → `<repo>/actions`)
   - Ask user to confirm/edit the generated config
   - Write `.claude/atlas.yaml` to the project's `.claude/` directory (create dir if needed)
   - Cache it

8. Confirm: `Registered: <slug> → <path>`

## Subcommand: show

1. Resolve slug:
   - If slug provided, use it
   - If no slug, detect from cwd by matching against registry paths (same logic as hook)
   - If can't resolve, ask user
2. Read registry entry for path and repo
3. Read cached config from `~/.claude/atlas/cache/projects/<slug>.yaml`
4. If cache missing, try to read directly from `<path>/.claude/atlas.yaml`

Output formatted details:
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

1. Resolve slug (same as show)
2. Read the project's `.claude/atlas.yaml` from disk (not cache)
3. Present the current content to the user
4. Ask what they want to change (or let them provide edits)
5. Apply changes using the Edit tool on the project's `.claude/atlas.yaml`
6. Refresh the cache: copy updated file to `~/.claude/atlas/cache/projects/<slug>.yaml` with `_cache_meta`
7. Confirm changes

## Subcommand: remove

1. Require slug argument
2. Read registry, verify slug exists
3. Ask for confirmation: "Remove <slug> from atlas? (config in project repo will NOT be deleted)"
4. Remove the slug's block from `registry.yaml` using Edit tool
5. Delete cache file `~/.claude/atlas/cache/projects/<slug>.yaml` if it exists (Bash `rm -f`)
6. Confirm removal

## Subcommand: link

Syntax: `/atlas:projects link <name> <url> [--project <slug>]`

1. Resolve project slug (from `--project` or cwd)
2. Read the project's `.claude/atlas.yaml`
3. If `links:` section exists:
   - If link name already exists, update the URL
   - If link name is new, add it under `links:`
4. If `links:` section doesn't exist, add it with the new link
5. Use Edit tool to modify the file
6. Refresh the cache
7. Confirm: `Added link: <name> → <url>`

## Subcommand: refresh

1. If specific slug provided, refresh only that project
2. Otherwise, walk all projects in registry

For each project:
1. Read registry entry for path
2. Check if path exists on disk:
   - **Path exists**: Read `.claude/atlas.yaml`, update cache with `_cache_meta`
   - **Path missing**: Warn `<slug>: path not found (<path>) — using stale cache`
3. Check if `.claude/atlas.yaml` exists:
   - **Exists**: Cache it
   - **Missing**: Warn `<slug>: no .claude/atlas.yaml — consider running /atlas:projects edit <slug>`
4. Validate `summary` field exists

Report summary:
```
Refreshed N projects:
  digital-web-sdk      ✓ cached
  digital-collector    ✓ cached
  old-project          ⚠ path not found
  new-project          ⚠ no atlas.yaml
```
