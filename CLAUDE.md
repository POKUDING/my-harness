# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - Configure project-level API tokens (saved to `.harness/config.env`, gitignored)
- `/proj-status` - Analyze current project status (git, files, dependencies)
- `/proj-review` - Run a structured code review workflow
- `/slack-list-plan` - Slack List에서 작업 계획서 자동 생성
- `/task-review` - Slack List 미완료 항목 확인 → 코드리뷰 → 완료 처리
- `/code-review` - 다중 에이전트 합의 기반 코드 리뷰 (PR/diff → 심각도 기반 리포트)

## Agents
- `my-harness:researcher` (Sonnet) - Deep codebase research and analysis
- `my-harness:quick-fix` (Haiku) - Fast, lightweight fixes and lookups

## Harness: code-review

**목표:** 다중 에이전트 합의 기반 코드 리뷰 시스템

**트리거:** 코드 리뷰, PR 리뷰, diff 리뷰 요청 시 `/code-review` 스킬을 사용하라.

**에이전트:**
- `code-review-orchestrator` (Opus) — 메인 오케스트레이터
- `review-supervisor` (Opus) — 리뷰 감독 (A/B 독립 운용)
- `correctness-agent` (Sonnet) — 정확성
- `reliability-agent` (Sonnet) — 안정성
- `security-agent` (Sonnet) — 보안
- `performance-agent` (Sonnet) — 성능
- `maintainability-agent` (Opus) — 유지보수성
- `report-comparator` (Opus) — 보고서 비교 분석

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-10 | 초기 구성 | 전체 | 코드 품질/유지보수성 향상을 위한 리뷰 시스템 |

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
