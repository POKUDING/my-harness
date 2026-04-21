---
name: code-review-fix
description: "코드 리뷰 결과를 기반으로 fix_now 항목을 파일별로 병렬 수정하는 스킬. /code-review로 생성된 리포트(JSON)를 입력으로 받아 여러 cr-fix 에이전트를 동시에 생성하여 수정을 수행하고, 변경 요약을 출력한다. 코드 수정, 리뷰 반영, finding 고치기, 자동 수정 요청 시 이 스킬을 사용할 것."
---

# Code Review Fix — 리뷰 결과 병렬 수정

`/code-review`로 생성된 리뷰 결과의 `fix_now` 항목을 파일별로 병렬 수정한다.

## 사용자 입력 UI (v0.17+)

수정 계획 승인은 **`AskUserQuestion`**. `preview`로 수정 계획 표(파일×findings×severity)를 monospace 박스에 렌더하여 한눈에 확인. `multiSelect`로 특정 파일만 선택해 수정하는 부분 적용도 지원.

## 사용법

```
/code-review-fix                                                   # 가장 최근 리뷰 결과 사용
/code-review-fix .harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-review.json   # 특정 리뷰 결과 지정
```

## 실행 흐름

### Step 0: 리뷰 결과 로드

1. **인자 있음** → 지정된 JSON 파일을 Read
2. **인자 없음** → `.harness/reviews/*/` 하위 폴더 중 가장 최근의 `*-review.json` 파일을 자동 탐지
   ```bash
   ls -t .harness/reviews/*/*-review.json | head -1
   ```
3. JSON이 없으면 안내 후 중단:
   ```
   리뷰 결과를 찾을 수 없습니다.
   먼저 /code-review를 실행하세요.
   ```

리뷰 파일 경로에서 **부모 폴더**를 추출하여 이후 산출물 저장에 재사용한다:
```
review_dir = dirname(review_json_path)     # .harness/reviews/{TS}-{SUM}/
prefix     = basename(review_json_path, "-review.json")   # {TS}-{SUM}
```

### Step 1: fix_now 항목 필터링 및 그룹핑

JSON의 `findings` 배열에서:
1. `scope: "fix_now"` 항목만 필터링
2. `severity: "nit"` 제외
3. 파일 경로(`file`)별로 그룹핑

fix_now 항목이 없으면:
```
수정할 항목이 없습니다. 모든 finding이 followup 범위입니다.
```

사용자에게 수정 계획을 보여주고 **AskUserQuestion**으로 승인 받는다:

```
AskUserQuestion({
  questions: [{
    question: "위 수정 계획대로 진행할까요?",
    header: "Apply plan",
    options: [
      { label: "전체 적용 (Recommended)",
        description: "계획된 모든 파일에 대해 cr-fix 에이전트 병렬 spawn",
        preview: "```\n## 수정 계획\n\n| 파일 | findings | severity 분포 |\n|------|----------|---------------|\n| src/api/users.ts | CR-001, CR-004 | 1 Critical, 1 Major |\n| src/services/order.ts | CR-002, CR-003 | 2 Major |\n| src/utils/validate.ts | CR-007 | 1 Minor |\n\n총 5건 · 3 파일\n```" },
      { label: "파일 선택 적용",
        description: "어느 파일만 수정할지 개별 선택 (이어지는 multiSelect 질문에서 지정)" },
      { label: "중단",
        description: "수정 실행하지 않고 종료. 리뷰 리포트는 그대로 유지." }
    ],
    multiSelect: false
  }]
})
```

"파일 선택 적용" 선택 시 이어서 **multiSelect** 질문 추가:

```
AskUserQuestion({
  questions: [{
    question: "수정할 파일을 선택하세요 (multiSelect)",
    header: "Pick files",
    multiSelect: true,
    options: [
      { label: "src/api/users.ts (2 findings · 1 Critical)",
        description: "CR-001, CR-004" },
      { label: "src/services/order.ts (2 findings · 2 Major)",
        description: "CR-002, CR-003" },
      { label: "src/utils/validate.ts (1 finding · Minor)",
        description: "CR-007" }
      // 파일이 4개 초과면 severity 기준 Top 3 + "나머지 일괄"로 요약
    ]
  }]
})
```

### Step 2: 파일별 cr-fix 에이전트 병렬 생성

**각 파일 그룹마다 1개의 cr-fix 에이전트를 생성한다.** 모든 cr-fix 에이전트를 한 번에 병렬로 생성한다.

```
# 파일 수만큼 Agent 호출을 한 번의 응답에서 동시 생성

Agent(
  description: "Fix src/api/users.ts",
  subagent_type: "my-harness:cr-fix",
  model: "sonnet",
  run_in_background: true,
  prompt: """
  다음 파일의 코드 리뷰 finding을 수정하라.

  ## 대상 파일
  src/api/users.ts

  ## 수정할 Findings
  {해당 파일의 findings JSON 배열}

  수정 후 변경 내역을 JSON으로 반환하라.
  """
)

