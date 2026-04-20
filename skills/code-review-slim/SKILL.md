---
name: code-review-slim
description: "슬림 구조 코드 리뷰 하네스 (Direct + Indirect + Comparator 3-agent). /code-review(5×2=10 expert)와 교차 비교용 대안. PR 번호/git diff/변경 파일을 입력으로 2개의 통합 리뷰어를 **독립 병렬 spawn**하여 A-set(표면 위험)과 B-set(간접 위험)을 얻고, Comparator가 합의/고유/충돌을 분석해 최종 리포트를 생성한다."
---

# Code Review Slim (3-agent)

같은 PR에 대해 `/code-review`(v0.13+ flat 5×2)와 **결과를 직접 비교**하기 위한 슬림 변형. Direct Reviewer와 Indirect Reviewer가 각각 5개 카테고리 전체/4개 축 전체를 한 컨텍스트에서 평가한다.

**구조:**
```
/code-review-slim (이 스킬, 메인 세션)
  │
  ├─ Spawn × 1 ─ cr-direct-reviewer   (Lens A — 5 카테고리 체크리스트, Opus)
  ├─ Spawn × 1 ─ cr-indirect-reviewer (Lens B — 4 축, Opus)
  │               (둘은 병렬, run_in_background)
  │
  └─ Spawn × 1 ─ cr-report-comparator (A-set/B-set 통합 + 최종 리포트 파일 작성)
```

총 3 spawn. `/code-review`(11 spawn) 대비 비용 1/3~1/4 수준, 속도는 유사(Direct/Indirect가 Opus이므로 각 단일 호출이 길어짐).

## 사용법

```
/code-review-slim                          # git diff main...HEAD 자동 사용
/code-review-slim #123                     # PR 번호
/code-review-slim main..feature-branch     # diff 범위 지정
/code-review-slim src/api/ src/models/     # 특정 디렉토리
```

## 실행 흐름

### Step 1: 입력 수집 및 diff 준비

`/code-review`와 동일. 사용자 인자를 파싱해 diff 수집.

- 인자 없음 → `git diff main...HEAD`
- PR 번호 (`#123`) → `gh pr diff 123`
- diff 범위 (`A..B`) → `git diff A..B`
- 파일/디렉토리 경로 → `git diff -- <paths>`

`.harness/code-review.json`의 `ignore` 패턴 적용.

### Step 1.5: Summary 도출 및 폴더 초기화

`/code-review`와 동일한 slug 도출 로직. 단, **폴더명에 `-slim` 접미사**를 붙여 `/code-review` 결과와 공존 가능하게 한다:

```bash
TS=$(date "+%Y%m%d_%H%M%S")
SUM="<도출된 slug>"
BASE=".harness/reviews/${TS}-${SUM}-slim"
mkdir -p "$BASE"
PREFIX="${BASE}/${TS}-${SUM}-slim"
TRACE="${PREFIX}-trace.jsonl"

echo "{\"event\":\"skill_start\",\"variant\":\"slim\",\"time\":\"$(date -Iseconds)\",\"summary\":\"${SUM}\",\"scope\":\"<scope>\"}" > "$TRACE"
```

이렇게 하면 `ls .harness/reviews/`에서 `20260420_143022-og-preview/`(5×2)와 `20260420_143022-og-preview-slim/`(3-agent)가 나란히 보인다.

### Step 2: Direct + Indirect Reviewer 병렬 Spawn

**한 응답에서 두 Agent 호출을 모두 포함하라.** 둘 다 `run_in_background: true`. 각 spawn 직전에 `agent_spawn` trace 기록.

```bash
echo "{\"event\":\"agent_spawn\",\"subagent_type\":\"cr-direct-reviewer\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
echo "{\"event\":\"agent_spawn\",\"subagent_type\":\"cr-indirect-reviewer\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

```
Agent(
  subagent_type: "my-harness:cr-direct-reviewer",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 diff를 5개 카테고리(correctness, reliability, security, performance, maintainability) 전체 체크리스트로 리뷰하라.

[출력 언어] 자연어 필드는 한글.

{diff 전문}

결과를 JSON findings 배열로 반환하라. 각 finding에:
id(DR-{NNN}), title, severity, category, file, lines, problem, why, impact, recommendation, scope
"""
)

Agent(
  subagent_type: "my-harness:cr-indirect-reviewer",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 diff를 4개 축(데코레이터-예외 경로 상호작용, 언어 관용구 함정, future-risk, 계약·스키마 일관성)으로 리뷰하라. cr-direct-reviewer가 잡을 만한 표면 이슈는 의도적으로 패스하고 간접적·파생적 위험에 집중.

[출력 언어] 자연어 필드는 한글.

{diff 전문}

결과를 JSON findings 배열로 반환하라. 각 finding에:
id(IR-{NNN}), title, severity, category, axis(optional), file, lines, problem, why, impact, recommendation, scope
"""
)
```

### Step 3: 결과 수집 + trace 기록

두 에이전트 완료 대기. 각 완료 시 `agent_result` 기록:

```bash
echo "{\"event\":\"agent_result\",\"subagent_type\":\"cr-direct-reviewer\",\"finding_count\":N,\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
echo "{\"event\":\"agent_result\",\"subagent_type\":\"cr-indirect-reviewer\",\"finding_count\":N,\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

