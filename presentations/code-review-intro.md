# 다중 에이전트 코드 리뷰 하네스

> PPT 구성을 위한 핵심 컨텐츠. 각 `##` 섹션이 슬라이드 1장에 대응하도록 구성했습니다.

---

## 1. 왜 기존 코드 리뷰는 힘든가

- **1인 리뷰의 한계**: 리뷰어의 컨디션·관심 분야에 따라 편차
- **관심사 혼재**: 보안·성능·유지보수를 한 사람이 동시에 보기 어렵다
- **병목**: 리뷰 대기로 배포 지연, PR 회전율 저하
- **자동 도구의 한계**: 스타일 중심 · 맥락 부재 · false positive
- **"그때는 놓쳤다"**: 같은 유형의 버그가 반복적으로 프로덕션에 도달

핵심 질문: **다수의 독립적 관점 × 전문 분야 분리 × 확정적 검증**을 어떻게 시스템으로 만들까?

---

## 2. 솔루션 한 줄 요약

> **5명의 전문가 × 2명의 감독 × 비교 분석 = 합의 기반 리뷰 리포트**

10개의 에이전트가 병렬로 독립 리뷰 → 두 감독이 통합 → 비교 분석으로 합의율 산출 → 단일 리포트로 귀결.

Claude Code 플러그인으로 `/code-review` 한 번에 실행.

---

## 3. 아키텍처 — Fork 1회 + 내부 Spawn으로 병렬 조율

```
Main Session (thin wrapper)
  │
  └─ ⭐ Fork → cr-orchestrator (격리된 컨텍스트, 메인 타임라인에서 분기)
               │
               │  ↓ 이하는 orchestrator가 내부에서 Spawn으로 병렬 조율
               │
               ├─ Spawn → cr-supervisor-a ──┐
               │           └─ Spawn → 5 전문 에이전트 (병렬)
               ├─ Spawn → cr-supervisor-b ──┤  A/B 동시 실행
               │           └─ Spawn → 5 전문 에이전트 (병렬)
               └─ Spawn → cr-report-comparator
                           └─ 최종 리포트
```

### 용어 구분

| 경계 | 용어 | 의미 |
|------|------|------|
| Main → Orchestrator | **Fork** | 메인 대화 타임라인에서 **분기** — 메인은 오염되지 않고, 리뷰 작업은 독립 경로로 진행 |
| Orchestrator 내부 | **Spawn** | 워커 에이전트 **생성** — 병렬 실행을 위한 위임, 결과를 부모에게 반환 |

**핵심:** 격리 Fork는 Main↔Orchestrator 한 번뿐. 내부의 Spawn은 orchestrator의 병렬 실행 구현 세부사항이며, 메인 세션의 관심사가 아니다.

---

## 4. 5명의 전문가

| 에이전트 | 담당 | 주요 탐지 항목 |
|---------|------|---------------|
| **cr-correctness** | 정확성 | 로직 오류, edge case, 요구사항 정합성 |
| **cr-reliability** | 안정성 | 에러 처리, 비동기 race, timeout, null safety |
| **cr-security** | 보안 | 인증/인가, injection, 민감정보 노출, OWASP |
| **cr-performance** | 성능 | N+1, 루프 내 I/O, 메모이제이션, 메모리 누수 |
| **cr-maintainability** | 유지보수성 | SOLID, 함수 분리, 중복 코드, 변경 용이성 |

각 에이전트는 **자기 영역에만 집중**하도록 프롬프트 분리 → 교차 관심사로 인한 희석 방지.

---

## 5. 이중 감독 합의 — "Two Pass, One Truth"

**왜 Supervisor 2명?**
- 같은 diff를 서로 다른 supervisor가 **독립적으로** 리뷰 (A는 중요한 것부터, B는 놓치기 쉬운 것부터)
- 양쪽이 동일하게 지적 → **high confidence** (consensus)
- 한쪽만 지적 → **medium confidence** (unique, 검토 필요)
- 상반된 판정 → **review** (사용자 최종 판단)

**Report Comparator**: 두 결과를 매칭 휴리스틱으로 비교해 합의/고유/충돌 분류 → 합의율(%) 산출.

---

## 6. 심각도 × 범위 체계

**Severity (4단계)**
| 레벨 | 기준 |
|------|------|
| Critical | 즉시 장애·데이터 손상·RCE 수준 |
| Major | 특정 조건에서 유의미한 오동작 |
| Minor | 드문 조건·사소한 개선 |
| Nit | 취향·스타일 수준 |

**Scope (2단계)**
- `fix_now`: 이 PR에서 반드시 해결
- `followup`: 별도 작업으로 미룰 수 있음

각 finding은 `{severity} × {scope}` 매트릭스로 분류됨 → **"지금 고쳐야 하는 것"과 "나중에 볼 것"이 명확히 구분**.

---

## 7. Fork-First 설계 — 단 한 번의 Fork로 메인 컨텍스트 보호

