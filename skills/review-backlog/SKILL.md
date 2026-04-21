---
name: review-backlog
description: "코드 리뷰의 followup/보류 항목을 중앙 백로그에서 관리하는 스킬. /code-review의 major+ followup은 자동 append, /code-review-walk의 [d]보류도 자동 push. 조회·해결·dismiss·stale 정리·통계 제공. dedup key로 여러 리뷰에서 반복 지적되는 이슈 자동 병합(재발견 횟수 카운트)."
---

# Review Backlog — 코드 리뷰 보류 항목 중앙 트래커

여러 리뷰에 걸쳐 발생한 `followup` / 보류 findings를 한 파일에 모아 관리한다. **기존엔 리뷰 폴더마다 흩어져 망각되던 항목**을 한 눈에 파악 + 추적.

## 데이터 위치

```
.harness/review-backlog/
  backlog.json    — 기계가 읽는 정본 (dedup_key, occurrence_count 포함)
  backlog.md      — 사람이 읽는 버전 (쓰기마다 자동 생성)
  resolved.json   — 해결된 항목 이력 (트렌드용)
```

`.harness/`는 gitignored라 로컬 전용. 팀 공유가 필요하면 `.gitignore`에 `!.harness/review-backlog/backlog.md` 예외 추가.

## 핵심 개념