실패한 에이전트가 있으면 재-spawn (1회).

### Step 4: Comparator Spawn

Direct와 Indirect의 findings를 각각 A-set / B-set으로 전달:

```bash
echo "{\"event\":\"comparator_start\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

```
Agent(
  subagent_type: "my-harness:cr-report-comparator",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 A-set과 B-set을 비교 분석하라.

[출력 언어] 한글.
[변형] slim (3-agent). 일반 code-review와 비교 가능하도록 review.json의 metadata에 "variant": "slim" 포함.

A-set (Lens=A, Direct Reviewer):
{direct findings JSON}

B-set (Lens=B, Indirect Reviewer):
{indirect findings JSON}

[작업]
1. 합의 매칭 휴리스틱(파일+라인±5+category+키워드)으로 합의/고유/충돌 분류
2. 최종 리포트를 아래 두 파일에 직접 작성:
   - Markdown: {review_md 절대 경로}
   - JSON:     {review_json 절대 경로}
3. 완료 후 다음 JSON만 반환:
   { "total": N, "critical": N, "major": N, "minor": N, "nit": N, "consensus_rate": 0.0-1.0, "unique_a": N, "unique_b": N, "conflicts": N }

출력 형식 상세: skills/code-review/references/report-format.md 참조 (단, review.json.metadata.variant = "slim" 추가)
"""
)
```

완료 후:
```bash
echo "{\"event\":\"comparator_end\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
echo "{\"event\":\"skill_end\",\"variant\":\"slim\",\"time\":\"$(date -Iseconds)\",\"findings\":N}" >> "$TRACE"
```

### Step 5: Trace 검증

```bash
grep -c '"event":"agent_spawn"' "$TRACE"   # 기대값: 2 (Direct + Indirect) + 1 (Comparator) = 3
grep '"event":"spawn_unavailable"' "$TRACE" && echo "WARN: fallback" || echo "OK"
```

### Step 6: 최종 요약 출력

```markdown
## Code Review (Slim) 완료

- 변형: slim (3-agent Direct + Indirect + Comparator)
- 리포트: `.harness/reviews/{TS}-{SUM}-slim/{TS}-{SUM}-slim-review.md`
- 발견: Critical N, Major N, Minor N, Nit N (총 N건)
- A/B 합의율: N%
- Execution Trace: 3 spawn / 3 return ✅

### 비교 권장

같은 PR을 `/code-review`로도 실행했다면 다음을 비교:
- Total findings 수
- B-unique 발견 수 (slim의 indirect가 놓친 게 있는지)
- cross-category 발견 (slim의 integrated 리뷰어 우위 확인)
- 소요 시간 및 대략 토큰 비용

### 다음 단계
- 리포트 검토: 위 경로 열기
- 병렬 자동 수정: `/code-review-fix`
- 대화형 점검: `/code-review-walk`
```

## /code-review와의 차이 요약

| 항목 | `/code-review` (v0.13+) | `/code-review-slim` |
|------|------------------------|---------------------|
| Spawn 수 | 11 (5 experts × 2 lens + comparator) | 3 (direct + indirect + comparator) |
| 모델 | Sonnet × 8 + Opus × 3 | Opus × 3 |
| 카테고리 분리 | 5 전문 에이전트 | 1 통합 리뷰어(×2) |
| Cross-category 이슈 | 카테고리 경계에 따라 누락 가능 | 전체 맥락 한 컨텍스트라 잡기 쉬움 |
| 폴더 접미사 | 없음 | `-slim` |
| 비용 | 높음 | 약 1/3 |
| review.json metadata | `"variant": "flat"` | `"variant": "slim"` |

## 결과물 공유

`/code-review-walk`와 `/code-review-fix`는 폴더 접미사를 식별해 `-slim` 폴더도 정상 처리한다 (review.json 경로만 맞으면 됨). 추가 변경 불필요.

## 측정 연동

`.harness/code-review-measurement.md`에 각 slim 실행 결과를 같은 테이블에 **행 하나로 추가**해 `/code-review`(5×2)와 비교 가능. "비고" 컬럼에 `variant: slim` 표기 권장.

## 참조 문서

- `agents/cr-direct-reviewer.md` — 5 카테고리 통합 리뷰어 (Lens A)
- `agents/cr-indirect-reviewer.md` — 4 축 통합 리뷰어 (Lens B)
- `agents/cr-report-comparator.md` — 비교 분석 + 최종 리포트 작성
- `skills/code-review/references/report-format.md` — 출력 형식
