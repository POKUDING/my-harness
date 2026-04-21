---
name: code-review-walk
description: "코드 리뷰 결과의 finding을 하나씩 유저와 같이 점검하고 해결하는 대화형 스킬. 각 항목에 대해 발생 원인/이슈인 이유/해결 방안 예시를 설명하고, 작업 진행/패스/보류 상태를 저장하여 다음 실행 시 중복 작업을 방지한다."
---

# Code Review Walk — 대화형 리뷰 점검

`/code-review` 결과 JSON의 각 finding을 **한 번에 하나씩** 유저와 같이 점검한다. 각 항목에 대해 자세히 설명하고, 유저의 판단에 따라 작업/패스/보류를 기록한다. 다음 실행 시 이미 처리된 항목은 건너뛴다.

## 사용자 입력 UI (v0.16.1+)

이 스킬의 결정 지점은 모두 **`AskUserQuestion` 도구**로 받는다 — 텍스트 파싱(`[w]/[p]/...`)이 아닌 구조화된 선택지 UI. 각 지점의 구체 옵션은 아래 Step별 명세 참조.

**규칙:**
- 옵션은 2~4개. 권장 선택지는 첫 번째로 두고 label에 `(Recommended)` 추가
- `description`으로 각 옵션의 구체 결과·트레이드오프 설명
- `header`는 12자 이내 짧은 라벨
- 코드·diff·커밋 메시지 비교는 `preview` 필드에 fenced code block으로 넣음 (side-by-side 렌더)
- free-text가 필요한 부분(패스 사유, 보류 메모)은 AskUserQuestion의 자동 "Other" 옵션 또는 대화로 받음

## 사용법

```
/code-review-walk                                 # 최근 리뷰부터 시작 (처리된 항목 제외)
/code-review-walk .harness/reviews/20260410_...   # 특정 리뷰 지정
/code-review-walk --include-deferred              # 보류 항목도 다시 포함
/code-review-walk --filter critical,major         # 특정 severity만
/code-review-walk --category security             # 특정 category만
/code-review-walk --status                        # 진행 현황만 표시하고 종료
/code-review-walk --reset                         # state 파일 삭제 후 처음부터
```

## 실행 흐름

### Step 0: 리뷰 JSON 로드

1. 인자 있음 → 지정된 `*-review.json` 파일 Read
2. 인자 없음 → `.harness/reviews/*/` 하위에서 가장 최근 `*-review.json` 자동 탐지
   ```bash
   ls -t .harness/reviews/*/*-review.json | head -1
   ```
3. 파일 없으면 안내 후 중단:
   ```
   리뷰 결과를 찾을 수 없습니다. 먼저 /code-review를 실행하세요.
   ```

리뷰 파일 경로에서 폴더와 prefix를 추출:
```
review_dir = dirname(review_json_path)                  # .harness/reviews/{TS}-{SUM}/
prefix     = basename(review_json_path, "-review.json") # {TS}-{SUM}
```

### Step 1: State 파일 로드

State 파일 경로: `{review_dir}/{prefix}-walk.json`
예: `.harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-walk.json`

- 존재 → 기존 진행 상태 로드
- 부재 → 신규 state 생성

`--reset` 플래그 → 기존 state 삭제 후 신규 생성
`--status` 플래그 → 현재 state 요약만 표시하고 종료 (Step 6)

### Step 2: 대상 finding 필터링

다음 조건으로 대상 findings 선정:

1. **기본 제외**: `status`가 `done`, `passed`, `deferred`인 항목
2. **`--include-deferred`** → `deferred` 포함
3. **`--filter severity`** → 지정 severity만 (critical/major/minor/nit)
4. **`--category`** → 지정 category만

**진행 중(`in_progress`) 항목이 있으면 먼저 처리**:
```
이전 세션에서 중단된 항목이 있습니다:
- CR-005: "timeout 미설정" (시작: 2026-04-17 14:30)
재개하시겠어요? [Y/n]
```

### Step 3: 대상 요약

처리할 findings 수를 보여준다:

```
## Code Review Walk

### 대상 리뷰
- 리뷰 파일: 20260410_143022-review.json
- 전체 findings: 15건
- 이미 처리됨: 5건 (done: 3, passed: 1, deferred: 1)
- 이번 세션 대상: 10건

### 대상 분포
| Severity | 건수 |
|----------|------|
| Critical | 1 |
| Major    | 4 |
| Minor    | 4 |
| Nit      | 1 |
```

