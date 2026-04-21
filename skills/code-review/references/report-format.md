# Report Format — 리뷰 결과 출력 형식 (v0.15+)

> **언어 규칙:** 모든 리포트(Markdown · JSON의 자연어 필드)는 **한글**로 작성한다. 코드·식별자·파일 경로·명령어는 원문을 유지. enum 값은 영문 소문자. 기술 용어(예: race condition, injection)는 필요 시 한글 병기.

> **엄격도 (v0.15+):** 모든 finding은 **재현 시나리오**와 **검증 방법**을 포함해야 하며, severity는 `severity-guide.md`의 캘리브레이션 체크리스트 결과를 `reasoning` 필드에 인용해야 한다.

---

## A. Markdown 리포트

```markdown
# 코드 리뷰 리포트

**일자:** YYYY-MM-DD
**PR / 범위:** #{number} (또는 git diff 범위)
**변경 파일 수:** N
**리뷰 구성:** Direct (Lens A) + Indirect (Lens B) + Deep Focus [{도메인 목록}] + Comparator
**Variant:** unified (v0.15+)

---

## 실행 요약 (Executive Summary)

**Top 3 우선순위 (즉시 조치):**
1. **CR-XXX**: (한 줄 요약 — 파일:라인, 영향)
2. ...
3. ...

**핵심 리스크 주제:**
- {테마 1}: 관련 finding CR-A, CR-B, CR-C → 공통 원인 서술
- {테마 2}: ...

**합의 신뢰도:** Critical/Major의 N% 가 multi-agent 합의 (high confidence)

---

## 요약 통계

| 심각도 | 건수 | fix_now | followup |
|--------|------|---------|----------|
| Critical | N | N | N |
| Major    | N | N | N |
| Minor    | N | N | N |
| Nit      | N | - | - |
| **합계** | **N** | **N** | **N** |

**합의율:** A/B consensus 기준 N% (Direct·Indirect 양쪽 지적)
**Deep Focus 기여율:** Deep 에이전트가 추가로 발견한 finding N건

---

## Agent Execution Trace

| Agent | Role | Findings | Status |
|-------|------|----------|--------|
| cr-direct-reviewer | Lens A (baseline 5 카테고리) | N | ✅ |
| cr-indirect-reviewer | Lens B (4 축) | N | ✅ |
| cr-correctness (deep) | correctness 심층 | N | ✅ (조건부) |
| ... |

Trace 파일: `.harness/reviews/{TS}-{SUM}/{TS}-{SUM}-trace.jsonl`

---

## Critical

### CR-001 — [제목]

- **파일:** `src/path/to/file.ts` > `functionName` (lines 42-58)
- **카테고리:** correctness | reliability | security | performance | maintainability
- **탐지:** cr-direct-reviewer, cr-indirect-reviewer, cr-correctness-deep (합의 N 중 M)
- **신뢰도:** high (consensus) | medium (unique) | review (conflict)
- **범위:** fix_now | followup

**문제.** [무엇이 문제인지 구체적으로. 모호한 추측 금지.]

**발생 조건 (재현 시나리오).** [어떤 입력·환경·순서에서 이 문제가 실제로 발생하는지 단계적으로 서술. Critical은 1개 이상, Major는 최소 1개 필수.]

예시:
> 1. 사용자 A가 POST /v1/info-channels/posts로 URL이 포함된 post 생성
> 2. fetch_og_preview가 DB 충돌로 IntegrityError 발생
> 3. 본문 `except Exception: log_and_return()`이 해당 예외를 삼킴
> 4. autoretry_for 데코레이터 트리거되지 않음 → 영구 미리보기 없음

**영향.** [발생 시 사용자·시스템·팀이 받는 구체적 결과. "문제가 된다" 같은 모호 표현 금지.]

**원인 (왜 문제인가).** [기술적 배경. 언어/프레임워크 메커니즘 언급.]

**권장 조치.** [구체적 수정 방향. 가능하면 before/after 코드 스니펫.]

```python
# Before
try:
    ...
