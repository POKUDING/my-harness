# Report Format — 리뷰 결과 출력 형식

> **언어 규칙:** 모든 리포트(Markdown · JSON의 자연어 필드)는 **한글**로 작성한다. 코드·식별자·파일 경로·명령어는 원문을 유지한다. 기술 용어(예: race condition, injection)는 필요 시 한글 병기(예: "경쟁 상태(race condition)").

## A. Markdown 리포트

```markdown
# 코드 리뷰 리포트

**일자:** YYYY-MM-DD
**PR / 범위:** #{number} (또는 git diff 범위)
**변경 파일 수:** N
**리뷰 모드:** 이중 감독 합의 (dual-supervisor consensus)

---

## 요약

| 심각도 | 건수 |
|--------|------|
| Critical | N |
| Major    | N |
| Minor    | N |
| Nit      | N |
| **합계** | **N** |

**합의율:** N% (양쪽 감독 에이전트가 동일하게 지적한 비율)

---

## Agent Execution Trace

- **Supervisor A:** N spawned / N returned — 카테고리: correctness, reliability, security, performance, maintainability
- **Supervisor B:** N spawned / N returned — 동일 카테고리
- **Comparator:** A {N}건 + B {N}건 → 병합 {N}건 (합의 {N} / A 고유 {N} / B 고유 {N})

Trace 파일: `.harness/reviews/{TS}-{SUM}/{TS}-{SUM}-trace.jsonl`

---

## Critical

### CR-001 — [제목]

- **파일:** `src/path/to/file.ts` > `functionName` (lines 42-58)
- **카테고리:** correctness | reliability | security | performance | maintainability
- **탐지 에이전트:** my-harness:cr-correctness, my-harness:cr-reliability
- **신뢰도:** high (consensus) | medium (unique) | review (conflict)

**문제.** [무엇이 문제인지 구체적으로]

**영향.** [발생 시 어떤 결과를 초래하는지 — 사용자/시스템 관점]

**원인.** [왜 이것이 문제인지 — 기술적 배경]

**권장 조치.** [어떻게 수정하면 되는지 — 구체적 방향]

**범위:** fix_now | followup

---

## Major

### CR-002 — [제목]
(동일 구조)

---

## Minor

### CR-003 — [제목]
(동일 구조, 간략화 가능)

---

## Nit

- `src/file.ts:15` — [간단한 제안]
- `src/other.ts:42` — [간단한 제안]

---

## 리뷰 메타데이터

- **Supervisor A findings:** N
- **Supervisor B findings:** N
- **합의 findings:** N
- **A 고유:** N
- **B 고유:** N
- **충돌 해소:** N
```

## B. JSON 리포트

자연어 필드(`title`, `problem`, `why`, `impact`, `recommendation`)는 모두 한글로 작성한다. `id`, `severity`, `category`, `scope`, `file`, `symbol`, `lines` 등 enum·식별자 필드는 영문 소문자를 유지한다.

```json
{
  "metadata": {
    "date": "YYYY-MM-DD",
    "pr": "#123",
    "files_changed": 5,
    "review_mode": "dual-supervisor-consensus"
  },
  "summary": {
    "total": 12,
    "critical": 1,
    "major": 4,
    "minor": 5,
    "nit": 2,
    "consensus_rate": 0.75
  },
  "findings": [
    {
      "id": "CR-001",
      "title": "사용자 입력을 정제하지 않은 SQL 질의 주입",
      "severity": "critical",
      "category": "security",
      "agents": ["my-harness:cr-security"],
      "confidence": "high",
      "file": "src/api/users.ts",
      "symbol": "getUserById",
      "lines": "42-58",
      "problem": "request params의 user id가 문자열 보간으로 SQL 질의에 직접 삽입됨. 파라미터 바인딩이 없음.",
      "why": "임의의 SQL 실행이 가능. id 값을 조작하면 의도하지 않은 쿼리가 수행됨.",
      "impact": "DB 전체 읽기/쓰기, 데이터 유출, 데이터 파괴 가능.",
      "recommendation": "파라미터화 쿼리로 변경: db.query('SELECT * FROM users WHERE id = $1', [id])",
      "scope": "fix_now"
    }
  ],
  "review_stats": {
    "supervisor_a_findings": 8,
    "supervisor_b_findings": 10,
    "consensus": 6,
    "unique_a": 2,
    "unique_b": 4,
    "conflicts_resolved": 1
  }
}
```

## 필드 명세

| 필드 | 타입 | 설명 |
|------|------|------|
| id | string | `CR-{NNN}` 형식, 보고서 내 고유 |
| title | string | 한 줄 요약 (한글) |
| severity | enum | `critical`, `major`, `minor`, `nit` |
| category | enum | `correctness`, `reliability`, `security`, `performance`, `maintainability` |
| agents | string[] | 이 finding을 발견한 에이전트 목록 |
| confidence | enum | `high` (consensus), `medium` (unique), `review` (conflict) |
| file | string | 파일 경로 |
| symbol | string? | 함수/클래스/메서드명 (가능하면) |
| lines | string? | 라인 범위 (가능하면) |
| problem | string | 문제 설명 (한글) |
| why | string | 왜 문제인지 (한글) |
| impact | string | 영향 (한글) |
| recommendation | string | 수정 방향 (한글) |
| scope | enum | `fix_now`, `followup` |