위 요약을 보여준 후 **AskUserQuestion**으로 시작 여부를 묻는다:

```
AskUserQuestion({
  questions: [{
    question: "N건의 finding을 순차 점검합니다. 시작할까요?",
    header: "Walk 시작",
    options: [
      { label: "시작 (Recommended)",
        description: "첫 finding부터 순서대로 점검 시작" },
      { label: "취소",
        description: "세션을 종료합니다. state 변경 없음." }
    ],
    multiSelect: false
  }]
})
```

사용자가 "취소" 선택 시 스킬 종료.

### Step 4: Finding 순회 (메인 루프)

severity 순(Critical → Major → Minor → Nit)으로 하나씩 표시한다.

각 finding에 대해:

#### 4-1. 컨텍스트 보강

설명 출력 **직전에** 다음을 수집하여 더 풍부한 설명을 만든다:

1. **해당 파일의 관련 코드 Read** — finding의 `file`, `lines`, `symbol`에 해당하는 코드와 주변 맥락 5-10줄
2. **연관 패턴 검색** — Grep으로 같은 프로젝트 내 비슷한 패턴이 어떻게 처리되는지 확인 (예: 다른 fetch 호출은 어떻게 timeout을 다루는지)
3. **카테고리 기반 트레이드오프** — 아래 표의 카테고리별 기본 템플릿 + 이번 finding의 구체 맥락으로 장단점 합성

복잡하거나 맥락 파악이 어려운 Critical/Major finding에는 필요 시 `my-harness:researcher` 에이전트로 1-2분 심층 분석 위탁.

#### 4-2. 구조화된 설명 출력

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[3/10] CR-005 · 🔴 Critical · reliability
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

**제목:** 외부 API 호출에 timeout 미설정
**파일:** src/integrations/payment.ts:45-52 (symbol: charge)
**Detected by:** my-harness:cr-reliability (consensus: 양쪽 supervisor 일치)

## 📌 배경
이 코드는 결제 게이트웨이(Stripe 추정)와 통신하는 외부 HTTP 호출부다.
Node.js 기본 fetch는 timeout 기본값이 없어 네트워크 지연이나 상대 서비스
장애 시 응답을 무한 대기한다. Node 18+부터 `AbortController`로 제어하거나
`undici`의 `bodyTimeout`/`headersTimeout`을 사용하는 것이 권장된다.

같은 레포 내 `src/integrations/slack.ts`에서는 이미 AbortController로
7초 timeout을 적용하고 있음. 패턴 불일치 상태.

## 🔍 발생 원인
fetch 호출에 timeout이나 AbortController가 설정되지 않아 응답이 오지 않을 때
무한 대기 상태가 됨.

```typescript
// 문제 코드 (src/integrations/payment.ts:45-52)
const res = await fetch(url, { method: 'POST', body });
```

## ⚠️ 이슈인 이유
결제 게이트웨이 장애 시 요청 워커가 모두 이 호출에 묶임. 시간이 지날수록
사용 가능한 워커가 고갈되어 서비스 전체가 응답 불가 상태로 전파됨.

**미해결 시 영향**
- **발생 가능성**: 중간 — 외부 서비스 장애는 분기에 1-2회 수준으로 발생
- **발생 시 심각도**: 높음 — 서비스 전체 응답 중단으로 번짐
- **복구 비용**: 재시작 필요 (상태가 나쁘게 복구됨)
- **관측 가능성**: 낮음 — 타임아웃 없으면 장애 감지 자체가 늦어짐

## 💡 해결 방안
```typescript
// After
const ctrl = new AbortController();
const timer = setTimeout(() => ctrl.abort(), 5000);
try {
  const res = await fetch(url, { method: 'POST', body, signal: ctrl.signal });
  // ...
} finally {
  clearTimeout(timer);
}
```

또는 기존 `src/integrations/slack.ts`와 동일한 유틸 함수로 추출해서
재사용 가능.

## ✅ 수정했을 때 장점
- 외부 서비스 장애가 내 서비스로 번지는 경로 차단 (주된 이득)
- 타임아웃 로그로 상대 서비스 이상을 조기 감지 가능
- 레포 내 다른 외부 호출과 패턴 일치 (유지보수성 ↑)
- 테스트에서 느린 응답 시나리오 검증 가능해짐