```
❌ Before: 모든 로직이 메인 세션에서 실행
   → diff + supervisor 결과 + 리포트 = 메인 컨텍스트 폭발

✅ After: cr-orchestrator 한 번 Fork
   → 메인은 {paths, summary JSON}만 받음
   → orchestrator 내부에서 Spawn으로 병렬 조율은 자체 해결
```

**메인 세션 유지비용**:
- Before: 큰 PR 1회 리뷰로 주 컨텍스트 소진
- After: 큰 PR이어도 메인 세션은 정상 유지, 다른 작업 병행 가능

**중요:** Fork는 타임라인 분기(메인 ↔ 리뷰 작업), Spawn은 작업 내부의 병렬 워커 생성. 이 둘을 구분하는 것이 설계의 핵심.

---

## 8. 검증 가능성 — "정말 5명이 돌았나?"

과거 문제: supervisor가 에이전트를 안 띄우고 혼자 카테고리 이름만 적어내는 경우가 있었음.

**해결: Trace 로깅**
```jsonl
{"event":"supervisor_start","supervisor":"A","time":"..."}
{"event":"agent_spawn","supervisor":"A","subagent_type":"cr-correctness","time":"..."}
{"event":"agent_spawn","supervisor":"A","subagent_type":"cr-reliability","time":"..."}
...
{"event":"agent_result","supervisor":"A","subagent_type":"cr-correctness","finding_count":3}
...
{"event":"supervisor_end","supervisor":"A","spawned":5,"returned":5}
```

- 실시간: `tail -f .harness/reviews/*/*-trace.jsonl`
- 사후: orchestrator가 trace 집계 → 리포트 metadata에 `execution_trace` 포함
- **확정적 증거** — 추측이 아닌 파일 기반 검증

---

## 9. 리포트 구성 — 폴더 단위 아티팩트

```
.harness/reviews/20260420_143022-payment-integration/
  20260420_143022-payment-integration-review.md       ← 사람이 읽는 리포트
  20260420_143022-payment-integration-review.json     ← 기계가 읽는 리포트
  20260420_143022-payment-integration-trace.jsonl     ← 실행 증거
  20260420_143022-payment-integration-fix-result.md   ← (fix 실행 시)
  20260420_143022-payment-integration-walk.json       ← (walk 실행 시)
```

- **폴더명 = 타임스탬프 + 주제 slug**: 한눈에 어떤 리뷰인지 식별 (`payment-integration`, `auth-refactor` 등)
- Summary는 PR 제목/브랜치명/최빈 디렉토리로 자동 도출 → 사용자 확인
- Markdown은 팀 공유용, JSON은 자동화 연동용

---

## 10. 리포트 샘플 (Markdown)

```markdown
# Code Review Report
PR: #123 (payment-integration)
Consensus Rate: 67%
Execution Trace: Supervisor A 5/5 ✅ | Supervisor B 5/5 ✅

## Critical
### CR-001: SQL Injection via unsanitized user input
- Category: security · Confidence: high (consensus)
- File: src/api/users.ts:42-58
- Problem: ...
- Why: ...
- Impact: ...
- Recommendation: ...
- Scope: fix_now

## Major
### CR-002: 외부 API 호출에 timeout 미설정
...
```

**확인 즉시 행동으로 이어지는 구조**: 왜 문제인지 → 어떻게 고치는지 → 지금/나중 판단까지 포함.

---

## 11. 후속 워크플로우 — 리뷰만으로 끝나지 않는다

```
/code-review          → 리포트 생성
      │
      ├─ /code-review-walk    대화형 점검 (하나씩 설명·결정·커밋)
      │     - 배경·영향·장단점 설명
      │     - [w]작업 [p]패스 [d]보류 선택
      │     - 상태 저장 → 다음 실행 시 건너뜀
      │     - 수정 시 finding별 자동 커밋
      │
      └─ /code-review-fix     자동 병렬 수정
            - fix_now 항목만, 파일별 병렬 에이전트
            - 수정 후 구문 체크
            - fix-result.json으로 결과 기록
```

상황에 맞게 **대화형 심층 점검** vs **자동 일괄 수정** 선택.

---

## 12. 대화형 점검 (`/code-review-walk`) 상세

각 finding에 대해 다음을 보여주고 사용자 결정을 받음:

- **📌 배경**: 이 패턴이 왜 존재하는지, 레포 내 유사 패턴은 어떻게 처리되는지
- **🔍 발생 원인** + 실제 코드 스니펫
- **⚠️ 이슈인 이유**: 발생 가능성 / 심각도 / 복구 비용 / 관측성으로 분해
- **💡 해결 방안**: before/after 코드 예시
- **✅ 수정 시 장점**: 구체적 이득
- **⚠️ 수정 시 고려사항**: 리팩토링 범위, 트레이드오프, 체크 필요 항목
- **🔗 연관 코드**: Grep으로 찾은 유사 패턴

**결정 후 자동 커밋** (conventional commit 형식):
```
fix(review): CR-005 외부 API 호출에 timeout 미설정

AbortController로 5s timeout 추가.

Review:  .harness/reviews/20260420_.../
Finding: CR-005 (reliability/critical)
Files:   src/integrations/payment.ts
```

