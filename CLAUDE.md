# my-harness - Personal Claude Code Plugin

Personal productivity plugin for Claude Code.

## Skills
- `/slack-setup` - 프로젝트 단위 API 토큰 설정 (`.harness/config.env`에 저장, gitignored)
- `/proj-status` - 현재 프로젝트 상태 분석 (git, 파일, 의존성)
- `/code-review-quick` - 빠른 단일 에이전트 코드 리뷰 (가벼운 점검). 본격 리뷰는 `/code-review` 사용
- `/slack-plan` - Slack List에서 작업 계획서 자동 생성
- `/slack-review` - Slack List 미완료 항목 확인 → 코드리뷰 → 완료 처리
- `/code-review` - 통합 다중 에이전트 코드 리뷰 (v0.15+, unified): Direct + Indirect baseline + 변경 패턴에 따른 Deep-Focus(0~3) + Comparator. 꼼꼼함 강화(Critical/Major reproduction·verification·reasoning 필수). 완료 시 major+ followup을 중앙 백로그에 자동 append
- `/code-review-fix` - 코드 리뷰 결과의 fix_now 항목을 파일별 병렬 수정
- `/review-backlog` - **v0.16+** 여러 리뷰에 걸친 followup/보류 항목 중앙 백로그 관리. list/resolve/dismiss/stale-check/import-all/stats. dedup key로 반복 지적된 이슈는 occurrence_count 누적
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

**아키텍처 (v0.15+, Unified Hybrid):** Claude Code는 subagent가 subagent를 spawn하는 것을 금지. 스킬이 메인 세션에서 직접 Direct + Indirect baseline(항상)을 spawn하고, 변경 패턴을 분석해 Deep-Focus 전문가(0~3개)를 추가 spawn. Comparator가 모든 set을 통합하면서 심각도 캘리브레이션 교차검증까지 수행. 단순 PR은 3 spawn, 복잡 PR은 최대 7 spawn.

**에이전트:**
- `my-harness:cr-direct-reviewer` (Opus) — Lens A baseline 통합 리뷰어 (5 카테고리)
- `my-harness:cr-indirect-reviewer` (Opus) — Lens B 4 축 리뷰어 (데코레이터-예외 경로·관용구 함정·future-risk·계약 일관성)
- `my-harness:cr-correctness` (Sonnet) — correctness deep-focus (migrations/signal/serializer 변경 시 자동 spawn)
- `my-harness:cr-reliability` (Sonnet) — reliability deep-focus (tasks/cron/workers 변경 시)
- `my-harness:cr-security` (Sonnet) — security deep-focus (permissions/auth/SSRF 변경 시)
- `my-harness:cr-performance` (Sonnet) — performance deep-focus (annotate/Subquery 다중·인덱스 변경 시)
- `my-harness:cr-maintainability` (Opus) — maintainability deep-focus (대규모 구조 변경 시)
- `my-harness:cr-report-comparator` (Opus) — 가변 입력 set(2~6) 통합 + 심각도 캘리브레이션 교차검증 + 최종 리포트 Write
- `my-harness:cr-fix` (Sonnet) — 파일별 finding 수정 실행 · /code-review-fix

**꼼꼼함 요구사항 (v0.15+, 엄격):** Critical/Major finding은 반드시 `reproduction`(재현 시나리오), `verification`(검증 방법), `reasoning`(severity-guide 기준 인용)을 포함. Comparator가 인용 없는 Critical은 자동 Major 강등.

**Lens:** 각 전문 에이전트는 `Lens: A`(baseline) 또는 `Lens: B`(indirect-risk)로 프롬프트에 지정되어 호출된다. A는 카테고리 전체 체크리스트 균등 적용, B는 데코레이터/예외 경로·관용구 함정·future-risk·계약 일관성 같은 간접 위험에 우선순위.

**변경 이력:**
| 날짜 | 변경 내용 | 대상 | 사유 |
|------|----------|------|------|
| 2026-04-10 | 초기 구성 | 전체 | 코드 품질/유지보수성 향상을 위한 리뷰 시스템 |
| 2026-04-10 | fix-agent + code-review-fix 추가 | agents, skills | 리뷰 결과 병렬 자동 수정 |
| 2026-04-17 | 에이전트를 `agents/` 플랫 구조로 이동, `cr-` prefix 적용 | agents | 플러그인 네이티브 `subagent_type` 등록 |
| 2026-04-20 | 3단계 중첩 → flat 10-expert 구조로 재설계, cr-orchestrator/cr-supervisor 삭제, Lens A/B 도입 | agents, skills | Claude Code가 subagent의 nested spawn 미지원 (공식 문서 확정) |
| 2026-04-20 | /code-review-slim 추가 (cr-direct-reviewer + cr-indirect-reviewer + comparator, 총 3 spawn) | agents, skills, commands | 5×2 구조와 3-agent 구조의 효과 비교 측정용 |
| 2026-04-20 | v0.15 unified: /code-review-slim을 /code-review로 통합. Direct + Indirect + Deep-Focus(자동 감지, 0~3) 하이브리드. 꼼꼼함 요구사항 강화(reproduction/verification/reasoning 필수), 심각도 캘리브레이션 교차검증 추가 | agents, skills, references, commands | 측정 결과 slim의 cross-category 강점 + flat의 깊이를 모두 살리는 방향으로 단일화 |
| 2026-04-21 | v0.16 /review-backlog 추가: 리뷰 followup/보류 항목 중앙 집중. dedup key(file+symbol+category+keywords)로 반복 지적 자동 병합, occurrence_count로 우선순위 시그널. /code-review 완료 시 major+ followup 자동 append, /code-review-walk [d]보류 시 수동 push. scripts/backlog_tool.py로 CRUD + stale-check + render-md | scripts, skills, commands | 이전 버전에서는 followup이 각 review 폴더에 흩어져 실질적 망각. 중앙 집중으로 기술 부채 가시화 및 트렌드 추적 |
| 2026-04-21 | v0.16.1 /code-review-walk의 모든 결정 지점을 AskUserQuestion 도구로 전환 (텍스트 `[w]/[p]/...` 파싱 제거). 5개 지점 모두 구조화 옵션 + description 제공. 수정 제안/커밋 메시지는 preview 필드로 diff·메시지를 monospace 박스에 side-by-side 렌더. | skills/code-review-walk | UX 일관성·명확성 향상. 유저가 각 옵션의 트레이드오프를 description에서 확인 후 선택 가능. Claude가 텍스트 한 글자 해석에 의존하지 않음 |
| 2026-04-21 | v0.17.0 AskUserQuestion 패턴을 4개 추가 스킬로 확장: /slack-review(미작업 진행 + 완료 처리 multiSelect), /code-review-fix(수정 계획 preview + 파일 선택 multiSelect), /slack-plan(완료 후 다음 단계 분기), /plan-execute(실행 계획 preview + 자가 수정 실패 시 분기). 모든 스킬 상단에 "사용자 입력 UI" 원칙 명시. | skills/slack-review, code-review-fix, slack-plan, plan-execute | 텍스트 기반 Y/n 프롬프트를 구조화 UI로 일관 전환. multiSelect/preview 활용으로 일괄 확인·선택 적용·시각 검토 가능 |

## MCP Tools
- `harness_project_info` - Get structured project metadata (git info, package info, file stats)

## Hooks
- **SessionStart**: Auto-loads project context (branch, recent commits)
- **PreToolUse**: Provides contextual hints before tool execution