## ⚠️ 수정 시 고려사항
- **리팩토링 범위**: 이 함수 호출부 ~3곳 확인 필요 (Grep으로 유틸 추출 대상 판단)
- **적절한 timeout 값 결정**: 결제 게이트웨이의 p99 응답 시간 기준 +여유
  (너무 짧으면 정상 요청 실패, 너무 길면 보호 효과 감소 — 5s 권장)
- **재시도와의 조합**: 현재 재시도 로직이 있는지 확인 — 있으면 timeout이
  재시도를 트리거하지 않도록 에러 구분 필요 (AbortError vs 네트워크 에러)
- **테스트 영향**: 모킹된 fetch에 signal 지원 확인 필요
- **멱등성 고려**: POST 호출은 timeout 시 서버에 반영됐는지 모호 — 재시도 시
  중복 결제 방지 로직 점검 필요

## 🔗 연관 코드
- `src/integrations/slack.ts:28` — 동일 패턴 이미 적용됨 (참고)
- `src/integrations/payment.ts:78` — 같은 파일의 다른 호출도 동일 이슈 가능성

**Scope:** fix_now (이 PR에서 수정 권장)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 필드 매핑 및 보강 기준

| 섹션 | 출처 |
|------|------|
| **📌 배경** | 관련 파일 Read + 연관 패턴 Grep + 일반적 도메인 지식으로 합성 |
| **🔍 발생 원인** | `problem` + 실제 코드 스니펫 (가능한 경우) |
| **⚠️ 이슈인 이유** | `why` + 발생 가능성/심각도/복구 비용 분해 |
| **💥 미해결 시 영향** | `impact`를 가능성·심각도·관측성 관점으로 분해 |
| **💡 해결 방안** | `recommendation` + before/after 코드 블록 |
| **✅ 수정 시 장점** | 카테고리 기반 템플릿 + finding 맥락으로 합성 |
| **⚠️ 수정 시 고려사항** | 아래 카테고리별 트레이드오프 템플릿 + 실제 코드 맥락 |
| **🔗 연관 코드** | Grep 결과 중 관련성 높은 3-5개 |

### 카테고리별 트레이드오프 템플릿

| Category | 일반 장점 | 일반 고려사항 |
|----------|----------|---------------|
| **correctness** | 의도한 동작 보장, 회귀 방지 | 기존 동작에 의존하던 호출부 확인 |
| **reliability** | 장애 격리, 관측 가능성 ↑ | 타임아웃 값 선정, 재시도 조합, 멱등성 |
| **security** | 공격 벡터 차단 | 합법 사용자 플로우 영향 여부, 성능 trade-off |
| **performance** | 응답 시간 단축, 리소스 절약 | 읽기 난이도 상승 가능, 캐시 무효화 로직 필요 |
| **maintainability** | 변경 용이성, 테스트 가능성 ↑ | 단기 리팩토링 비용, 리뷰 범위 확대 |

**주의:** 템플릿은 시작점일 뿐. 반드시 해당 finding의 **구체적 맥락**(어느 파일, 어느 호출부, 어떤 레포 패턴)을 녹여 합성한다. 일반론만 나열하면 유용성이 떨어진다.

#### 4-3. 유저 액션 선택

**AskUserQuestion**으로 4개 옵션 제시:

```
AskUserQuestion({
  questions: [{
    question: "<FINDING_ID>: <finding.title> — 어떻게 처리할까요?",
    header: "Walk action",
    options: [
      { label: "작업 진행 (Recommended)",
        description: "함께 코드 수정. 에이전트가 초안을 제시하고 같이 다듬음. 수정 후 자동 커밋 옵션 제공" },
      { label: "패스",
        description: "실제 문제 아니라고 판단. 다음 실행 시 제외 (사유는 다음 단계에서 입력)" },
      { label: "보류",
        description: "당장은 넘기고 나중에 재검토. 중앙 백로그에도 push되어 추적됨. --include-deferred 없이는 다음 walk 실행 제외" },
      { label: "건너뛰기",
        description: "이번 세션만 넘김. state 저장 안 되므로 다음 실행 시 다시 등장" }
    ],
    multiSelect: false
  }]
})
```

**종료 `[q]` 처리:** AskUserQuestion 옵션에서 제외. 유저가 답변 대신 "그만", "종료", "나중에 이어서" 같은 자연어로 응답하면 Claude가 포착 → Step 6 요약 후 종료. Ctrl+C도 동일.

