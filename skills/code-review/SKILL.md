---
name: code-review
description: "다중 에이전트 코드 리뷰 하네스. PR 번호, git diff, 변경 파일을 입력으로 받아 5개 전문 에이전트(Correctness, Reliability, Security, Performance, Maintainability)를 Lens A(baseline)와 Lens B(indirect-risk) 두 렌즈로 각각 독립 실행(= 총 10회)한 뒤, Report Comparator로 합의/고유/충돌을 분석해 심각도 기반 최종 리포트(Markdown + JSON)를 생성한다. 코드 리뷰, PR 리뷰, diff 리뷰, 변경사항 검토, 코드 품질 검사 요청 시 이 스킬을 사용할 것."
---

# Code Review Harness (Flat Architecture — v0.13+)

PR 또는 git diff를 입력으로 받아 다중 에이전트 합의 기반 코드 리뷰를 수행한다.

**아키텍처 결정 (2026-04-20):** Claude Code 공식 문서는 **"Subagents cannot spawn other subagents"**를 명시하고 있다 ([docs](https://code.claude.com/docs/en/sub-agents)). 따라서 이전의 3단계 중첩(`Main → Orchestrator → Supervisor → Experts`)은 기술적으로 불가능. 이 스킬은 **메인 세션(이 skill 실행 컨텍스트)에서 직접 11개 에이전트를 flat하게 spawn**한다:

```
/code-review (이 스킬, 메인 세션에서 실행)
  │
  ├─ Spawn × 5 [Lens A] ─ cr-correctness, cr-reliability, cr-security, cr-performance, cr-maintainability (병렬)
  ├─ Spawn × 5 [Lens B] ─ 동일 5종, 다른 렌즈 (병렬)
  │
  └─ Spawn cr-report-comparator ─ A-set/B-set 비교 + 최종 리포트 파일 작성
```

컨텍스트 오염을 최소화하기 위해 **모든 spawn은 `run_in_background: true`**이며, 각 에이전트는 **compact JSON 요약만 반환**한다. diff 전문은 skill이 각 에이전트 프롬프트에 직접 주입한다.

## 사용법

```
/code-review                          # git diff main...HEAD 자동 사용
/code-review #123                     # PR 번호
/code-review main..feature-branch     # diff 범위 지정
/code-review src/api/ src/models/     # 특정 디렉토리
```

## 실행 흐름

### Step 1: 입력 수집 및 diff 준비

사용자 인자를 파싱해 diff를 수집한다.

- 인자 없음 → `git diff main...HEAD` (최근 리뷰 이후 범위가 있으면 그것을 사용, 아래 Step 1.5 참조)
- PR 번호 (`#123`) → `gh pr diff 123`
- diff 범위 (`A..B`) → `git diff A..B`
- 파일/디렉토리 경로 → `git diff -- <paths>`

`.harness/code-review.json`이 존재하면 `ignore` 패턴을 diff 수집에 적용한다.

### Step 1.5: Summary 도출 및 폴더 초기화

리뷰 주제를 short slug로 추정:

1. PR 번호 → `gh pr view {n} --json title -q .title`을 slugify
2. 현재 브랜치명이 main/master가 아님 → 브랜치명 slugify (`feature/payment-integration` → `payment-integration`)
3. 변경 파일의 최빈 공통 디렉토리 → 디렉토리 slug
4. 커밋 메시지 첫 키워드 → Conventional Commit type 제거 후 첫 단어
5. fallback → `review`

사용자에게 summary 확인을 요청 (이미 확정된 PR/브랜치 패턴이면 skip 가능).

폴더 초기화:
```bash
TS=$(date "+%Y%m%d_%H%M%S")
SUM="<도출된 slug>"
BASE=".harness/reviews/${TS}-${SUM}"
mkdir -p "$BASE"
PREFIX="${BASE}/${TS}-${SUM}"
TRACE="${PREFIX}-trace.jsonl"

echo "{\"event\":\"skill_start\",\"time\":\"$(date -Iseconds)\",\"summary\":\"${SUM}\",\"scope\":\"<scope>\"}" > "$TRACE"
```

### Step 2: A-set Spawn (5 experts × Lens A, 병렬)

**한 번의 응답에서 5개 Agent 호출을 모두 포함하라.** 모두 `run_in_background: true`. 각 spawn 직전에 `agent_spawn` 이벤트를 trace에 기록한다 (Bash echo 5회).

```
Agent(
  subagent_type: "my-harness:cr-correctness",
  model: "sonnet",
  run_in_background: true,
  prompt: """
Lens: A

아래 diff를 정확성 관점에서 리뷰하라.

{diff 전문}

결과를 JSON findings 배열로 반환하라. 자연어 필드는 한글. 각 finding에:
id, title, severity, category('correctness'), file, lines, problem, why, impact, recommendation, scope
"""
)
# cr-reliability, cr-security, cr-performance, cr-maintainability 각각 동일 패턴
# cr-maintainability는 model: "opus" 사용
```

### Step 3: B-set Spawn (5 experts × Lens B, 병렬)

A-set spawn 직후 이어서(또는 동시에) B-set을 spawn한다. 동일 5개 에이전트지만 프롬프트 첫 줄이 `Lens: B`.

```
Agent(
  subagent_type: "my-harness:cr-correctness",
  ...
  prompt: """
Lens: B

아래 diff를 정확성 관점에서 리뷰하되, **계약·스키마 일관성** 중심으로 간접적·파생적 위험을 탐지하라.

{diff 전문}

결과 형식은 A와 동일.
"""
)
# 나머지 4개도 동일. 각 에이전트가 자기 카테고리의 Lens B 지침을 따른다.
```

**총 10개 Agent spawn을 한 번에 또는 두 배치(A 먼저, B 이어서)로 실행**한다. 레이트 리밋이 우려되면 배치 분리, 아니면 10개 동시. 각 spawn마다 trace에 `agent_spawn` 기록.

### Step 4: 결과 수집 + trace 기록

10개 에이전트가 모두 완료될 때까지 대기. 각 완료 시 `agent_result` 이벤트를 trace에 기록:

```bash
echo "{\"event\":\"agent_result\",\"subagent_type\":\"cr-correctness\",\"lens\":\"A\",\"finding_count\":N,\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

누락된 카테고리(예: A-set에서 cr-security 에이전트가 실패)가 있으면 해당 에이전트만 즉시 재-spawn.

### Step 5: Comparator Spawn

5개 카테고리 × 2개 렌즈 = 총 10개의 findings 배열을 Comparator에게 전달:

```
Agent(
  subagent_type: "my-harness:cr-report-comparator",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 A-set과 B-set을 비교 분석하라.

[출력 언어] 한글.

A-set (Lens=A, baseline):
- cr-correctness: {findings JSON}
- cr-reliability: {...}
- cr-security: {...}
- cr-performance: {...}
- cr-maintainability: {...}

B-set (Lens=B, indirect-risk):
- cr-correctness: {...}
- cr-reliability: {...}
- cr-security: {...}
- cr-performance: {...}
- cr-maintainability: {...}

[작업]
1. 합의/고유/충돌 분석
2. 최종 리포트를 아래 두 파일에 직접 작성:
   - Markdown: {review_md 절대 경로}
   - JSON:     {review_json 절대 경로}
3. 완료 후 다음 JSON만 반환:
   { "total": N, "critical": N, "major": N, "minor": N, "nit": N, "consensus_rate": 0.0-1.0, "unique_a_rate": ..., "unique_b_rate": ... }

출력 형식 상세: skills/code-review/references/report-format.md 참조
"""
)
```

Comparator 호출 전후 trace 기록 (`comparator_start` / `comparator_end`).

### Step 6: Trace 검증

```bash
# 카테고리별 spawn/result 수 확인
grep '"event":"agent_spawn"' "$TRACE" | wc -l   # 기대값: 10
grep '"event":"agent_result"' "$TRACE" | wc -l  # 기대값: 10
```

카테고리 누락, spawn/result 수 불일치 등 이상 발견 시 `validation_warnings`에 기록.

### Step 7: 최종 요약 출력

```bash
echo "{\"event\":\"skill_end\",\"time\":\"$(date -Iseconds)\",\"findings\":N,...}" >> "$TRACE"
```

사용자에게 보여줄 요약:

```markdown
## Code Review 완료

- 리포트: `.harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-review.md`
- 발견: Critical 1, Major 4, Minor 5, Nit 2 (총 12건)
- A/B 합의율: 67%
- Execution Trace: 10 spawn / 10 return ✅

### 다음 단계
- 리포트 검토: 위 경로 열기
- 병렬 자동 수정: `/code-review-fix`
- 대화형 점검: `/code-review-walk`
```

`validation_warnings`가 있으면 상단에 경고 배너.

## 설정

### ignore 정책

`.harness/code-review.json`:

```json
{
  "ignore": [
    "**/*.test.ts",
    "**/*.spec.ts",
    "**/migrations/**",
    "package-lock.json",
    "yarn.lock"
  ],
  "severity_threshold": "minor",
  "max_nits": 5
}
```

스킬이 이 파일을 Step 1에서 읽어 diff 수집 및 finding 필터링에 적용한다.

## 아키텍처 — 왜 평탄화인가

**이전 (v0.12.x 이하):** `Main → cr-orchestrator → cr-supervisor(A/B) → 5 experts` 3단계 중첩.
**문제:** Claude Code는 subagent가 subagent를 spawn하는 것을 금지. 따라서 orchestrator와 supervisor는 자식 에이전트를 생성할 수 없어 in-context fallback으로 회귀 (`execution_trace_ok: false`, consensus_rate 저하).

**현재 (v0.13+):** `Main(skill) → 10 experts + 1 comparator` 2단계 flat.
**이점:**
- 모든 에이전트가 **진짜 독립 프로세스** — Lens A와 Lens B의 findings가 **실제로 분리 생성**됨
- trace에 `agent_spawn` 이벤트 10건이 실제로 기록됨 (in-context fallback 아님)
- consensus_rate가 의미를 가짐 (같은 context에서 뽑아낸 두 패스가 아님)

**트레이드오프:**
- 스킬이 메인 세션이라 diff가 주 컨텍스트를 잠시 통과 (10개 spawn 직후 사라짐)
- Orchestrator/Supervisor 에이전트는 deprecated (archive 처리, 추후 삭제)

## 참조 문서

- `references/severity-guide.md` — 심각도 판정 기준
- `references/maintainability-rules.md` — 유지보수성 전담 판정 규칙
- `references/report-format.md` — 출력 형식 상세
- `agents/cr-{correctness,reliability,security,performance,maintainability}.md` — 5 전문 에이전트 프롬프트
- `agents/cr-report-comparator.md` — 비교 분석 + 최종 리포트 작성 에이전트