- **dedup key**: `sha1(file + symbol + category + keywords)` 12자 해시. 같은 파일·심볼·카테고리·유사 제목이면 동일 이슈로 수렴
- **occurrence_count**: 여러 리뷰가 같은 이슈를 다시 지적하면 증가 → 우선순위 시그널
- **status**: `open` (미해결) · `resolved` (해결) · `dismissed` (won't fix) · `stale` (코드 변경으로 무효)
- **자동 append 정책**: severity ≥ `major`의 `scope: followup` 만 자동. `minor` 이하는 `/code-review-walk` 보류 시 수동만

## 사용법

```
/review-backlog                        # open 항목 전체 (기본 동작)
/review-backlog list                   # 위와 동일
/review-backlog list --severity major  # severity 필터
/review-backlog list --file tasks.py   # 파일명 부분 매치
/review-backlog list --status stale    # 상태 필터
/review-backlog list --json            # JSON 원본 출력 (파이프용)

/review-backlog resolve BL-005 --commit abc1234 --approach "파라미터화 쿼리 적용"
/review-backlog dismiss BL-012 --reason "이미 삭제된 코드"
/review-backlog stale-check            # 파일/심볼 존재 확인 후 stale 마킹
/review-backlog import-all             # 기존 .harness/reviews/ 전수 스캔 (one-shot)
/review-backlog render-md              # backlog.md 재생성
/review-backlog stats                  # open/resolved/stale/dismissed 요약
```

## 실행 흐름

### Step 1: 인자 파싱

- 인자 없음 또는 `list` → list 명령으로 위임
- `resolve BL-XXX` → resolve 명령
- `dismiss BL-XXX --reason "..."` → dismiss 명령
- `stale-check` → stale-check 명령
- `import-all` → import-all 명령
- `render-md` → render-md 명령
- `stats` → stats 명령
- 기타 → 사용법 안내

### Step 2: 스크립트 호출

모든 연산은 `scripts/backlog_tool.py` 에서 수행. 메인 세션은 인자 변환 + 결과 출력만 담당.

**list** (기본):
```bash
python3 scripts/backlog_tool.py list [--status X] [--severity X] [--file X] [--category X] [--json]
```

**resolve**:
```bash
python3 scripts/backlog_tool.py resolve BL-005 --commit abc1234 --approach "..."
```
- `--commit` 생략 시 자동 감지 시도: `git log -1 --pretty=%H` 최근 커밋
- 실행 후: backlog.json에서 제거 → resolved.json에 append → backlog.md 재생성

**dismiss**:
```bash
python3 scripts/backlog_tool.py dismiss BL-012 --reason "이미 삭제된 코드"
```
- reason은 **필수**. 생략하면 사용자에게 질문
- status를 `dismissed`로 마킹 (제거되지 않음, 히스토리 보존)

**stale-check**:
```bash
python3 scripts/backlog_tool.py stale-check
```
- open 항목 전수 스캔
- 파일 부재 → `stale` 마킹 + `stale_reason: file missing`
- 심볼 부재 → `stale_candidate: true` 플래그 (자동 stale 아님, 사용자 판단)

**import-all** (one-shot, 초기 이관용):
```bash
python3 scripts/backlog_tool.py import-all [--reviews-dir .harness/reviews]
```
- 모든 `*-review.json` 스캔 → `severity >= major` + `scope == followup`만 백로그 추가
- dedup으로 중복 병합
- **정기 실행 불필요** (자동 append가 있으므로)

**stats**:
```bash
python3 scripts/backlog_tool.py stats
```
- key=value 형식 출력 (다른 스크립트 파이프용)

### Step 3: 결과 표시

스크립트 stdout을 사용자에게 그대로 전달. 필요 시 요약 추가:

```markdown
## 백로그 현황

- 미해결: 12건 (critical 2, major 5, minor 5)
- 재발견 3회 이상: BL-001, BL-007 (우선순위 고려)
- Stale: 3건 (/review-backlog stale-check로 정리 권장)

### 다음 단계
- 상세 조회: /review-backlog list --severity critical
- 해결 처리: /review-backlog resolve BL-XXX --commit $(git rev-parse HEAD)
```

## 다른 스킬과의 연동

### /code-review
리뷰 완료 직후 자동 append:
```bash
python3 scripts/backlog_tool.py add --review-json {review.json 경로} --only-major-plus
```
`--only-major-plus`는 기본값. `severity: critical|major` + `scope: followup`만 추가.

### /code-review-walk
- `[d] 보류` 선택 시:
  ```bash
  python3 scripts/backlog_tool.py add-manual \
    --file {finding.file} --title {finding.title} \
    --severity {finding.severity} --category {finding.category} \
    --problem {finding.problem} --recommendation {finding.recommendation} \
    --symbol {finding.symbol} --lines {finding.lines} \
    --note {user_note} --source-review {review.json 경로}
  ```
- `[w] 작업` 완료 시: 해당 finding이 이미 backlog에 있으면 resolve
  ```bash
  # 사전 확인: backlog list --json으로 dedup_key 매칭
  # 매칭된 BL-XXX 있으면:
  python3 scripts/backlog_tool.py resolve BL-XXX --commit {방금_커밋_SHA} --approach {action_요약}
  ```

### /code-review-fix
- 수정된 finding과 매칭되는 backlog 항목을 자동 resolve하지 **않음** (안전)
- 대신 완료 후 안내: "수정한 finding 중 N건이 백로그에도 존재합니다. `/review-backlog list --file <파일>`로 확인 후 수동 resolve 권장."

## Dedup 동작 확인

다음 3개는 동일 이슈로 수렴 (동일 dedup_key):
```
A: "SQL injection in getUserById"   file=src/api/users.ts  symbol=getUserById
B: "getUserById SQL 주입 취약"       file=src/api/users.ts  symbol=getUserById
C: "SQL 주입"                       file=src/api/users.ts  symbol=getUserById
```

다음은 **다른 이슈**로 인식:
```
D: 다른 파일 (file=src/api/posts.ts)
E: 다른 심볼 (symbol=getPostById)
F: 심볼 없음 (symbol=null) — keyword만으로 비교되므로 제목에 따라 분리 가능
```

dedup이 과하게 묶였거나 분산된 경우 수동 조정:
- 과하게 묶임: 백로그에서 잘못 수렴된 항목은 dismiss 후 수동 re-add
- 분산: 현재 수동 병합 명령 없음 (v0.16 MVP). 필요 시 향후 `merge BL-X BL-Y` 명령 추가 예정

## 판정 기준 요약

| 상황 | 자동 처리 | 수동 처리 |
|------|----------|-----------|
| 리뷰 완료 → major/critical followup 발견 | 자동 append (/code-review가 호출) | - |
| 리뷰 완료 → minor/nit followup 발견 | 백로그 추가 **안 함** | walk에서 보류 선택 시 |
| walk에서 [d] 보류 | - | add-manual 호출 |
| walk에서 [w] 작업 완료 | dedup_key로 backlog 조회 후 해당 있으면 resolve 제안 | resolve 명령 |
| 코드 리팩토링으로 경로 변경 | - | stale-check 실행 |
| 검토 결과 무시 결정 | - | dismiss 명령 |

## 팀 공유 패턴 (선택)

팀 전체에 백로그를 보여주고 싶다면:

1. 루트 `.gitignore`에 예외 추가:
   ```
   .harness/
   !.harness/review-backlog/backlog.md
   ```
2. `/review-backlog render-md` 후 `git add .harness/review-backlog/backlog.md`
3. 정기 커밋 (매 /code-review 후 또는 주간 갱신)

JSON 원본은 개인 상태로 유지.

## 에러 핸들링

- `BL-XXX not found` → backlog.json 또는 resolved.json 확인. 이미 resolved된 항목에 resolve 재호출하면 실패 (이력 보호)
- JSON 파싱 실패 → 스크립트가 `.broken.{ts}` 접미사로 백업 후 빈 state로 초기화. 복구 필요 시 백업 파일 참조
- `.harness/review-backlog/` 없음 → 스크립트가 자동 생성
