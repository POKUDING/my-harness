---
name: plan-execute
description: "작업 계획서(docs/plans/*-plan.md)를 입력으로 받아 TODO를 병렬 실행하여 코드를 작성하는 스킬. 의존성 분석 → 배치 분할 → 병렬 executor → 배치 간 검증/자가수정 패턴으로 동작. 계획 기반 구현, 자동 코딩, TODO 실행, plan execution 요청 시 이 스킬을 사용할 것."
---

# Plan Execute — 계획 기반 병렬 구현

작업 계획서의 TODO들을 분석하여 **독립적인 것끼리 병렬로**, **의존성 있는 것은 순차로** 실행한다. 각 배치 완료 후 검증하고 실패 시 자가 수정을 시도한다.

## 사용법

```
/plan-execute                                       # 가장 최근 plan 자동 탐지
/plan-execute docs/plans/slack-list-F12345-plan.md  # 특정 plan 지정
/plan-execute --todo TODO-001 TODO-003              # 특정 TODO만 실행
/plan-execute --dry-run                             # 실행 계획만 보고 중단
/plan-execute --priority P0 P1                      # 우선순위 필터
```

## 실행 흐름

### Step 0: 계획서 로드

1. **인자 있음** → 지정된 파일 Read
2. **인자 없음** → `docs/plans/*-plan.md` 중 가장 최근 수정된 파일 자동 선택
3. 파일이 없으면 안내 후 중단:
   ```
   실행할 계획서가 없습니다.
   먼저 /slack-plan을 실행하여 계획서를 생성하거나,
   docs/plans/에 직접 계획서를 작성하세요.
   ```

### Step 1: TODO 파싱

계획서에서 `## 3. 실행 TODO` 섹션을 파싱하여 각 TODO를 추출한다.

각 TODO의 필수 메타데이터:
- `id` (TODO-XXX)
- `title`
- `description`
- `priority` (P0/P1/P2)
- `scope` (`예상 작업 범위` — 영향 파일/모듈)
- `depends_on` (`선행 조건` — 다른 TODO ID 언급 시 의존성 추출)
- `completion_criteria`
- `slack_record_ids` (`Slack record_id` 필드 — 없으면 빈 배열. `/slack-review` 연동에 사용)

**필터 적용:**
- `--todo` 플래그 → 지정된 TODO만
- `--priority` 플래그 → 해당 우선순위만

### Step 2: 의존성 분석 및 배치 계획

**의존성 그래프 구성:**
1. 명시적 의존성: `선행 조건`에서 언급된 TODO ID
2. 암시적 의존성: 동일 파일을 수정하는 TODO → 파일 충돌 방지를 위해 순차화
3. 기반 의존성: 모듈 생성 TODO → 그 모듈을 사용하는 TODO

**배치 생성 (Topological Sort):**
- 의존성이 해결된 TODO들을 같은 배치에 모음
- 배치 내 TODO는 서로 독립적 → 병렬 실행 가능
- 배치 간 순서는 의존성에 따라 결정

**파일 충돌 검사:**
- 같은 파일을 수정하는 TODO가 한 배치에 있으면 → 하나는 다음 배치로 분리
- 신규 생성 파일은 충돌 아님 (단, 같은 경로 생성은 예외 처리)

### Step 3: 실행 계획 검토

사용자에게 배치 계획을 보여주고 승인을 받는다:

```markdown
## 실행 계획

### 입력
- 계획서: docs/plans/slack-list-F12345-plan.md
- 필터: priority=P0,P1
- 총 TODO: 7건 → 실행 대상 5건 (P2 2건 제외)

### 실행 순서

**배치 1 — 병렬 3건** (서로 독립적)
- TODO-001: 결제 게이트웨이 어댑터 추가
  - 파일: src/integrations/stripe.ts (신규)
- TODO-002: 주문 도메인 모델 확장
  - 파일: src/models/order.ts (수정)
- TODO-005: API 에러 응답 표준화
  - 파일: src/middleware/error-handler.ts (신규), src/app.ts (수정)

**배치 2 — 순차 1건** (TODO-001, TODO-002 선행 필요)
- TODO-003: POST /api/v1/payments 엔드포인트
  - 파일: src/api/payments.ts (신규), src/routes/index.ts (수정)

**배치 3 — 순차 1건** (TODO-003 선행 필요)
- TODO-004: 결제 완료 시 주문 상태 자동 전이
  - 파일: src/services/order.ts (수정)

### 병렬도
- 최대 병렬 실행: 3
- 예상 배치 수: 3

진행할까요? [Y/n]
```

`--dry-run`이면 여기서 중단.

### Step 4: 배치별 병렬 실행

각 배치마다:

1. **스폰**: 배치 내 각 TODO에 `my-harness:plan-executor` 에이전트 생성 (`run_in_background: true`)

```
Agent(
  description: "Execute TODO-001",
  subagent_type: "my-harness:plan-executor",
  model: "sonnet",
  run_in_background: true,
  prompt: """
  아래 TODO를 구현하라.

  {TODO 전체 내용}

  ## 프로젝트 컨텍스트
  - 기술 스택: {package.json 등에서 추론}
  - 관련 파일: {scope 필드의 파일}
  - 컨벤션: {감지된 스타일}

  결과를 JSON으로 반환하라.
  """
)
```