사용자가 AskUserQuestion의 자동 "Other" 옵션으로 자유 텍스트 입력 시: Claude가 의도 해석 (예: "이건 보류"→보류 처리, "같이 고쳐"→작업 진행). 모호하면 재질문.

#### 4-4. 액션별 처리

**[w] 작업 진행:**
1. **사전 체크** — `git status --porcelain`으로 작업 트리 확인:
   - 깨끗함 → 진행
   - 이 finding 외의 변경사항이 있음 → **AskUserQuestion + preview**로 경고:
     ```
     AskUserQuestion({
       questions: [{
         question: "작업 트리에 다른 변경이 있습니다. 어떻게 진행할까요?",
         header: "Dirty tree",
         options: [
           { label: "기존 변경 먼저 커밋 (Recommended)",
             description: "기존 작업을 먼저 커밋한 뒤 finding 수정을 독립 커밋으로 진행",
             preview: "```\n<git status --porcelain 출력>\n```" },
           { label: "stash 후 진행",
             description: "git stash push로 기존 변경을 보관하고 finding만 수정. 완료 후 git stash pop 안내" },
           { label: "무시하고 진행",
             description: "기존 변경 유지한 채 finding 수정. 커밋은 git add -- {finding의 files_changed}만 수행하여 섞임 방지" },
           { label: "중단",
             description: "이 finding 작업을 취소하고 다음으로 이동 (state는 변경 없음)" }
         ],
         multiSelect: false
       }]
     })
     ```
2. state에 `in_progress` 마크 (중단 시 재개 가능)
3. `my-harness:researcher` 에이전트로 영향 범위 파악 (관련 호출부, 기존 패턴)
4. 수정 제안 제시 + 유저 승인 (**AskUserQuestion + diff preview**):
   ```
   AskUserQuestion({
     questions: [{
       question: "다음 수정을 적용할까요?",
       header: "Apply fix",
       options: [
         { label: "이대로 적용 (Recommended)",
           description: "제안된 수정을 Edit 도구로 바로 적용. 이어서 구문 체크·커밋 단계로 진행.",
           preview: "```diff\n<수정 diff (before/after)>\n```" },
         { label: "다른 접근 제안 요청",
           description: "이 방향이 아닌 대안을 제시받기. 이전 제안은 폐기됨." },
         { label: "수동 조정 후 재제시",
           description: "사용자가 대화로 세부 조정 사항을 지시. 그에 따라 수정안을 다시 만든 뒤 재승인." },
         { label: "수정 중단",
           description: "이 finding 작업을 멈추고 state는 in_progress로 유지. 다음 실행 시 재개 가능." }
       ],
       multiSelect: false
     }]
   })
   ```
   "이대로 적용" 선택 → Edit 도구로 파일 수정.
   "다른 접근" 선택 → 대안 제시 후 AskUserQuestion 재호출.
   "수동 조정" 선택 → 자유 텍스트로 지시받아 수정안 조정.
5. 수정 완료 후 구문 체크 (`tsc --noEmit` 등)
6. **자동 커밋** (기본 활성화, config로 비활성화 가능):
   - 이번 수정으로 실제 변경된 파일만 스테이징: `git add -- {files_changed}`
   - 커밋 메시지 생성 (아래 템플릿) 후 **AskUserQuestion + preview**로 승인 받기:
     ```
     AskUserQuestion({
       questions: [{
         question: "이 메시지로 커밋할까요?",
         header: "Commit",
         options: [
           { label: "그대로 커밋 (Recommended)",
             description: "아래 메시지로 즉시 git commit. pre-commit 훅은 정상 실행 (--no-verify 금지).",
             preview: "```\nfix(review): CR-005 외부 API 호출에 timeout 미설정\n\nAbortController로 5s timeout 추가. src/integrations/slack.ts의\n기존 패턴과 동일하게 적용.\n\nReview:  .harness/reviews/20260410_143022-review.json\nFinding: CR-005 (reliability/critical)\nFiles:   src/integrations/payment.ts\n```" },
           { label: "메시지 수정",
             description: "사용자가 자유 텍스트로 다른 제목·본문을 지시. 그에 따라 재생성 후 재승인." },
           { label: "커밋 건너뛰기",
             description: "수정은 유지하되 커밋은 수동으로 나중에. state는 done으로 기록." }
         ],
         multiSelect: false
       }]
     })
     ```
   - 승인 시 `git commit` 실행 (사전 체크 [stash 후 진행] 옵션을 썼다면 stash pop 안내 포함)
   - config `auto_commit: false`면 이 스텝 전체 생략
