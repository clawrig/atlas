# Atlas Schema Reference

## Central Registry: `~/.claude/atlas/registry.yaml`

Minimal mapping of project slugs to filesystem paths.

```yaml
projects:
  <slug>:
    path: <absolute-or-tilde-path>    # Required. Filesystem path to project root
    repo: <url>                        # Required. Git remote URL
    additional_paths:                  # Optional. Extra paths that resolve to this project
      - <path>
```

### Rules

- **slug**: lowercase kebab-case, unique identifier (e.g., `digital-web-sdk`)
- **path**: supports `~` expansion (e.g., `~/dev/project`)
- **repo**: HTTPS or SSH git remote URL
- **additional_paths**: for monorepo child dirs or related directories that should resolve to this project

### Example

```yaml
projects:
  digital-web-sdk:
    path: ~/dev/digital/clients/digital-personalization-web-sdk
    repo: https://git.angara.cloud/digital/web-sdk
    additional_paths:
      - ~/dev/digital/clients/digital-personalization-tags

  fam:
    path: ~/dev/personal/fam
    repo: https://github.com/iVintik/fam
```

## Per-Project Config: `<project-root>/.claude/atlas.yaml`

Lives in the project repo, version-controlled, team-shared.

```yaml
name: <string>              # Required. Human-readable project name
summary: <string>           # Required. One-liner <100 chars for project index
tags: [<string>, ...]       # Optional. Categorization tags
group: <string>             # Optional. Logical grouping (e.g., "digital-platform")

links:                      # Optional. Quick-access URLs
  docs: <url>
  ci: <url>
  staging: <url>
  figma: <url>
  confluence: <url>
  # Any key: value pairs

docs:                       # Optional. Documentation sources
  context7_id: <string>     # Context7 library ID (e.g., "/npm/react")
  context7_query: <string>  # Fallback query for Context7 ID resolution
  local: <path>             # Local docs directory (relative to project root)
  readme: <path>            # README path (relative to project root)

notes: |                    # Optional. Free-form notes (multiline string)
  Build: npm run build
  Test: npm run test

metadata:                   # Optional. Arbitrary key-value pairs
  team: <string>
  language: <string>
  framework: <string>
```

### Field Details

| Field | Required | Constraint | Used In |
|-------|----------|------------|---------|
| `name` | Yes | — | Context skill, project details |
| `summary` | Yes | <100 chars | Session start index (every session) |
| `tags` | No | Array of strings | Filtering (`list --tag`) |
| `group` | No | String | Filtering (`list --group`) |
| `links` | No | Map of name→URL | Context skill |
| `docs` | No | Map | Docs skill, Context7 bridge |
| `notes` | No | Multiline string | Context skill |
| `metadata` | No | Map | Extensible metadata |

## Cache Structure: `~/.claude/atlas/cache/`

```
~/.claude/atlas/cache/
├── projects/
│   └── <slug>.yaml          # Cached copy of project's .claude/atlas.yaml + _cache_meta
└── context7-ids.yaml        # Cached Context7 library ID resolutions
```

### Cached Project File

```yaml
_cache_meta:
  source: <absolute-path-to-source-file>
  cached_at: "<ISO-8601 timestamp>"
  repo: <repo-url>

# ... exact copy of the project's .claude/atlas.yaml fields
name: "..."
summary: "..."
tags: [...]
```

## Path Matching Rules

Used by SessionStart hook to detect current project:

1. **Exact match**: `$PWD == project.path` (highest priority)
2. **Child match**: `$PWD` starts with `project.path/` (deeper path wins)
3. **Additional paths**: `$PWD == additional_path` or starts with `additional_path/`
4. **Deepest wins**: When multiple projects match, the most specific (deepest) path wins
