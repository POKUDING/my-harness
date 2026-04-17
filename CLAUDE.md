# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - Configure project-level API tokens (saved to `.harness/config.env`, gitignored)
- `/proj-status` - Analyze current project status (git, files, dependencies)
- `/proj-review` - Run a structured code review workflow
- `/slack-list-plan` - Slack List에서 작업 계획서 자동 생성
- `/task-review` - Slack List 미완료 항목 확인 → 코드리뷰 → 완료 처리
- `/code-review` - 다중 에이전트 합의 기반 코드 리뷰 (PR/diff → 심각도 기반 리포트)
- `/code-review-fix` - 코드 리뷰 결과의 fix_now 항목을 파일별 병렬 수정
- `/init-guide` - 프로젝트 분석 → `.harness/guide.md` 가이드 문서 생성/업데이트
- `/guide-check` - 가이드 vs 현재 코드 비교 → 불일치 항목 확인 및 저장 (히스토리 기반 범위 자동 결정)
- `/guide-fix` - guide-check 결과의 불일치 항목을 가이드에 반영하고 기록 저장

## Agents
- `my-harness:researcher` (Sonnet) - Deep codebase research and analysis
- `my-harness:quick-fix` (Haiku) - Fast, lightweight fixes and lookups

## Harness: code-review

**목표:** 다중 에이전트 합의 기반 코드 리뷰 시스템

**트리거:** 코드 리뷰, PR 리뷰, diff 리뷰 요청 시 `/code-review` 스킬을 사용하라.

**에이전트:**
- `my-harness:cr-orchestrator` (Opus) — 메인 오케스트레이터
- `my-harness:cr-supervisor` (Opus) — 리뷰 감독 (A/B 독립 운용)
- `my-harness:cr-correctness` (Sonnet) — 정확성
- `my-harness:cr-reliability` (Sonnet) — 안정성
- `my-harness:cr-security` (Sonnet) — 보안
- `my-harness:cr-performance` (Sonnet) — 성능
- `my-harness:cr-maintainability` (Opus) — 유지보수성
- `my-harness:cr-report-comparator` (Opus) — 보고서 비교 분석
- `my-harness:cr-fix` (Sonnet) — 파일별 finding 수정 실행

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-10 | 초기 구성 | 전체 | 코드 품질/유지보수성 향상을 위한 리뷰 시스템 |
| 2026-04-10 | fix-agent + code-review-fix 추가 | agents, skills | 리뷰 결과 병렬 자동 수정 |
| 2026-04-17 | 에이전트를 `agents/` 플랫 구조로 이동, `cr-` prefix 적용 | agents | 플러그인 네이티브 `subagent_type` 등록 |

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