7. state 업데이트:
   ```json
   {
     "status": "done",
     "action": "AbortController + 5s timeout 추가",
     "files_changed": ["src/integrations/payment.ts"],
     "commit": "abc1234",
     "timestamp": "..."
   }
   ```
8. **중앙 백로그에서 대응 항목 resolve** — 이 finding이 이전 리뷰에서 이미 백로그에 올라가 있었다면 자동 해결 처리:
   ```bash
   # 먼저 backlog에서 같은 이슈를 찾는다 (dedup_key 기반)
   python3 scripts/backlog_tool.py list --file "<finding.file>" --json > /tmp/bl_search.json
   # Python 한 줄로 매칭 후보 추출 (file + symbol + category 일치)
   BL_ID=$(python3 -c "import json,sys; e=[x for x in json.load(open('/tmp/bl_search.json')) if x.get('symbol')=='<finding.symbol>' and x.get('category')=='<finding.category>']; print(e[0]['id'] if e else '')")
   if [[ -n "$BL_ID" ]]; then
     python3 scripts/backlog_tool.py resolve "$BL_ID" --commit "<방금 커밋 SHA>" --approach "<action 요약>"
     echo "[walk] backlog $BL_ID auto-resolved"
   fi
   ```
   매칭이 없으면 조용히 진행. walk에서의 작업은 "새로 발견한 finding을 바로 수정"한 경우가 많아 backlog에 항목이 없는 게 정상.

### 자동 커밋 메시지 템플릿

```
fix(review): {FINDING_ID} {title}

{action 요약 1-3줄 — 무엇을 어떻게 바꿨는지}

Review:  .harness/reviews/{review-ts}-review.json
Finding: {finding.id} ({category}/{severity})
Files:   {file1}, {file2}, ...
```

**subject prefix 매핑** (카테고리 → Conventional Commit 타입):

| Category | Prefix |
|----------|--------|
| correctness | `fix` |
| reliability | `fix` |
| security | `fix` (또는 `security`) |
| performance | `perf` |
| maintainability | `refactor` |

수정이 신규 기능을 동반하지 않고 리뷰 지적 해결에 국한되므로 대부분 `fix` 또는 `refactor` 계열.

**[p] 패스:**
1. 패스 사유 입력 받음: "왜 문제가 아니라고 판단하셨나요? (선택)"
2. state:
   ```json
   {
     "status": "passed",
     "reason": "이 서비스는 내부 전용이며 외부 장애 영향 없음",
     "timestamp": "..."
   }
   ```

**[d] 보류:**
1. 보류 사유/메모 입력: "나중 검토 시 참고할 메모 (선택)"
2. state:
   ```json
   {
     "status": "deferred",
     "note": "Q2 리팩토링 플랜에 포함 예정",
     "timestamp": "..."
   }
   ```
3. **중앙 백로그에 push** — 모든 보류 항목이 `.harness/review-backlog/backlog.json`으로 흘러들어 여러 리뷰에 걸쳐 추적되도록:
   ```bash
   python3 scripts/backlog_tool.py add-manual \
     --file "<finding.file>" \
     --title "<finding.title>" \
     --severity "<finding.severity>" \
     --category "<finding.category>" \
     --problem "<finding.problem>" \
     --recommendation "<finding.recommendation>" \
     --symbol "<finding.symbol>" \
     --lines "<finding.lines>" \
     --note "<user_note>" \
     --source-review "<review.json 절대 경로>"
   ```
   dedup key가 이미 존재하면 `occurrence_count`만 증가 → 여러 번 보류된 이슈는 더 눈에 띄게 됨.
   스크립트 실패 시 경고만 표시하고 walk는 계속 진행 (state는 저장됨).

**[s] 건너뛰기:**
- state 변경 없음. 다음 finding으로 이동.

**[q] 종료:**
- 현재까지 진행 상태를 state 파일에 저장
- Step 6 요약 출력 후 종료

### Step 5: 모든 finding 완료 시

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
모든 대상 finding 점검 완료
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

Step 6로 진행.

### Step 6: 세션 요약

