---
name: init
description: Initialize atlas for first-time use — creates directories, registers the SessionStart hook, discovers and registers projects in the current directory. Use when atlas has not been set up yet or to re-scan for projects.
argument-hint: "[--scan <path>]"
---

# Atlas Initialization

Set up atlas for first-time use and discover projects.

## Parse Arguments

Parse `$ARGUMENTS`:
- `--scan <path>`: Directory to scan for projects. Defaults to current working directory.

## Step 1: Create Directory Structure

Create the atlas directories if they don't exist:

```
~/.claude/atlas/
~/.claude/atlas/cache/projects/
```

Use Bash `mkdir -p` for this.

## Step 2: Create Registry

If `~/.claude/atlas/registry.yaml` doesn't exist, create it with:

```yaml
# Atlas project registry — maps project slugs to filesystem paths.
# Managed by /atlas:projects. See knowledge/schema.md for format.

projects:
```

If it already exists, leave it as-is.

## Step 3: Register SessionStart Hook (Workaround)

**Context**: Plugin SessionStart hooks don't surface output to Claude due to a known bug (#16538). As a workaround, register the hook directly in `~/.claude/settings.local.json` where it works correctly.

1. Read `~/.claude/settings.local.json` (create `{}` if it doesn't exist)
2. Determine the absolute path to the hook script. The plugin root is the directory containing `.claude-plugin/plugin.json`. From the plugin root, the script is at `hooks/scripts/session-start.py`.
   - To find the plugin root: use the path of this skill file and navigate up to find `.claude-plugin/plugin.json`
   - The plugin is installed at a path like `/Users/.../famdeck-atlas/` — resolve this to an absolute path
3. Add a SessionStart hook entry. Use Bash with `jq` to merge:

```bash
jq --arg script "python3 <ABSOLUTE_PATH>/hooks/scripts/session-start.py" '
  .hooks //= {} |
  .hooks.SessionStart //= [] |
  if (.hooks.SessionStart | map(select(.hooks[]?.command == $script)) | length) > 0
  then .
  else .hooks.SessionStart += [{
    "matcher": "*",
    "hooks": [{
      "type": "command",
      "command": $script,
      "timeout": 5
    }]
  }]
  end
' ~/.claude/settings.local.json > /tmp/atlas-settings.json && mv /tmp/atlas-settings.json ~/.claude/settings.local.json
```

4. Confirm registration to the user.

## Step 4: Scan for Projects

Scan the target directory (cwd or `--scan` path) for projects:

1. Use Bash to find `.git/` directories up to 3 levels deep:
   ```bash
   find <scan-path> -maxdepth 3 -name ".git" -type d 2>/dev/null
   ```

2. For each found git repo:
   - Extract the project directory (parent of `.git/`)
   - Check if `.claude/atlas.yaml` exists in it
   - Detect repo URL from `.git/config` (read the `[remote "origin"]` url)
   - Generate a slug from the directory name (lowercase kebab-case)

3. Present discovered projects as a table:
   ```
   Found N projects:
     slug              path                                    has atlas.yaml
     digital-web-sdk   ~/dev/digital/.../web-sdk               yes
     digital-collector ~/dev/digital/digital-collector          no
     my-tool       ~/dev/personal/my-tool                yes
   ```

4. Ask the user which projects to register using AskUserQuestion:
   - Option 1: "Register all" (default/recommended)
   - Option 2: "Let me choose"
   - Option 3: "Skip for now"

## Step 5: Register Selected Projects

For each project to register:

1. Read the current `~/.claude/atlas/registry.yaml`
2. Append the project entry under `projects:`:
   ```yaml
     <slug>:
       path: <path>
       repo: <repo-url>
   ```
3. If `.claude/atlas.yaml` exists in the project:
   - Read it and cache to `~/.claude/atlas/cache/projects/<slug>.yaml` (prepend `_cache_meta`)
   - Check that `summary` field exists — warn if missing
4. If `.claude/atlas.yaml` does NOT exist:
   - Offer to create a minimal one:
     - Auto-detect `name` from `package.json` (name field), `Cargo.toml`, `build.gradle`, or directory name
     - Ask for `summary` (suggest based on detected info, must be <100 chars)
     - Auto-detect tags from language/framework files present
     - Guess CI link from repo URL pattern
   - Write `.claude/atlas.yaml` to the project
   - Cache it

## Step 6: Summary

Print a summary:
```
Atlas initialized!
  Registry: ~/.claude/atlas/registry.yaml
  Projects registered: N
  Hook registered: yes (in ~/.claude/settings.local.json)

  Next steps:
  - Start a new Claude session to see the project index
  - Use /atlas:projects add to register more projects
  - Use /atlas:projects edit <slug> to customize project configs
```