2. **진행 모니터링**: 각 executor 완료 시 진행 보고
```
[진행] 배치 1/3 — 2/3 완료
  ✅ TODO-001: completed (3 files, 94 lines)
  ✅ TODO-002: completed (1 file, 12 lines)
  ⏳ TODO-005: 진행중...
```

3. **배치 완료 대기**: 배치 내 모든 TODO가 완료될 때까지 대기

### Step 5: 배치 간 검증

배치 완료 후 즉시 검증 실행:

1. **구문 체크**: 프로젝트에 맞는 기본 체크
   - `package.json` → `npx tsc --noEmit` 또는 `npm run lint`
   - `pyproject.toml` → `python -m py_compile` 또는 `ruff check`
   - 기타 언어별 기본 체크

2. **결과 판정**:
   - ✅ 통과 → 다음 배치로 진행
   - ❌ 실패 → Step 5a (자가 수정)

### Step 5a: 자가 수정 루프 (Ralph 패턴)

검증 실패 시 최대 2회 자가 수정 시도:

1. 에러 출력을 분석하여 영향 파일 식별
2. `my-harness:quick-fix` 에이전트를 각 에러 파일별로 병렬 스폰
3. 수정 후 재검증
4. 2회 시도 후에도 실패하면 → 사용자에게 보고 후 진행 여부 확인

### Step 6: 전체 완료 후 결과 보고

```markdown
## Plan Execute 완료

### 실행 결과
| TODO | 상태 | 파일 변경 | 비고 |
|------|------|----------|------|
| TODO-001 | ✅ completed | +3 신규, +0 수정 | - |
| TODO-002 | ✅ completed | +0 신규, +1 수정 | - |
| TODO-005 | ⚠️ partial | +1 신규, +1 수정 | 테스트 미작성 (프레임워크 설정 필요) |
| TODO-003 | ✅ completed | +1 신규, +1 수정 | - |
| TODO-004 | ❌ failed | - | blockers: 외부 워크플로우 엔진 필요 |

### 요약
- 실행: 5건 | 완료: 3건 | 부분: 1건 | 실패: 1건
- 총 변경 파일: 8개 (+5 신규, +3 수정)
- 배치 실행: 3회, 자가 수정: 1회 (배치 2에서 타입 에러 해결)

### 변경 파일 목록
- src/integrations/stripe.ts (신규, 145 lines)
- src/models/order.ts (수정, +12/-3)
- ...

### 다음 단계
- `git diff`로 변경 확인
- `/code-review` 로 리뷰 수행
- 통과 시 커밋 → `/slack-review`로 Slack 반영
```

### Step 7: 기록 저장

`.harness/plans/{YYYYMMDD_HHmmss}-execute.json`과 `.harness/plans/{YYYYMMDD_HHmmss}-execute.md` 저장.

JSON 형식:
```json
{
  "metadata": {
    "date": "YYYY-MM-DDTHH:mm:ss",
    "source_plan": "docs/plans/slack-list-F12345-plan.md",
    "filters": {"priority": ["P0", "P1"]},
    "batches": 3,
    "total_todos": 5,
    "completed": 3,
    "partial": 1,
    "failed": 1
  },
  "batches": [
    {
      "batch_number": 1,
      "parallelism": 3,
      "todos": ["TODO-001", "TODO-002", "TODO-005"],
      "verification": {"passed": true, "attempts": 1}
    }
  ],
  "results": [
    {
      "todo_id": "TODO-001",
      "status": "completed",
      "slack_record_ids": ["Rec..."],
      "files_changed": [{"path": "src/integrations/stripe.ts", "action": "created"}]
    }
  ]
}
```

## 안전 장치

1. **실행 전 사용자 승인 필수** — Step 3에서 배치 계획을 보여주고 승인 받음
2. **커밋되지 않은 변경 경고** — 시작 전 `git status` 확인, 미커밋 변경 있으면 경고
3. **롤백 안내** — 실패 시 `git checkout -- .` 또는 `git stash`로 복구 가능함을 안내
4. **배치 간 검증 실패 시 중단** — 자가 수정 2회 실패하면 진행 중단, 사용자 판단
5. **병렬도 제한** — 기본 최대 5 (설정으로 변경 가능)

## 설정

`.harness/plan-execute.json` (선택):

```json
{
  "max_parallel": 5,
  "max_self_fix_attempts": 2,
  "auto_commit_per_batch": false,
  "verification_commands": {
    "typescript": "npx tsc --noEmit",
    "python": "ruff check ."
  }
}
```

## 제약 사항

- **파일 수준 병렬화**: 같은 파일 수정 TODO는 다른 배치로 분리. 함수 수준 병렬화는 지원하지 않음.
- **명시적 의존성 우선**: 암시적 의존성(호출 체인)은 파일 기반으로만 감지. 세밀한 제어가 필요하면 `선행 조건`에 명시.
- **장기 실행 작업 부적합**: 각 TODO는 자동 실행 가능한 코드 작성 수준. 수작업 배포, 외부 승인 대기 등은 `blockers`로 빠짐.