```markdown
## Code Review Walk 세션 요약

### 이번 세션
- 점검: 8건
- 작업 완료: 4건
- 패스: 2건
- 보류: 2건

### 이번에 수정한 항목
| ID | Severity | 제목 | 파일 |
|----|----------|------|------|
| CR-001 | Critical | SQL Injection | src/api/users.ts |
| CR-005 | Major | timeout 미설정 | src/integrations/payment.ts |
| ...

### 전체 진행 현황 (review 전체 기준)
- 전체: 15건
- 완료/패스: 8건 (53%)
- 보류: 3건 (20%)
- 미처리: 4건 (27%)

### 저장된 파일
- State: .harness/reviews/{review-ts}-walk.json
- 수정된 소스: src/api/users.ts, src/integrations/payment.ts, ...

### 다음 단계
- `git diff`로 변경 확인
- 문제 없으면 커밋 → `/slack-review`로 Slack 반영
- 남은 finding 계속 처리: `/code-review-walk`
- 보류 항목 재검토: `/code-review-walk --include-deferred`
```

## State 파일 형식

`.harness/reviews/{review-ts}-walk.json`:

```json
{
  "metadata": {
    "source_review": "20260410_143022-review.json",
    "source_review_total": 15,
    "first_walked_at": "2026-04-17T10:00:00",
    "last_walked_at": "2026-04-17T14:30:00",
    "walk_session_count": 2
  },
  "summary": {
    "done": 4,
    "passed": 2,
    "deferred": 2,
    "in_progress": 0,
    "untouched": 7
  },
  "findings": {
    "CR-001": {
      "status": "done",
      "action": "파라미터화 쿼리로 변경",
      "files_changed": ["src/api/users.ts"],
      "commit": "abc1234",
      "timestamp": "2026-04-17T10:15:00"
    },
    "CR-002": {
      "status": "passed",
      "reason": "스타일 선호 차이로 판단",
      "timestamp": "2026-04-17T10:20:00"
    },
    "CR-003": {
      "status": "deferred",
      "note": "대규모 리팩토링 필요, 별도 이슈 등록 예정",
      "timestamp": "2026-04-17T10:25:00"
    }
  }
}
```

## 상태 정의

| status | 다음 실행 시 | 의미 |
|--------|-------------|------|
| `done` | 제외 | 실제 코드 수정 완료 |
| `passed` | 제외 | 문제 아니라고 판단, 수정 없이 종결 |
| `deferred` | 제외 (기본) / 포함 (`--include-deferred`) | 당장은 넘기고 나중에 다시 볼 것 |
| `in_progress` | 우선 재개 제안 | 세션 중단으로 인한 미완 |
| (없음) | 포함 | 아직 점검하지 않음 |

## 안전 장치

1. **작업 진행 전 승인 필수** — 에이전트가 수정안을 제시한 뒤 유저 확인 없이 Edit 적용 금지
2. **비파괴적 상태 변경** — state 업데이트만 하고 기존 review JSON은 변경하지 않음
3. **종료 시 상태 저장** — `[q]`, Ctrl-C, 에러 발생 모두 최신 state 저장 시도
4. **리뷰 외 정보 표시** — detected by, confidence, scope 등 JSON의 모든 유용 필드 활용
5. **커밋 스테이징은 파일 단위 정밀 지정** — `git add -- {files_changed}`만, 절대 `git add -A` 금지 (다른 파일이 섞이지 않도록)
6. **--no-verify 금지** — 프로젝트 pre-commit 훅은 그대로 실행. 훅 실패 시 커밋 중단 후 유저에게 결과 보고
7. **커밋 실패 시 롤백 안내** — 구문 체크 실패/훅 실패 시 state는 `done` 마크 안 함, 다음 실행 시 재시도 가능

## 설정

`.harness/code-review-walk.json` (선택):

```json
{
  "default_severity_filter": ["critical", "major"],
  "auto_typecheck_after_edit": true,
  "show_code_snippet_context_lines": 5,
  "auto_commit": true,
  "commit_prefix_override": null,
  "commit_require_approval": true
}
```

- `auto_commit`: 수정 후 자동 커밋 활성화 (기본: true)
- `commit_prefix_override`: 카테고리 매핑 대신 고정 prefix 사용 (예: `"fix"`)
- `commit_require_approval`: 커밋 전 유저 승인 요청 (기본: true, false면 바로 커밋)
