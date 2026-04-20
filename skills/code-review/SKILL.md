---
name: code-review
description: "다중 에이전트 코드 리뷰 하네스. PR 번호, git diff, 변경 파일을 입력으로 받아 2개의 독립 리뷰 감독 에이전트가 5개 전문 서브에이전트(Correctness, Reliability, Security, Performance, Maintainability)를 운용하여 코드를 리뷰하고, 비교 분석을 거쳐 심각도 기반 최종 리포트(Markdown + JSON)를 생성한다. 코드 리뷰, PR 리뷰, diff 리뷰, 변경사항 검토, 코드 품질 검사 요청 시 이 스킬을 사용할 것."
---

# Code Review Harness

PR 또는 git diff를 입력으로 받아 다중 에이전트 합의 기반 코드 리뷰를 수행한다.

**구조:** 이 스킬은 얇은 진입점이다. 실제 orchestration은 `my-harness:cr-orchestrator` 에이전트가 **백그라운드 컨텍스트에서 독립적으로** 수행한다. 메인 세션은 orchestrator에게 입력 전달 + 최종 결과 출력만 담당하므로 컨텍스트 오염을 피한다.

## 사용법

```
/code-review                          # git diff main...HEAD 자동 사용
/code-review #123                     # PR 번호
/code-review main..feature-branch     # diff 범위 지정
/code-review src/api/ src/models/     # 특정 디렉토리
```

## 아키텍처

```
Main Session (thin wrapper)
  │
  └─ ⭐ Fork → Agent(cr-orchestrator, run_in_background)
               │  — 메인 타임라인에서 분기된 격리 컨텍스트
               │
               ├─ 입력 수집 · summary 도출 · 아티팩트 폴더 초기화
               ├─ Spawn → Agent(cr-supervisor-a, run_in_background)
               │           └─ Spawn → Agent(cr-correctness|reliability|security|performance|maintainability) × 5
               ├─ Spawn → Agent(cr-supervisor-b, run_in_background)
               │           └─ Spawn → (동일 5개)
               ├─ Spawn → Agent(cr-report-comparator)
               └─ 최종 리포트 작성 + trace 검증
  ← 메인 세션에는 요약과 파일 경로만 돌아옴
```

**Fork vs Spawn (개념 구분, 기술적 메커니즘은 동일 `Agent(run_in_background)`):**
- **Fork** (1회): Main → Orchestrator — 메인 대화 타임라인에서 분기되는 격리 경계
- **Spawn** (내부): Orchestrator 내부 워커 생성 — 병렬 실행을 위한 위임

격리 Fork는 Main↔Orchestrator 한 번뿐. 내부 Spawn은 orchestrator의 병렬 구현 세부사항이며 메인 컨텍스트와 무관하다.

## 실행 흐름 (skill 관점)

### Step 1: 최소 입력 검증

사용자 인자를 파싱하여 orchestrator에게 전달할 원시 입력만 준비한다. 실제 diff 수집은 orchestrator가 수행.

- 인자 없음 → `mode: "auto"` (orchestrator가 이전 리뷰 이후 범위 탐지)
- PR 번호 → `mode: "pr", pr: {number}`
- diff 범위 (`main..feature`) → `mode: "range", range: "..."`
- 파일/디렉토리 경로 → `mode: "paths", paths: [...]`

### Step 2: Orchestrator Fork

메인 세션에서 `my-harness:cr-orchestrator`를 **Fork**한다 — 메인 타임라인에서 분기된 격리 컨텍스트로 실행. 기술적으로는 `Agent(run_in_background: true)` 호출이지만, 용어상 **Fork**(격리 경계를 만드는 경우)로 부른다. 이후 orchestrator 내부에서 일어나는 워커 생성은 **Spawn**으로 부른다.

```
Agent(
  name: "cr-orchestrator",
  subagent_type: "my-harness:cr-orchestrator",
  model: "opus",
  run_in_background: true,
  prompt: """
  당신은 Code Review Orchestrator이다. agents/cr-orchestrator.md의 지침에 따라
  다음 단계를 모두 수행하라:

  1. 입력 수집 + summary 도출 + 사용자 확인
  2. 아티팩트 폴더 `.harness/reviews/{TS}-{SUM}/` 초기화, trace.jsonl 생성
  3. Supervisor A/B를 병렬 spawn
  4. Report Comparator spawn
  5. 최종 Markdown + JSON 리포트 작성 (폴더 안)
  6. Agent Execution Trace 검증 결과를 metadata에 포함

  완료 후 다음 JSON을 반환하라:
  {
    "review_dir": ".harness/reviews/{TS}-{SUM}/",
    "review_md": ".harness/reviews/{TS}-{SUM}/{TS}-{SUM}-review.md",
    "review_json": ".harness/reviews/{TS}-{SUM}/{TS}-{SUM}-review.json",
    "summary": { "total": N, "critical": N, "major": N, "minor": N, "nit": N },
    "consensus_rate": 0.0-1.0,
    "validation_warnings": [...]
  }

  ## 원시 입력
  {mode + 관련 인자}
  """
)
```

메인 세션은 이후 orchestrator 완료만 기다린다. **diff 내용, supervisor 결과, comparator 결과 등 중간 산출물을 보지 않음** → 컨텍스트 오염 없음.

### Step 3: 진행 상황 모니터링 (선택)

orchestrator 실행 중에 trace 파일을 짧게 확인하여 사용자에게 진행 상황을 보여줄 수 있다:

```bash
# orchestrator 시작 후 주기적으로 (또는 사용자 요청 시)
tail -n 5 .harness/reviews/{최근 폴더}/*-trace.jsonl
```

자동 모니터링이 번거로우면 Step 2에서 바로 Step 4로 진행.

### Step 4: 결과 보고

orchestrator가 반환한 JSON을 사용자에게 요약해 보여준다:

```markdown
## Code Review 완료

- 리포트: `.harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-review.md`
- 발견: Critical 1, Major 4, Minor 5, Nit 2 (총 12건)
- Supervisor 합의율: 67%

### 다음 단계
- 리포트 검토: `cat {path}` 또는 에디터에서 열기
- 병렬 자동 수정: `/code-review-fix`
- 하나씩 점검: `/code-review-walk`
```

validation_warnings가 있으면 상단에 경고 표시.

## 설정

### ignore 정책

특정 파일/패턴을 리뷰에서 제외하려면 `.harness/code-review.json`을 생성한다:

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

- `ignore`: 리뷰 제외 파일 패턴
- `severity_threshold`: 이 레벨 미만은 보고서에서 제외 (기본: 모두 포함)
- `max_nits`: Nit 레벨 최대 개수 (기본: 제한 없음)

Orchestrator가 이 파일을 읽어 적용한다.

## 에이전트 확장

새 전문 에이전트를 추가하려면:

1. `agents/cr-{name}.md` 파일 생성 (기존 에이전트 형식 참조, `name:` 필드를 `cr-{name}`으로 설정)
2. `agents/cr-supervisor.md`의 서브에이전트 목록에 추가
3. 필요 시 `references/severity-guide.md`에 해당 카테고리 추가

## 참조 문서

- `agents/cr-orchestrator.md` — 실제 orchestration 로직 (이 스킬이 fork 하는 에이전트)
- `references/severity-guide.md` — 심각도 판정 기준
- `references/maintainability-rules.md` — 유지보수성 전담 판정 규칙
- `references/report-format.md` — 출력 형식 상세
