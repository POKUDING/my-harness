# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - 프로젝트 단위 API 토큰 설정 (`.harness/config.env`에 저장, gitignored)
- `/proj-status` - 현재 프로젝트 상태 분석 (git, 파일, 의존성)
- `/code-review-quick` - 빠른 단일 에이전트 코드 리뷰 (가벼운 점검). 본격 리뷰는 `/code-review` 사용
- `/slack-plan` - Slack List에서 작업 계획서 자동 생성
- `/slack-review` - Slack List 미완료 항목 확인 → 코드리뷰 → 완료 처리
- `/code-review` - 다중 에이전트 합의 기반 코드 리뷰 (PR/diff → 심각도 기반 리포트, flat 5×2 + comparator)
- `/code-review-slim` - 슬림 3-agent 리뷰 (Direct + Indirect + Comparator). `/code-review`와 교차 비교용 대안. 비용 약 1/3
- `/code-review-fix` - 코드 리뷰 결과의 fix_now 항목을 파일별 병렬 수정
- `/code-review-walk` - 리뷰 finding을 하나씩 유저와 함께 점검 (작업/패스/보류 상태 저장, 다음 실행 시 중복 제외)
- `/guide-init` - 프로젝트 분석 → `.harness/guide.md` 가이드 문서 생성/업데이트
- `/guide-check` - 가이드 vs 현재 코드 비교 → 불일치 항목 확인 및 저장 (히스토리 기반 범위 자동 결정)
- `/guide-fix` - guide-check 결과의 불일치 항목을 가이드에 반영하고 기록 저장
- `/plan-execute` - 작업 계획서(docs/plans/*-plan.md)의 TODO를 의존성 분석 후 병렬 executor로 자동 구현 (ultrawork + ralph 패턴)
- `/api-summary` - 작업 완료 후 **협업팀 공유용** API 변경 요약 문서 생성 (독립 스킬, 체인의 일부 아님). 지정 범위의 API를 자동 파싱하여 신규/수정/삭제로 분류. Express/NestJS/FastAPI/Django REST/Flask 등 자동 감지

## Agents
- `my-harness:researcher` (Sonnet) - Deep codebase research and analysis
- `my-harness:quick-fix` (Haiku) - Fast, lightweight fixes and lookups
- `my-harness:plan-executor` (Sonnet) - 단일 TODO 구현 전담 (plan-execute에서 병렬로 스폰)

## Harness: code-review

**목표:** 다중 에이전트 합의 기반 코드 리뷰 시스템

**트리거:** 코드 리뷰, PR 리뷰, diff 리뷰 요청 시 `/code-review` 스킬을 사용하라.

**아키텍처 (v0.13+, Flat):** Claude Code는 subagent가 subagent를 spawn하는 것을 금지하므로 orchestrator/supervisor 중첩 구조가 불가능. 스킬이 메인 세션에서 직접 5 expert × 2 lens = 10개 + comparator 1개를 spawn하는 평탄화 구조로 전환.

**에이전트:**
- `my-harness:cr-correctness` (Sonnet) — 정확성 (Lens A/B) · /code-review
- `my-harness:cr-reliability` (Sonnet) — 안정성 (Lens A/B) · /code-review
- `my-harness:cr-security` (Sonnet) — 보안 (Lens A/B) · /code-review
- `my-harness:cr-performance` (Sonnet) — 성능 (Lens A/B) · /code-review
- `my-harness:cr-maintainability` (Opus) — 유지보수성 (Lens A/B) · /code-review
- `my-harness:cr-direct-reviewer` (Opus) — 5 카테고리 통합 리뷰어 (Lens A) · /code-review-slim
- `my-harness:cr-indirect-reviewer` (Opus) — 4 축 통합 리뷰어 (Lens B) · /code-review-slim
- `my-harness:cr-report-comparator` (Opus) — A-set/B-set 비교 분석 + 최종 리포트 파일 작성 · 공통
- `my-harness:cr-fix` (Sonnet) — 파일별 finding 수정 실행 · /code-review-fix

**Lens:** 각 전문 에이전트는 `Lens: A`(baseline) 또는 `Lens: B`(indirect-risk)로 프롬프트에 지정되어 호출된다. A는 카테고리 전체 체크리스트 균등 적용, B는 데코레이터/예외 경로·관용구 함정·future-risk·계약 일관성 같은 간접 위험에 우선순위.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-10 | 초기 구성 | 전체 | 코드 품질/유지보수성 향상을 위한 리뷰 시스템 |
| 2026-04-10 | fix-agent + code-review-fix 추가 | agents, skills | 리뷰 결과 병렬 자동 수정 |
| 2026-04-17 | 에이전트를 `agents/` 플랫 구조로 이동, `cr-` prefix 적용 | agents | 플러그인 네이티브 `subagent_type` 등록 |
| 2026-04-20 | 3단계 중첩 → flat 10-expert 구조로 재설계, cr-orchestrator/cr-supervisor 삭제, Lens A/B 도입 | agents, skills | Claude Code가 subagent의 nested spawn 미지원 (공식 문서 확정) |
| 2026-04-20 | /code-review-slim 추가 (cr-direct-reviewer + cr-indirect-reviewer + comparator, 총 3 spawn) | agents, skills, commands | 5×2 구조와 3-agent 구조의 효과 비교 측정용 |

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
