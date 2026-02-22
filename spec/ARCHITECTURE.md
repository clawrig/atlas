# Atlas — Project Registry & Awareness

## Overview

Atlas is a Claude Code plugin that provides **global project awareness** across all sessions. It maintains a central registry of projects with their metadata, links, documentation references, and issue tracker configurations. Any Claude session — regardless of working directory — can query atlas to understand the project landscape.

## Core Responsibilities

1. **Project Registry** — CRUD operations on project definitions
2. **Session Context Injection** — Detect current project on session start, inject context
3. **Documentation Bridge** — Connect projects to their docs via Context7 integration
4. **Foundation for Relay** — Provide project metadata that relay uses for issue routing and handoff

## Plugin Structure

```
atlas/
├── .claude-plugin/
│   └── plugin.json
├── hooks/
│   ├── hooks.json
│   └── scripts/
│       └── project-detect.sh         # SessionStart: match cwd → project
├── skills/
│   ├── projects/SKILL.md             # /atlas:projects — manage project registry
│   ├── docs/SKILL.md                 # /atlas:docs — query project documentation
│   └── context/SKILL.md              # /atlas:context — show current project info
├── knowledge/
│   ├── schema.md                     # Project definition schema reference
│   └── integrations.md              # How atlas connects to other tools
├── spec/                             # This directory — design documents
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
- Data stored as YAML files on local filesystem

### 2. Global Scope

Project data lives in `~/.claude/atlas/` — accessible from any working directory, any session, any machine (if synced).

### 3. Convention Over Configuration

- Auto-detect project from `cwd` matching registered paths
- Auto-detect repo type from `.git/config`
- Sensible defaults for everything

### 4. Foundation, Not Framework

Atlas provides data. It doesn't enforce workflows. Relay, beads, and clawrig build on top of atlas data without atlas needing to know about them.

### 5. Cross-Tool Compatibility

- Skills are markdown — portable to OpenClaw
- Data is YAML — readable by any tool
- No Claude Code-specific bash in skill logic where avoidable
