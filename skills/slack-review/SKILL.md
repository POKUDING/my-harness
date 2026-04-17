---
name: slack-review
description: Slack List 미완료 요청 확인, 코드 변경 검증, 코드리뷰, 완료 처리까지 일괄 수행
---

# Task Review - 작업 검증 및 완료 처리

Slack List 계획서의 미완료 항목을 확인하고, 코드 변경사항을 검증한 뒤 코드리뷰를 거쳐 Slack List 항목을 완료 상태로 업데이트한다.

## 사용법

```
/slack-review <SLACK_LIST_URL 또는 LIST_ID>
```

인자 없이 실행 시, `.harness/config.env`의 `SLACK_LIST_URL`을 사용한다. 설정이 없으면 `docs/plans/`에서 가장 최근 `slack-list-*-plan.md` 파일을 fallback으로 찾는다.

## 실행 흐름

### Step 0: 설정 확인 및 URL 결정

`.harness/config.env` 파일에서 `SLACK_BOT_TOKEN` 또는 `SLACK_USER_TOKEN`이 있는지 확인한다.

없으면 안내 후 중단:
```
Slack 토큰이 설정되지 않았습니다.
먼저 /slack-setup 을 실행해 토큰을 저장하세요.
```

**사용할 URL 결정 (우선순위 순):**
1. 인자로 URL이 전달된 경우 → 해당 URL 사용 + `.harness/config.env`의 `SLACK_LIST_URL`을 업데이트
2. 인자 없음 + `config.env`에 `SLACK_LIST_URL` 존재 → 저장된 URL 사용
3. 인자 없음 + `SLACK_LIST_URL` 없음 → 사용자에게 URL 입력 요청 후 `config.env`에 저장

URL을 새로 저장/업데이트할 때:
```bash
grep -q "^SLACK_LIST_URL=" .harness/config.env \
  && sed -i '' "s|^SLACK_LIST_URL=.*|SLACK_LIST_URL=<URL>|" .harness/config.env \
  || echo "SLACK_LIST_URL=<URL>" >> .harness/config.env
```

### Step 1: 미완료 요청사항 확인

Slack List에서 최신 데이터를 가져온다:

```bash
python3 skills/slack-plan/scripts/fetch_slack_list.py "<결정된 URL>"
```

가져온 아이템 중 상태가 **완료가 아닌 항목**을 필터링한다.
- 상태 컬럼 이름은 `status`, `상태`, `state` 등 다양할 수 있으므로 유연하게 매칭한다.
- 완료로 간주하는 값: `완료`, `done`, `complete`, `completed`, `백엔드 배포완료`, `이슈아님`
- 그 외 모든 값은 미완료로 간주한다.

미완료 항목이 없으면:
```
모든 요청사항이 완료 상태입니다. 처리할 항목이 없습니다.
```
라고 안내하고 종료한다.

미완료 항목 목록을 사용자에게 표로 보여준다:
```markdown
## 미완료 요청사항 ({N}건)

| # | 요청 내용 | 현재 상태 | 담당자 |
|---|----------|----------|--------|
| 1 | ...      | ...      | ...    |
```

### Step 2: 코드 변경 확인

각 미완료 항목에 대해 관련 코드 변경이 있는지 확인한다.

**매칭 방법 (우선순위 순):**

1. **plan-execute 기록 우선 사용** — `.harness/plans/`에서 가장 최근 `*-execute.json`을 Read:
   - 각 TODO 결과의 `slack_record_ids`와 Slack 아이템 `record_id`를 직접 매칭
   - 해당 TODO의 `files_changed` 목록을 그대로 사용 (추측 불필요)
   - TODO `status`로 진행 상태 바로 판정:
     - `completed` → **작업됨**
     - `partial` → **부분 작업**
     - `failed` → **미작업**
   - 매칭된 아이템은 fallback 대상에서 제외

2. **Fallback: plan 파일 + git log** — 실행 기록에서 매칭되지 않은 아이템에 한해:
   - `docs/plans/slack-list-*-plan.md`의 "원문 요청 요약" 테이블에서 `record_id` 컬럼 확인
   - 해당 아이템과 연결된 TODO의 `예상 작업 범위` 파일 목록 파악
   - `.harness/reviews/`의 최근 리뷰 이후 `git log --since` + `git diff`로 실제 변경 수집
   - 파일 목록이 겹치거나 커밋 메시지에 item 키워드가 나타나면 작업됨으로 판정

각 항목별 작업 진행 상태를 판정한다:
- **작업됨**: plan-execute `completed` 또는 관련 코드 변경 확인
- **미작업**: 실행 기록/관련 변경 모두 없음
- **부분 작업**: plan-execute `partial` 또는 일부 파일만 변경됨

결과를 사용자에게 보여준다:
```markdown
## 작업 진행 현황

| # | 요청 내용 | 진행 상태 | 관련 변경 |
|---|----------|----------|----------|
| 1 | ...      | 작업됨    | src/foo.ts (+23/-5), ... |
| 2 | ...      | 미작업    | -        |
```

**미작업 항목이 있으면** 사용자에게 알리고, 작업됨/부분 작업 항목에 대해서만 다음 단계를 진행할지 확인한다.

### Step 3: 코드리뷰 진행

작업됨으로 판정된 항목 전체에 대해 `/code-review` 스킬을 호출하여 다중 에이전트 리뷰를 수행한다.