---

## 13. 자동 수정 (`/code-review-fix`) 상세

- `fix_now` 항목만 대상 (`followup`, `nit` 제외)
- **파일별 병렬 fix-agent 실행** — 파일 수만큼 동시 수정
- 수정 후 구문 체크 자동 실행
- 결과를 fix-result.json으로 기록 (CI/CD 연동 가능)
- `git diff`로 사용자 확인 → 커밋은 사용자 승인

---

## 14. 차별점 요약

| 항목 | 일반 리뷰 도구 | 다중 에이전트 하네스 |
|------|-------------|------------------|
| 관점 | 1인 | 5 전문가 × 2 감독 |
| 독립성 | 단일 | 이중 독립 + 합의 측정 |
| 깊이 | 스타일 중심 | 영역별 전문 프롬프트 |
| 검증 | 결과만 | Trace 로깅으로 실행 증명 |
| 후속 작업 | 리포트 생성에서 끝 | walk(대화) + fix(자동) 통합 |
| 컨텍스트 | 메인 세션 오염 | Fork-first 격리 |
| 산출물 | 단일 파일 | 폴더 단위 (리포트+trace+fix 기록) |

---

## 15. 전체 스킬 카탈로그 (연관 도구)

| 스킬 | 역할 |
|------|------|
| `/code-review` | 다중 에이전트 합의 리뷰 |
| `/code-review-fix` | fix_now 항목 병렬 자동 수정 |
| `/code-review-walk` | finding을 대화형으로 하나씩 점검·수정·커밋 |
| `/code-review-quick` | 빠른 단일 에이전트 리뷰 (가벼운 점검) |
| `/api-summary` | 작업 후 API 변경 요약 (팀 공유용) |
| `/slack-plan` · `/slack-review` | Slack List ↔ 작업 계획서 ↔ 완료 처리 |
| `/plan-execute` | 계획서 기반 병렬 구현 (ultrawork + ralph) |
| `/guide-init` · `/guide-check` · `/guide-fix` | 프로젝트 가이드 문서 생성/동기화 |

**코드리뷰는 독립 기능이지만, 리뷰→수정→Slack 보고까지 하나의 체인으로 연결 가능**.

---

## 16. 설정 · 확장성

**커스터마이징** (`.harness/code-review.json`)
```json
{
  "ignore": ["**/*.test.ts", "**/migrations/**"],
  "severity_threshold": "minor",
  "max_nits": 5
}
```

**새 전문 에이전트 추가**:
1. `agents/cr-{name}.md` 생성
2. `cr-supervisor.md`의 스폰 목록에 추가
3. 즉시 사용 가능

예: i18n 전문, a11y 전문, 데이터 스키마 전문 에이전트 추가 가능.

---

## 17. 기술 스택

- **플랫폼**: Claude Code 플러그인 (자체 제작 my-harness)
- **모델 전략**:
  - Orchestrator / Supervisor / Comparator / Maintainability: Opus (판단 난이도 높음)
  - Correctness / Reliability / Security / Performance: Sonnet (패턴 탐지)
  - quick-fix: Haiku (경량 수정)
- **병렬화**: `run_in_background: true`로 동시 실행
- **재현성**: 타임스탬프 기반 폴더, JSONL trace, 설정 파일 version 관리

---

## 18. 기대 효과

- **리뷰 회전율**: 수분 내 리뷰 리포트 완성 → 인간 리뷰어는 확정 판단에 집중
- **품질**: 5 영역 × 2 독립 리뷰로 누락 최소화, 합의율로 신뢰도 정량화
- **일관성**: 모든 PR이 같은 기준표로 평가
- **학습 자산**: finding + 배경 설명 + 자동 커밋 이력이 향후 참고 자산
- **실험 가능**: 에이전트 교체·추가·프롬프트 튜닝으로 조직 맥락에 맞춤

---

## 19. 한계와 솔직한 트레이드오프

- **토큰 비용**: 10개 에이전트 × 2회 실행 = 일반 PR 대비 토큰 많음
- **작은 PR은 과함**: 1-2파일 변경은 `/code-review-quick`이 적합
- **합의는 보조지표**: 합의율이 낮다고 finding이 틀린 것은 아님
- **LLM 한계**: 도메인 특화 룰(회사 내부 규정)은 별도 에이전트 추가 필요
- **Flaky 가능성**: LLM 특성상 동일 입력에도 결과 변동 있음 → 이중 감독으로 완화

---

## 20. 요약 슬라이드

- **이중 독립 × 5 전문가 × Fork-first 격리**로 신뢰도 높은 리뷰
- **Trace 로깅**으로 실행 증명
- **대화형 / 자동 수정 / 자동 커밋**까지 하나의 워크플로우
- **확장 가능** — 새 영역 전문가 추가 · 설정으로 커스터마이징
- 현재 v0.11.0, 주 단위 개선 중

> 코드 리뷰를 "사람이 짜내는 노동"에서 "검증 가능한 시스템"으로 전환.