Agent(
  description: "Fix src/services/order.ts",
  subagent_type: "my-harness:cr-fix",
  model: "sonnet",
  run_in_background: true,
  prompt: """
  ...(동일 구조)...
  """
)

# ... 파일 수만큼 반복
```

### Step 3: 진행률 보고 및 결과 수집

각 cr-fix 에이전트가 완료될 때마다 진행 상황을 보고한다:

```
[진행] src/api/users.ts 수정 완료 (1/3 파일)
  - 수정: 2건 (CR-001, CR-004)
  - 스킵: 0건
  - 실패: 0건
```

모든 cr-fix 에이전트 완료 후 결과를 수집한다.

### Step 4: 결과 검증

수정된 파일들에 대해:
1. 파일이 정상적으로 수정되었는지 확인 (Read로 재확인)
2. 구문 오류 발생 여부 확인 (가능하면 `npx tsc --noEmit` 또는 해당 언어 lint 실행)
3. 검증 실패 시 사용자에게 경고

### Step 5: 결과 저장 및 요약 보고

fix 결과를 파일로 저장한다. Step 0에서 추출한 `review_dir`와 `prefix`를 재사용하여 **원본 리뷰와 같은 폴더**에 저장한다:

- `{review_dir}/{prefix}-fix-result.md` — 사람이 읽는 결과 요약
- `{review_dir}/{prefix}-fix-result.json` — 기계가 읽는 결과 (CI/CD 연동용)

예: `.harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-fix-result.md`

JSON 형식:
```json
{
  "metadata": {
    "date": "YYYY-MM-DDTHH:mm:ss",
    "source_review": "YYYYMMDD_HHmmss-review.json",
    "total_fix_now": 5,
    "fixed": 4,
    "skipped": 3,
    "failed": 1
  },
  "results": [
    {"id": "CR-001", "severity": "critical", "file": "src/api/users.ts", "status": "fixed"},
    {"id": "CR-003", "severity": "major",    "file": "src/services/order.ts", "status": "failed", "reason": "아키텍처 변경 필요"},
    {"id": "CR-005", "severity": "major",    "file": "src/models/user.ts", "status": "skipped", "scope": "followup"}
  ]
}
```

사용자에게 요약을 보여준다:

```markdown
## Code Review Fix 완료

### 수정 결과
| Finding | Severity | File | 결과 |
|---------|----------|------|------|
| CR-001 | Critical | src/api/users.ts | 수정 완료 |
| CR-002 | Major | src/services/order.ts | 수정 완료 |
| CR-003 | Major | src/services/order.ts | 실패 — 아키텍처 변경 필요 |
| CR-004 | Major | src/api/users.ts | 수정 완료 |
| CR-007 | Minor | src/utils/validate.ts | 수정 완료 |

### 요약
- 수정 완료: 4건
- 스킵 (followup): 3건
- 실패: 1건

### followup 항목 (이번에 수정하지 않음)
| Finding | Severity | File | 사유 |
|---------|----------|------|------|
| CR-005 | Major | src/models/user.ts | 기존 구조 문제, 별도 리팩토링 필요 |
| CR-006 | Minor | src/config/db.ts | 이 PR 범위 밖 |
| CR-008 | Minor | src/utils/format.ts | 변경 이득 작음 |

### 실패 항목 상세
- **CR-003** (src/services/order.ts): 산탄총 수술 구조 — 자동 수정 불가, 수동 리팩토링 필요

### 저장된 파일
- `.harness/reviews/YYYYMMDD_HHmmss-fix-result.md`
- `.harness/reviews/YYYYMMDD_HHmmss-fix-result.json`

### 다음 단계
- `git diff`로 변경 내용을 확인하세요
- 문제가 없으면 커밋하세요
- 실패 항목은 별도 이슈로 등록을 권장합니다
```

## 안전 장치

1. **수정 전 사용자 확인 필수** — 수정 계획을 보여주고 승인을 받은 후 진행
2. **fix_now만 수정** — followup은 절대 건드리지 않음
3. **Nit 제외** — 스타일 수준의 변경은 자동 수정 대상이 아님
4. **검증 실행** — 수정 후 구문 오류 확인
5. **실패 시 롤백 안내** — `git checkout -- {file}`로 복구 가능함을 안내

## 설정

`.harness/code-review.json`의 추가 옵션:

```json
{
  "fix": {
    "auto_confirm": false,
    "run_lint_after": true,
    "max_parallel_agents": 5
  }
}
```

- `auto_confirm`: true면 수정 계획 확인 없이 바로 진행 (기본: false)
- `run_lint_after`: 수정 후 lint/typecheck 자동 실행 (기본: true)
- `max_parallel_agents`: 동시 생성할 cr-fix 에이전트 최대 수 (기본: 5)