1. 관련 변경사항의 diff 범위를 `/code-review`에 전달 (Step 2에서 결정된 범위)
2. `/code-review`가 `.harness/reviews/{YYYYMMDD_HHmmss}-review.json`을 생성할 때까지 대기
3. 생성된 리뷰 JSON의 findings를 항목별로 매핑하여 verdict를 판정한다:
   - **APPROVE**: 해당 항목 관련 파일에 `critical`/`major` severity 없음
   - **REQUEST_CHANGES**: `critical` 또는 `major` severity + `scope: fix_now` 존재
   - **NEEDS_DISCUSSION**: `major` severity + `scope: followup` 또는 판정 애매

결과를 사용자에게 보여준다:
```markdown
## 코드리뷰 결과

### 항목 #1: <요청 내용 요약>
- **Verdict**: APPROVE
- **변경 파일**: src/foo.ts, src/bar.ts
- **소견**: 정상적으로 구현됨. 추가 이슈 없음.

### 항목 #2: <요청 내용 요약>
- **Verdict**: REQUEST_CHANGES
- **변경 파일**: src/baz.ts
- **Findings**:
  - 🔴 Critical: ...
  - 🟡 Suggestion: ...
```

`REQUEST_CHANGES` 또는 `NEEDS_DISCUSSION` verdict가 있으면 해당 항목은 완료 처리하지 않고 사용자에게 수정을 안내한다.

### Step 4: 완료 항목 코멘트 표시

`APPROVE`를 받은 항목에 대해 작업 내용을 코멘트로 정리한다.

코멘트 작성을 위해 변경사항을 분석한다:

1. **변경된 API 스펙 파악**: diff에서 라우트, 엔드포인트, request/response 스키마, 상태코드 변경을 추출한다.
   - 새로 추가된 엔드포인트
   - 변경된 request 파라미터 또는 response 필드
   - 삭제된 엔드포인트
2. **변경된 유저 플로우 파악**: diff에서 비즈니스 로직, 조건 분기, 처리 순서 변경을 추출한다.
   - 새로 추가된 플로우 (예: 이메일 인증 단계 추가)
   - 변경된 플로우 (예: 결제 전 재고 확인 로직 추가)
   - 삭제된 플로우

Slack List 아이템에 코멘트를 추가한다:

```
[Task Review] 백엔드 작업 완료
- 처리일: YYYY-MM-DD
- 커밋: abc1234 - <커밋 메시지>
- 변경 파일: src/foo.ts, src/bar.ts
- 리뷰 결과: APPROVE

📡 변경된 API 스펙:
- [추가] POST /api/v1/orders - 주문 생성 엔드포인트
- [변경] GET /api/v1/users - response에 `role` 필드 추가
- [삭제] DELETE /api/v1/legacy/... - 레거시 엔드포인트 제거

🔀 변경된 유저 플로우:
- [추가] 주문 생성 시 재고 확인 → 결제 → 주문 확정 플로우
- [변경] 로그인 후 이메일 미인증 사용자는 인증 페이지로 리다이렉트
```

> API 스펙 또는 유저 플로우 변경이 없는 경우 해당 섹션은 "변경 없음"으로 표기한다.

`update_slack_list.py`의 `--field` 옵션으로 코멘트를 작성한다:

```bash
# 레코드별 다른 코멘트 작성 (stdin JSON)
cat <<'EOF' | python3 skills/slack-plan/scripts/update_slack_list.py <LIST_ID> --field "백엔드 변경 사항"
[
  {"record_id": "Rec...", "value": "[Task Review] 백엔드 작업 완료\n- 처리일: YYYY-MM-DD\n- 커밋: abc1234\n- 변경 파일: src/foo.ts, src/bar.ts\n- 리뷰 결과: APPROVE\n\n📡 변경된 API 스펙:\n- ...\n\n🔀 변경된 유저 플로우:\n- ..."},
  {"record_id": "Rec...", "value": "[Task Review] 백엔드 작업 완료\n- 처리일: ..."}
]
EOF
```

### Step 5: 백엔드 배포완료 상태로 변경

APPROVE된 항목의 Slack List 상태를 `백엔드 배포완료`로 변경한다.

`update_slack_list.py`의 `--status` 옵션으로 상태를 변경한다 (스키마 조회 및 select 옵션 매칭을 스크립트가 자동 처리):

```bash
python3 skills/slack-plan/scripts/update_slack_list.py <LIST_ID> \
  --record Rec... Rec... \
  --status "백엔드 배포완료"
```

### Step 6: 최종 요약

전체 처리 결과를 요약한다:

```markdown
## Task Review 완료

### 처리 결과
| # | 요청 내용 | 리뷰 결과 | Slack 상태 |
|---|----------|----------|-----------|
| 1 | ...      | APPROVE  | 백엔드 배포완료 ✅ |
| 2 | ...      | REQUEST_CHANGES | 미변경 ⚠️ |
| 3 | ...      | 미작업    | 미변경 ⏳ |

### 요약
- 전체 미완료 항목: {N}건
- 코드리뷰 통과: {X}건
- 완료 처리됨: {X}건
- 수정 필요: {Y}건
- 미작업: {Z}건
```

## 주의사항

1. **자동 완료 처리 전 반드시 사용자 확인**: APPROVE 항목을 Slack에 반영하기 전에 사용자에게 "다음 항목들을 백엔드 완료로 변경합니다. 진행할까요?" 라고 확인한다.
2. **코드리뷰는 보수적으로**: 의심스러운 변경은 REQUEST_CHANGES로 판정한다.
3. **Slack API 실패 시 graceful 처리**: API 호출 실패 시 에러를 표시하되 나머지 항목은 계속 처리한다.
4. **계획서가 없는 경우**: `docs/plans/`에 관련 계획서가 없으면 커밋 메시지와 diff만으로 판단하되, 매칭 정확도가 낮을 수 있음을 사용자에게 알린다.
