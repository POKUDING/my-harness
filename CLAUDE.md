# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - Configure project-level API tokens (saved to `.harness/config.env`, gitignored)
- `/proj-status` - Analyze current project status (git, files, dependencies)
- `/proj-review` - Run a structured code review workflow

## Agents
- `my-harness:researcher` (Sonnet) - Deep codebase research and analysis
- `my-harness:quick-fix` (Haiku) - Fast, lightweight fixes and lookups

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
