# Atlas — Project Registry & Awareness

## Overview

Atlas is a Claude Code plugin that provides **global project awareness** across all sessions. It maintains a minimal central registry of project locations and discovers rich project metadata from config files stored in each project's repository. Any Claude session — regardless of working directory — can query atlas to understand the project landscape.

## Core Responsibilities

1. **Project Registry** — Track which projects you're working on (slug → path + repo)
2. **Config Discovery** — Pick up `.claude/atlas.yaml` from project repos, cache and serve it
3. **Session Context Injection** — Detect current project on session start, inject context
4. **Documentation Bridge** — Connect projects to their docs via Context7 integration
5. **Foundation for Other Plugins** — Provide project metadata that relay, beads, fam build on

## Key Architectural Decision

**Atlas does NOT own project metadata centrally.** Project configs (links, tags, docs, notes) live in each project's repo as `.claude/atlas.yaml`. Atlas only owns the registry mapping: "slug X is at path Y with repo Z."

This means:
- Project metadata is version-controlled and team-shared
- Cloning a repo brings its config along
- No central file that drifts out of sync
- Atlas discovers, caches, and serves — it doesn't define

## Plugin Structure

```
atlas/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── project-detect.sh         # SessionStart: match cwd → project, refresh cache
├── skills/
│   ├── projects/SKILL.md             # /atlas:projects — manage registry & configs
│   ├── docs/SKILL.md                 # /atlas:docs — query project documentation
│   └── context/SKILL.md              # /atlas:context — show current project info
├── knowledge/
│   ├── schema.md                     # .claude/atlas.yaml schema reference
│   └── integrations.md              # How atlas connects to other tools
├── spec/
│   ├── ARCHITECTURE.md
│   ├── DATA_MODEL.md
│   ├── INTEGRATION.md
│   └── SKILLS.md
└── README.md
```

## Design Principles

### 1. Lightweight & Always-On

Atlas loads on every session. It must be fast:
- SessionStart hook should complete in < 2 seconds
- No heavy dependencies (no database, no network calls at startup)
- Central registry is a tiny YAML file

### 2. Discover, Cache, Serve

Atlas is a **cache layer** over distributed project configs:
- Each project defines itself via `.claude/atlas.yaml` in its repo
- Atlas discovers these configs, caches them in `~/.claude/atlas/cache/`
- Cache is refreshed on session start (for current project) or on demand (all projects)

### 3. Minimal Central State

The central `~/.claude/atlas/registry.yaml` stores ONLY:
- Project slug
- Local filesystem path
- Remote repo URL
- Optional additional paths (for monorepo cwd matching)

Everything else comes from the project's own config file.

### 4. Convention Over Configuration

- Auto-detect project from `cwd` matching registered paths
- Auto-detect repo URL from `.git/config`
- Auto-create `.claude/atlas.yaml` with sensible defaults
- Suggest creating config if project repo doesn't have one

### 5. Foundation, Not Framework

Atlas provides data. It doesn't enforce workflows. Relay owns issue routing. Beads owns local issues. Fam owns session orchestration. Atlas just answers: "What project is this? What do I know about it?"

### 6. Cross-Tool Compatibility

- Skills are markdown — portable to OpenClaw
- Data is YAML — readable by any tool
- Per-project config is in `.claude/` — follows Claude Code conventions
- No Claude Code-specific bash in skill logic where avoidable
