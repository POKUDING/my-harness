# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - Configure project-level API tokens (saved to `.harness/config.env`, gitignored)
- `/proj-status` - Analyze current project status (git, files, dependencies)
- `/proj-review` - Run a structured code review workflow
- `/slack-list-plan` - Slack List에서 작업 계획서 자동 생성
- `/task-review` - Slack List 미완료 항목 확인 → 코드리뷰 → 완료 처리

## Agents
- `my-harness:researcher` (Sonnet) - Deep codebase research and analysis
- `my-harness:quick-fix` (Haiku) - Fast, lightweight fixes and lookups

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