except Exception as e:
    log_and_return()

# After
try:
    ...
except IntegrityError:
    raise  # let autoretry_for handle
except OgFetchError as e:
    ...
```

**검증 방법 (Verification).** [수정 후 이 finding이 해결됐는지 어떻게 확인하는가. **경량에서 무거운 순**으로 우선순위: 수동 재현 → 로그/메트릭 관찰 → 기존 테스트 보강 → (최후 선택) 신규 테스트 파일. 신규 테스트는 회귀 위험이 매우 높거나 이미 관련 테스트 파일이 있을 때만 권장.]

예시 (택일 또는 조합):
> - **수동 재현**: 로컬에서 동일 URL로 POST 2회 동시 요청 → Celery worker 로그에 `IntegrityError ... retrying` 출력 확인 (5분 소요)
> - **로그 확인**: `celery worker`에서 `Task X raised ... IntegrityError ... retrying (0/3)` 메시지 관찰
> - **Metric**: `celery.retries` 카운터 증가 확인 (스테이징에서 5분 관찰)
> - **기존 테스트 보강**: `test_fetch_og_preview_failure_paths`에 "IntegrityError 케이스" assertion 1줄 추가
> - **신규 테스트 (선택)**: 프로젝트가 테스트 중심 문화면 `test_integrity_error_triggers_autoretry` 추가 — mock으로 IntegrityError 주입 후 `self.retry` 호출 확인

**관련 Finding (선택).** CR-002 (camelCase 키), CR-009 (URL 정규화 누락) — 이들과 결합 시 효과 증폭.

**severity 판정 근거 (reasoning).** severity-guide Critical 기준 중 **"핵심 기능의 silent dead code"** 해당. autoretry 선언이 있지만 실행 경로가 never triggered → 설계된 복구 메커니즘 무력화.

---

## Major

### CR-002 — [제목]
(동일 구조. Critical 수준 상세도를 유지하되 재현 시나리오는 1개 필수)

---

## Minor

### CR-003 — [제목]
(재현·검증은 선택이지만 문제·영향·권장은 필수)

---

## Nit

- `src/file.ts:15` — [간단한 제안]
- `src/other.ts:42` — [간단한 제안]

---

## 리뷰 메타데이터

- **입력 findings 총합**: N (Direct: N, Indirect: N, Deep: N)
- **중복 제거 후 최종**: N (dedup rate: X%)
- **Consensus (2+ 에이전트 합의)**: N
- **Direct-only**: N
- **Indirect-only**: N
- **Deep-only**: N
- **충돌 해소**: N (severity downgrade: N, recommendation 병합: N)

### Drop된 findings
- (근거와 함께 제외된 finding 목록 — 중복·근거 부족·out of scope 등)

### 권장 작업 순서
1. Day 1: {Critical/Major 중 동일 파일 클러스터} — 동시 수정 효율
2. Day 2: {다음 클러스터}
3. ...
4. CI 보강: {검증 파이프라인 개선}
```

---

## B. JSON 리포트

자연어 필드(`title`, `problem`, `impact`, `why`, `recommendation`, `reproduction`, `verification`, `reasoning`)는 모두 한글. enum 값·식별자·경로는 원문.

