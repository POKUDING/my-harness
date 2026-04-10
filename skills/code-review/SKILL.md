---
name: code-review
description: "다중 에이전트 코드 리뷰 하네스. PR 번호, git diff, 변경 파일을 입력으로 받아 2개의 독립 리뷰 감독 에이전트가 5개 전문 서브에이전트(Correctness, Reliability, Security, Performance, Maintainability)를 운용하여 코드를 리뷰하고, 비교 분석을 거쳐 심각도 기반 최종 리포트(Markdown + JSON)를 생성한다. 코드 리뷰, PR 리뷰, diff 리뷰, 변경사항 검토, 코드 품질 검사 요청 시 이 스킬을 사용할 것."
---

# Code Review Harness

PR 또는 git diff를 입력으로 받아 다중 에이전트 합의 기반 코드 리뷰를 수행한다.

## 사용법

```
/code-review                          # git diff main...HEAD 자동 사용
/code-review #123                     # PR 번호
/code-review main..feature-branch     # diff 범위 지정
/code-review src/api/ src/models/     # 특정 디렉토리
```

## 아키텍처

```
Main Session
  └─ fork → Main Orchestrator (code-review-orchestrator)
               ├─ Review Supervisor A (review-supervisor)
               │    ├─ Correctness Agent (sonnet)
               │    ├─ Reliability Agent (sonnet)
               │    ├─ Security Agent (sonnet)
               │    ├─ Performance Agent (sonnet)
               │    └─ Maintainability Agent (opus)
               ├─ Review Supervisor B (review-supervisor)
               │    ├─ Correctness Agent (sonnet)
               │    ├─ Reliability Agent (sonnet)
               │    ├─ Security Agent (sonnet)
               │    ├─ Performance Agent (sonnet)
               │    └─ Maintainability Agent (opus)
               └─ Report Comparator (opus)
                    └─ 최종 보고서 (Markdown + JSON)
```

## 실행 흐름

### Step 0: 입력 수집

입력 방식을 자동 감지한다:

1. **PR 번호** (`#123` 또는 숫자) → `gh pr diff {number}`
2. **diff 범위** (`main..branch`) → `git diff {range}`
3. **파일/디렉토리** 경로 → 해당 파일들의 `git diff`
4. **인자 없음** → `git diff main...HEAD`

수집할 컨텍스트:
- diff 내용 전문
- 변경 파일 목록 및 변경 통계 (`git diff --stat`)
- 레포의 기술 스택 (package.json, tsconfig.json 등에서 추론)
- PR 설명 (PR 번호가 주어진 경우 `gh pr view`)

### Step 1: 리뷰 계획 수립

변경 파일을 논리 단위로 묶어 리뷰 계획을 수립한다:
- 모듈/디렉토리 기준 그룹핑
- 변경 규모 파악 (파일 수, 추가/삭제 라인 수)
- 기술 스택별 리뷰 포인트 정리

### Step 2: 리뷰 감독 에이전트 A, B 병렬 실행

두 감독 에이전트를 **동시에** 생성한다. 각각 독립적으로 5개 전문 서브에이전트를 운용한다.

```
Agent(
  name: "supervisor-a",
  subagent_type: "review-supervisor",
  model: "opus",
  run_in_background: true,
  prompt: """
  당신은 Review Supervisor A입니다.
  agents/review-supervisor.md의 지침을 따라 코드 리뷰를 수행하세요.

  ## 입력
  - Diff: {diff 전문}
  - 파일 목록: {변경 파일 목록}
  - 기술 스택: {추론된 스택}
  - 리뷰 계획: {Step 1 결과}

  ## 서브에이전트 생성
  다음 5개 에이전트를 모두 병렬 생성하세요:
  1. Agent(subagent_type: "correctness-agent", model: "sonnet")
  2. Agent(subagent_type: "reliability-agent", model: "sonnet")
  3. Agent(subagent_type: "security-agent", model: "sonnet")
  4. Agent(subagent_type: "performance-agent", model: "sonnet")
  5. Agent(subagent_type: "maintainability-agent", model: "opus")

  각 에이전트에게 diff 전문과 파일 목록을 전달하세요.
  결과를 수집하여 중복 제거, 우선순위화 후 JSON으로 반환하세요.

  severity 기준: skills/code-review/references/severity-guide.md 참조
  유지보수성 규칙: skills/code-review/references/maintainability-rules.md 참조
  """
)
```

Supervisor B도 동일하게 생성한다 (독립적 관점을 위해 프롬프트 뉘앙스를 약간 다르게 한다).

Supervisor B 프롬프트 차이점:
- "놓치기 쉬운 미묘한 문제에 집중하세요"
- "A와 다른 관점에서 검토하되, 기준은 동일하게 유지하세요"

### Step 3: 비교 분석

두 감독 에이전트의 결과를 Report Comparator에 위임한다:

```
Agent(
  subagent_type: "report-comparator",
  model: "opus",
  prompt: """
  두 감독 에이전트의 독립 리뷰 결과를 비교 분석하세요.

  ## Supervisor A 결과
  {supervisor_a_result}

  ## Supervisor B 결과
  {supervisor_b_result}

  합의 사항, 고유 발견, 충돌 의견을 분류하고
  최종 병합 findings 목록을 생성하세요.
  """
)
```

### Step 4: 최종 보고서 생성

비교 분석 결과와 자체 맥락을 종합하여 최종 보고서를 생성한다:

1. findings를 severity 순으로 정렬 (Critical → Major → Minor → Nit)
2. 각 finding에 confidence 레벨 부여 (high/medium/review)
3. **Markdown 리포트** 생성 — `_reviews/{date}-review.md`
4. **JSON 리포트** 생성 — `_reviews/{date}-review.json`

출력 형식 상세: `references/report-format.md` 참조

### Step 5: 결과 보고

사용자에게 요약을 보여준다:
- severity별 건수
- Critical/Major findings 요약
- 전체 리포트 파일 위치
- consensus rate (두 감독 에이전트의 합의율)

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

## 에이전트 확장

새 전문 에이전트를 추가하려면:

1. `agents/{name}-agent.md` 파일 생성 (기존 에이전트 형식 참조)
2. `agents/review-supervisor.md`의 서브에이전트 목록에 추가
3. 필요 시 `references/severity-guide.md`에 해당 카테고리 추가

## 참조 문서

- `references/severity-guide.md` — 심각도 판정 기준
- `references/maintainability-rules.md` — 유지보수성 전담 판정 규칙
- `references/report-format.md` — 출력 형식 상세
