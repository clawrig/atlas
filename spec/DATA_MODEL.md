# Atlas — Data Model

## Storage Location

```
~/.claude/atlas/
├── projects.yaml              # Project registry (source of truth)
└── cache/
    └── context7-ids.yaml      # Cached context7 library ID resolutions
```

## Project Definition Schema

```yaml
# ~/.claude/atlas/projects.yaml
projects:

  # Key: project slug (short, unique identifier)
  digital-web-sdk:

    # Display name (optional, defaults to slug)
    name: "Digital Personalization Web SDK"

    # Local filesystem path (required)
    # Supports ~ expansion and environment variables
    path: ~/dev/digital/clients/digital-personalization-web-sdk

    # Additional paths (e.g., monorepo packages, related dirs)
    # Used for cwd matching — any of these paths trigger project detection
    additional_paths:
      - ~/dev/digital/clients/digital-personalization-tags

    # Repository information (auto-detected from .git if omitted)
    repo:
      type: github | gitlab | bitbucket | other
      url: https://git.angara.cloud/digital/web-sdk
      default_branch: main                    # Optional, default: main

    # Important links (freeform key-value)
    links:
      docs: https://docs.example.com/web-sdk
      ci: https://git.angara.cloud/digital/web-sdk/-/pipelines
      staging: https://staging.example.com
      figma: https://figma.com/file/abc123
      confluence: https://confluence.example.com/display/SDK

    # Documentation configuration
    docs:
      context7_id: "digital-web-sdk"          # Context7 library identifier
      context7_query: "digital personalization sdk"  # Fallback search query
      local: ./docs/                           # Local docs path (relative to project path)
      readme: ./README.md                      # Custom readme location

    # Tags for filtering and grouping
    tags:
      - sdk
      - typescript
      - frontend
      - digital-platform

    # Project group (optional, for organizing related projects)
    group: digital-platform

    # Issue tracker configuration
    # Used by relay plugin for issue routing
    # Order matters: first matching tracker is default
    issue_trackers:

      - name: gitlab                          # Tracker identifier (unique within project)
        type: gitlab                          # gitlab | github | jira | beads
        project_id: "digital/web-sdk"         # Tracker-specific project reference
        default: true                         # Primary tracker for this project
        labels:                               # Default labels applied to new issues
          - sdk
          - web
        routing_rules:                        # Optional: fine-grained routing
          - match:
              type: bug                       # Issue type
              priority: [critical, high]      # Priority levels
            action:
              labels: [urgent]                # Additional labels
              assignee: "@team-lead"          # Auto-assign

      - name: beads
        type: beads
        scope: local                          # local = project's own .beads/
        routing_rules:
          - match:
              type: task                      # Agent tasks stay in beads
              source: agent
            action:
              default: true                   # Override default for agent-created tasks

    # Free-form notes (injected into session context)
    notes: |
      Core JS SDK for the Digital Personalization Platform.
      Uses TypeScript, builds with Vite.
      Test with: npm run test
      Build with: npm run build

    # Custom metadata (freeform, for extensions)
    metadata:
      team: platform
      language: typescript
      framework: vanilla
```

## Project Groups

Projects can be organized into groups for batch operations:

```yaml
# Implicit grouping via 'group' field
# Query: /atlas:projects --group digital-platform
# Returns: all projects with group: digital-platform
```

## Auto-Detection

When a project is registered with only `path`, atlas auto-detects:

1. **Repo type & URL** — from `.git/config` remote origin
2. **Default branch** — from `.git/HEAD` or remote HEAD
3. **Language/framework** — from `package.json`, `Cargo.toml`, `build.gradle`, etc.
4. **Existing beads** — checks for `.beads/` directory

## Path Matching Rules

For SessionStart project detection:

1. Exact match: `cwd == project.path`
2. Child match: `cwd` is inside `project.path`
3. Additional paths: `cwd` matches any `additional_paths` entry
4. Deepest match wins (most specific project)
5. If no match: session runs without project context (atlas still available)

## Data Integrity

- `projects.yaml` is the single source of truth
- No database, no lock files
- Concurrent writes: last-write-wins (acceptable for manual registry)
- Backup: user can version-control `~/.claude/atlas/` in a dotfiles repo
