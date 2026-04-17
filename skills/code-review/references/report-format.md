# Report Format — 리뷰 결과 출력 형식

## A. Markdown 리포트

```markdown
# Code Review Report

**Date:** YYYY-MM-DD
**PR:** #{number} (또는 git diff 범위)
**Files Changed:** N
**Review Mode:** Dual-supervisor consensus

---

## Summary

| Severity | Count |
|----------|-------|
| Critical | N |
| Major    | N |
| Minor    | N |
| Nit      | N |
| **Total** | **N** |

**Consensus Rate:** N% (양쪽 감독 에이전트가 동일하게 지적한 비율)

---

## Critical Findings

### CR-001: [제목]

- **Severity:** Critical
- **Category:** correctness | reliability | security | performance | maintainability
- **File:** `src/path/to/file.ts` > `functionName` (lines 42-58)
- **Detected by:** my-harness:cr-correctness, my-harness:cr-reliability
- **Confidence:** high (consensus) | medium (unique) | review (conflict)

**Problem:**
[무엇이 문제인지 구체적으로]

**Why this matters:**
[왜 이것이 문제인지 — 실제 영향]

**Impact:**
[발생 시 어떤 결과를 초래하는지]

**Recommendation:**
[어떻게 수정하면 되는지 — 구체적 방향]

**Scope:** fix_now | followup

---

## Major Findings

### CR-002: [제목]
(동일 구조)

---

## Minor Findings

### CR-003: [제목]
(동일 구조, 간략화 가능)

---

## Nit

- `src/file.ts:15` — [간단한 제안]
- `src/other.ts:42` — [간단한 제안]

---

## Review Metadata

- **Supervisor A findings:** N
- **Supervisor B findings:** N
- **Consensus findings:** N
- **Unique to A:** N
- **Unique to B:** N
- **Conflicts resolved:** N
```

## B. JSON 리포트

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
      "title": "SQL injection via unsanitized user input",
      "severity": "critical",
      "category": "security",
      "agents": ["my-harness:cr-security"],
      "confidence": "high",
      "file": "src/api/users.ts",
      "symbol": "getUserById",
      "lines": "42-58",
      "problem": "User ID from request params is directly interpolated into SQL query string without parameterization.",
      "why": "Allows arbitrary SQL execution by manipulating the id parameter.",
      "impact": "Full database read/write access, data exfiltration, data deletion.",
      "recommendation": "Use parameterized query: db.query('SELECT * FROM users WHERE id = $1', [id])",
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
| title | string | 한 줄 요약 |
| severity | enum | `critical`, `major`, `minor`, `nit` |
| category | enum | `correctness`, `reliability`, `security`, `performance`, `maintainability` |
| agents | string[] | 이 finding을 발견한 에이전트 목록 |
| confidence | enum | `high` (consensus), `medium` (unique), `review` (conflict) |
| file | string | 파일 경로 |
| symbol | string? | 함수/클래스/메서드명 (가능하면) |
| lines | string? | 라인 범위 (가능하면) |
| problem | string | 문제 설명 |
| why | string | 왜 문제인지 |
| impact | string | 영향 |
| recommendation | string | 수정 방향 |
| scope | enum | `fix_now`, `followup` |
