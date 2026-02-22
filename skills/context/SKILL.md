---
name: context
description: Show full project details from atlas — links, tags, docs, notes. Use when needing detailed project info beyond what the session start index provides, or when another tool needs project metadata.
argument-hint: "[--project <slug>] [--json]"
---

# Atlas Project Context

Show detailed project information on demand (Tier 2 — full details).

## Parse Arguments

Parse `$ARGUMENTS`:
- `--project <slug>`: Specific project to show. If omitted, detect from cwd.
- `--json`: Output as JSON (for programmatic consumption by other tools).
- Positional argument treated as slug if no `--project` flag.

## Resolve Project

1. If `--project <slug>` or positional slug provided, use it
2. Otherwise, detect from current working directory:
   - Read `~/.claude/atlas/registry.yaml`
   - Match `$PWD` against project paths (exact match, then child match, then additional_paths)
   - Deepest match wins
3. If no project resolved, inform the user:
   ```
   Not in a registered project. Use --project <slug> or cd to a project directory.
   Registered projects: <list slugs>
   ```

## Load Project Data

1. Read registry entry for the resolved slug: `path`, `repo`, `additional_paths`
2. Read cached config: `~/.claude/atlas/cache/projects/<slug>.yaml`
3. If cache doesn't exist, try reading directly from `<path>/.claude/atlas.yaml`
4. If neither available, show registry-only info with a note

## Output: Human Format (default)

```
Project: <name> (<slug>)
Path: <path>
Repo: <repo>
Group: <group>
Tags: <comma-separated tags>

Links:
  <name>    → <url>
  <name>    → <url>

Docs:
  Context7: <context7_id>
  Local:    <local path>

Notes:
  <notes content>

Metadata:
  <key>: <value>
```

Omit sections that have no data (don't show empty "Links:" if there are no links).

## Output: JSON Format (--json)

Merge registry data with cached config into a single JSON object:

```json
{
  "slug": "<slug>",
  "path": "<path>",
  "repo": "<repo>",
  "name": "<name>",
  "summary": "<summary>",
  "group": "<group>",
  "tags": ["<tag>", ...],
  "links": { "<name>": "<url>", ... },
  "docs": { "context7_id": "...", "local": "..." },
  "notes": "<notes>",
  "metadata": { "<key>": "<value>" },
  "_cache_meta": { "cached_at": "...", "source": "..." }
}
```

Output this JSON using a code block so it's easy to copy.