```json
{
  "metadata": {
    "date": "YYYY-MM-DD",
    "pr": "#123",
    "scope": "main...HEAD",
    "files_changed": 5,
    "variant": "unified",
    "agents_run": ["direct", "indirect", "correctness_deep", "security_deep"],
    "deep_focus_detected": ["correctness", "security"]
  },
  "summary": {
    "total": 12,
    "critical": 1,
    "major": 4,
    "minor": 5,
    "nit": 2,
    "fix_now": 8,
    "followup": 4,
    "consensus_rate": 0.75,
    "top_priorities": ["CR-001", "CR-002", "CR-005"]
  },
  "themes": [
    {
      "title": "OG-preview safety-net 전면 붕괴",
      "findings": ["CR-001", "CR-002", "CR-003"],
      "root_cause": "URL 필드 부재 + camelCase 키 혼동 + fresh_og 정규화 누락의 3중 결함"
    }
  ],
  "findings": [
    {
      "id": "CR-001",
      "title": "사용자 입력을 정제하지 않은 SQL 질의 주입",
      "severity": "critical",
      "category": "security",
      "agents": ["direct", "security_deep"],
      "confidence": "high",
      "file": "src/api/users.ts",
      "symbol": "getUserById",
      "lines": "42-58",
      "problem": "request params의 user id가 문자열 보간으로 SQL 질의에 직접 삽입됨. 파라미터 바인딩 없음.",
      "reproduction": "1. 공격자가 id=1; DROP TABLE users-- 전송 2. db.query(`SELECT * FROM users WHERE id = ${id}`) 실행 3. users 테이블 드롭",
      "impact": "DB 전체 읽기/쓰기, 데이터 유출, 데이터 파괴.",
      "why": "문자열 보간은 sanitization 없이 임의 SQL 토큰을 허용. ORM/prepared statement 우회.",
      "recommendation": "파라미터화 쿼리: db.query('SELECT * FROM users WHERE id = $1', [id])",
      "recommendation_code": {
        "before": "const user = await db.query(`SELECT * FROM users WHERE id = ${id}`);",
        "after": "const user = await db.query('SELECT * FROM users WHERE id = $1', [id]);"
      },
      "verification": "수동 재현: SQLi 페이로드(`1 OR 1=1`) 전송 후 의도한 파라미터 바인딩으로만 쿼리 실행되는지 DB 로그 확인. 선택: Snyk/semgrep 정적 분석, 기존 getUserById 테스트에 케이스 추가.",
      "scope": "fix_now",
      "reasoning": "severity-guide Critical 기준: 'RCE / 임의 SQL 실행' 해당. 공격자 인증 불필요."
    }
  ],
  "review_stats": {
    "direct_findings": 8,
    "indirect_findings": 10,
    "deep_findings_by_agent": {
      "correctness": 5,
      "security": 3
    },
    "consensus": 6,
    "direct_only": 2,
    "indirect_only": 4,
    "deep_only": 3,
    "conflicts_resolved": 1,
    "severity_downgrades": 2
  }
}
```

---

## 필드 명세

### 필수 필드 (모든 finding)

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `CR-{NNN}` 형식, 보고서 내 고유 |
| title | string | 한 줄 요약 (한글) |
| severity | enum | `critical`, `major`, `minor`, `nit` |
| category | enum | `correctness`, `reliability`, `security`, `performance`, `maintainability` |
| agents | string[] | 이 finding을 발견한 에이전트 (`direct`, `indirect`, `correctness_deep` 등) |
| confidence | enum | `high` (2+ 합의), `medium` (단일 탐지), `review` (충돌) |
| file | string | 파일 경로 |
| problem | string | 문제 설명 (한글) |
| impact | string | 영향 (한글) |
| recommendation | string | 수정 방향 (한글) |
| scope | enum | `fix_now`, `followup` |
| reasoning | string | severity 판정 근거 (severity-guide 기준 인용) |

### 심각도별 추가 필수

| 필드 | Critical | Major | Minor | Nit |
|------|---------|-------|-------|-----|
| reproduction | **필수** | **필수** | 선택 | - |
| verification | **필수** | **필수** | 선택 | - |
| recommendation_code | **필수** | 권장 | 선택 | - |
| why | **필수** | **필수** | 권장 | - |

### 선택 필드

| 필드 | 설명 |
|------|------|
| symbol | 함수/클래스/메서드명 |
| lines | 라인 범위 |
| related | 관련 finding id 배열 (테마·의존성) |
| axis | Lens B의 축: `decorator_exception_interaction`, `language_idiom_traps`, `future_risk`, `contract_schema_consistency` |
