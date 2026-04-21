---
name: code-review
description: "통합 다중 에이전트 코드 리뷰 하네스 (v0.15+, unified). PR/git diff/변경 파일을 입력으로 받아 Direct + Indirect 리뷰어를 병렬 spawn하고, diff 패턴으로 deep-focus 필요 카테고리를 자동 감지해 심층 전문가를 선택적으로 추가 spawn한다. Comparator가 모든 set을 합쳐 심각도 캘리브레이션 교차검증 후 최종 리포트를 생성. 코드 리뷰, PR 리뷰, diff 리뷰, 변경사항 검토, 코드 품질 검사 요청 시 이 스킬을 사용할 것."
---

# Code Review Harness — Unified (v0.15+)

다중 에이전트 코드 리뷰 스킬. **baseline (Direct + Indirect)** + **상황별 deep focus (0~3)**의 하이브리드 구조.

## 아키텍처

```
/code-review (메인 세션)
  │
  ├─ Step 1: Diff 수집 + summary 도출
  ├─ Step 2: Deep-Focus 자동 감지 (변경 파일 패턴 분석)
  │
  ├─ Step 3: Baseline 병렬 spawn (항상 2개)
  │    ├─ cr-direct-reviewer   (Lens A, 5 카테고리 통합, Opus)
  │    └─ cr-indirect-reviewer (Lens B, 4 축, Opus)
  │
  ├─ Step 4: Deep-Focus 병렬 spawn (0~3개, 감지 시)
  │    감지 카테고리 중 선택:
  │      correctness_deep     — migrations, signal/serializer 대규모 변경
  │      security_deep        — permissions, auth, jwt, SSRF 관련
  │      reliability_deep     — tasks.py, cron.py, workers
  │      performance_deep     — annotate/Subquery 체인, 대량 인덱스 변경
  │      maintainability_deep — views/serializers 대규모 리팩토링
  │
  └─ Step 5: cr-report-comparator (Opus)
       3~6개 set 통합 + 심각도 캘리브레이션 교차검증 + 최종 리포트 파일 작성
```

**spawn 수:** 최소 3 (단순 PR) ~ 최대 7 (Deep 3개 포함).

**꼼꼼함 (v0.15+ 엄격):** 모든 Critical/Major finding은 `reproduction`, `verification`, `reasoning` (severity-guide 기준 인용) 필수.

## 사용법

```
/code-review                          # git diff main...HEAD 자동 사용
/code-review #123                     # PR 번호
/code-review main..feature-branch     # diff 범위 지정
/code-review src/api/ src/models/     # 특정 디렉토리
```

## 실행 흐름

### Step 1: 입력 수집 및 diff 준비

사용자 인자를 파싱해 diff를 수집한다.

- 인자 없음 → `git diff main...HEAD`
- PR 번호 (`#123`) → `gh pr diff 123`
- diff 범위 (`A..B`) → `git diff A..B`
- 파일/디렉토리 경로 → `git diff -- <paths>`

`.harness/code-review.json`이 존재하면 `ignore` 패턴을 diff 수집에 적용.

### Step 1.5: Summary 도출 및 폴더 초기화

```bash
TS=$(date "+%Y%m%d_%H%M%S")
SUM="<도출된 slug>"  # PR title / branch name / common dir / commit keyword / "review"
BASE=".harness/reviews/${TS}-${SUM}"
mkdir -p "$BASE"
PREFIX="${BASE}/${TS}-${SUM}"
TRACE="${PREFIX}-trace.jsonl"

echo "{\"event\":\"skill_start\",\"variant\":\"unified\",\"time\":\"$(date -Iseconds)\",\"summary\":\"${SUM}\",\"scope\":\"<scope>\"}" > "$TRACE"
```

### Step 2: Deep-Focus 자동 감지

변경 파일 목록을 스캔해 심층 리뷰가 필요한 카테고리를 결정. **최대 3개까지** 선택하여 비용 폭주 방지.

**감지 규칙 (우선순위 순):**

| 패턴 | Deep Focus | 근거 |
|------|-----------|------|
| `migrations/*.py` 파일 **변경 또는 추가** | `correctness` | 필드 타입 변경, RunPython 누락, 제약 변경은 데이터 손상 리스크 |
| `permissions.py`, `auth*.py`, `jwt*.py`, SSRF·URL 검증 코드 변경 | `security` | 인증/인가/신뢰 경계 영향 |
| `tasks.py`, `workers.py`, `cron.py`, Celery 데코레이터 포함 파일 | `reliability` | 재시도·트랜잭션·비동기 경로 |
| `models.py`에 인덱스/annotate 관련 변경, views의 `annotate/Subquery` 다중 | `performance` | ORM 사이드이펙트 + 쿼리 cost |
| `serializers.py` + `views.py` 합산 500 라인 이상 변경 | `maintainability` | 대규모 구조 변경 |

```bash
# 자동 감지 의사코드
deep_focus=[]
CHANGED_FILES=$(git diff --name-only <scope>)

# migrations 패턴
echo "$CHANGED_FILES" | grep -q 'migrations/.*\.py$' && deep_focus+=("correctness")

# permissions/auth/jwt 패턴
echo "$CHANGED_FILES" | grep -qE '(permissions|auth|jwt|security)\.py$' && deep_focus+=("security")
# SSRF/URL validation 패턴 (tasks/services에서 URL 검증 함수 변경)
git diff <scope> -- '*.py' | grep -qE '(validate_url|safe_http_get|SSRF|PinnedHTTPAdapter)' && \
  [[ ! " ${deep_focus[@]} " =~ "security" ]] && deep_focus+=("security")

# tasks/cron/workers
echo "$CHANGED_FILES" | grep -qE '(tasks|cron|workers)\.py$' && deep_focus+=("reliability")

# performance: annotate/Subquery 다중
git diff <scope> -- '*.py' | grep -cE '(annotate|Subquery|Prefetch|only\(|defer\()' | awk '$1>=5{exit 0}{exit 1}' \
  && deep_focus+=("performance")

# maintainability: 대규모 구조 변경
lines_changed=$(git diff --numstat <scope> -- '*serializers.py' '*views.py' | awk '{s+=$1+$2} END {print s}')
[[ ${lines_changed:-0} -ge 500 ]] && deep_focus+=("maintainability")

# 최대 3개로 제한 (우선순위: correctness > security > reliability > performance > maintainability)
deep_focus=("${deep_focus[@]:0:3}")
```

감지 결과를 trace에 기록:

```bash
echo "{\"event\":\"deep_focus_detected\",\"categories\":$(echo -n "${deep_focus[@]}" | jq -R -s -c 'split(" ")'),\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

사용자에게 짧게 알림: "Deep Focus: correctness, security (2개 카테고리 심층 리뷰 추가)"

### Step 3: Baseline Spawn (Direct + Indirect, 병렬)

**한 응답에서 2개 Agent 호출을 모두 포함.** 둘 다 `run_in_background: true`. 각 spawn 직전에 trace 기록.

```bash
echo "{\"event\":\"agent_spawn\",\"agent\":\"cr-direct-reviewer\",\"lens\":\"A\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
echo "{\"event\":\"agent_spawn\",\"agent\":\"cr-indirect-reviewer\",\"lens\":\"B\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

```
Agent(
  subagent_type: "my-harness:cr-direct-reviewer",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 diff를 5개 카테고리(correctness, reliability, security, performance, maintainability) 전체 체크리스트로 **정밀 리뷰**하라.

[출력 언어] 자연어 필드는 한글.
[엄격도] Critical/Major는 반드시 reproduction, verification, reasoning(severity-guide 기준 인용) 포함.
[범위] diff 전체 파일을 1회 이상 훑고, migrations/signals/permissions/cron/settings는 명시적 점검.
[positive_notes] 설계 잘 된 부분 3~5개 기록.

{diff 전문}

결과를 JSON으로 반환: { findings: [...], positive_notes: [...] }
id prefix는 DR-{NNN}.
"""
)

Agent(
  subagent_type: "my-harness:cr-indirect-reviewer",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 diff를 4개 축(데코레이터-예외 경로 상호작용, 언어 관용구 함정, future-risk, 계약·스키마 일관성)으로 **정밀 리뷰**하라. cr-direct-reviewer가 잡을 만한 표면 이슈는 의도적으로 패스.

[출력 언어] 자연어 필드는 한글.
[엄격도] Critical/Major는 reproduction/verification/reasoning 필수. future-risk는 구체적 확장 시나리오 1개 제시.
[축 명시] 각 finding에 axis 필드 필수.

{diff 전문}

결과를 JSON으로 반환: { findings: [...] }
id prefix는 IR-{NNN}.
"""
)
```

### Step 4: Deep-Focus Spawn (조건부, 병렬)

Step 2에서 감지된 카테고리가 있으면 해당 수만큼 병렬 spawn. 없으면 스킵.

각 spawn 직전 trace 기록:

```bash
for cat in "${deep_focus[@]}"; do
  echo "{\"event\":\"agent_spawn\",\"agent\":\"cr-${cat}\",\"mode\":\"deep\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
done
```

```
# 예: correctness 심층이 필요한 경우
Agent(
  subagent_type: "my-harness:cr-correctness",
  model: "sonnet",  # 심층 카테고리 전문가는 Sonnet이 충분
  run_in_background: true,
  prompt: """
Mode: deep

아래 diff를 **correctness 전문 관점에서 심층 리뷰**하라. cr-direct/cr-indirect가 이미 baseline을 수행했으므로, 당신은 이 카테고리의 **세부 체크리스트를 깊이 있게** 적용한다.

특히 이번 변경에서 다음을 중점 확인:
- migrations 파일의 필드 타입 변경, RunPython 누락, 제약 호환성
- serializer-model 일관성 (없는 필드 선언, read_only/write_only 오용)
- camelCase/snake_case 전환 타이밍 오류
- edge case 누락 (empty, null, boundary)

[출력 언어] 한글.
[엄격도] Critical/Major reproduction/verification/reasoning 필수.

{diff 전문}

결과 JSON: { findings: [...] }
id prefix는 CR-COR-{NNN}.
"""
)

# security, reliability, performance, maintainability도 동일 패턴으로 심층 지시
```

카테고리별 "중점 확인" 가이드:

- **security_deep**: 인증/인가 경로, SSRF/URL 검증, 역직렬화 체인, 비밀 노출, 스키마 검증 누락
- **reliability_deep**: retry/autoretry + try/except 상호작용, timeout, idempotency, 트랜잭션 경계, shutdown handling
- **performance_deep**: N+1, annotate/Subquery cost, ORM 사이드이펙트, 인덱스 누락, 캐시 miss 경로
- **maintainability_deep**: SRP 위반, 결합도, 산탄총 수술, 테스트 불가능 구조, 중복 코드

### Step 5: 결과 수집 + 캘리브레이션 교차 검증 (Comparator)

모든 에이전트 완료 대기. 각 완료 시 `agent_result` 기록.

모든 findings를 Comparator에 전달:

```bash
echo "{\"event\":\"comparator_start\",\"input_sets\":<N>,\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
```

```
Agent(
  subagent_type: "my-harness:cr-report-comparator",
  model: "opus",
  run_in_background: true,
  prompt: """
아래 리뷰 set들을 통합 분석하라.

[출력 언어] 한글.

Direct set (cr-direct-reviewer, Lens A):
  findings: {direct_findings JSON}
  positive_notes: {direct_positive JSON}

Indirect set (cr-indirect-reviewer, Lens B):
  findings: {indirect_findings JSON}

Deep-Focus sets:
  {조건부: correctness_deep: {...}, security_deep: {...}, ...}

[작업]
1. 합의 매칭 휴리스틱으로 합의/고유/충돌 분류
2. 심각도 캘리브레이션 교차 검증 (agents/cr-report-comparator.md 규칙 1-5 엄격 적용)
3. 근본 원인 테마 식별 (2개 이상 finding이 공통 원인 공유 시 theme으로 묶기)
4. 최종 리포트를 아래 두 파일에 직접 Write:
   - Markdown: {review_md 절대 경로}
   - JSON:     {review_json 절대 경로}
5. 완료 후 요약 JSON만 반환.

review.json의 metadata:
  variant: "unified"
  agents_run: ["direct", "indirect", {deep_focus 목록}]
  deep_focus_detected: {deep_focus 배열}

출력 형식: references/report-format.md 참조.
심각도 기준: references/severity-guide.md 참조.
"""
)
```

완료 후:

```bash
echo "{\"event\":\"comparator_end\",\"time\":\"$(date -Iseconds)\"}" >> "$TRACE"
echo "{\"event\":\"skill_end\",\"variant\":\"unified\",\"time\":\"$(date -Iseconds)\",\"findings\":N}" >> "$TRACE"
```

### Step 6: Trace 검증

```bash
expected_spawn=$((2 + ${#deep_focus[@]} + 1))  # Direct + Indirect + Deep + Comparator
actual_spawn=$(grep -c '"event":"agent_spawn"' "$TRACE")
[[ $actual_spawn -eq $expected_spawn ]] && echo "OK" || echo "WARN: expected $expected_spawn, got $actual_spawn"

grep '"event":"spawn_unavailable"' "$TRACE" && echo "WARN: fallback triggered" || true
```

### Step 6.5: 백로그 자동 Append (major+ followup만)

리뷰 완료 후 `scope: followup` + `severity ≥ major` 항목을 **중앙 백로그에 자동 append**한다. dedup key로 이전 리뷰에서 이미 잡힌 이슈는 `occurrence_count`만 증가시키므로 중복 걱정 없음.

```bash
python3 scripts/backlog_tool.py add --review-json "${PREFIX}-review.json" --only-major-plus
# → stdout: [backlog] added=N updated=M total_open=K
```

출력의 `added`와 `updated`를 Step 7 요약에 포함.

**append 정책:**
- severity `critical` / `major` + `scope: followup` → 자동 추가
- `minor` / `nit` → 추가 안 함 (노이즈 방지). 필요하면 `/code-review-walk`에서 [d] 보류 선택 시만 추가됨
- `fix_now` → 지금 수정해야 하므로 백로그 제외 (별도 해결 경로)

**스크립트 실패 시:** 리뷰 자체는 성공으로 처리하고 경고만 표시. 백로그 append 실패가 리뷰 완료를 막지 않는다.

### Step 7: 최종 요약 출력

```markdown
## Code Review 완료

- 리포트: `.harness/reviews/20260420_143022-payment-integration/20260420_143022-payment-integration-review.md`
- 구성: Direct + Indirect + Deep Focus [security, reliability]
- 발견: Critical 1, Major 4, Minor 5, Nit 2 (총 12건)
- 합의율: 67%, 고유 발견: Direct 2건 / Indirect 4건 / Deep 3건
- Execution Trace: 5 spawn / 5 return ✅
- Top 3 우선순위: CR-001, CR-004, CR-007 (executive summary 참조)
- 백로그: 신규 3건 추가, 재발견 1건 (open 총 N건) → `/review-backlog` 으로 확인

### 다음 단계
- 리포트 검토: 위 경로
- 자동 수정: `/code-review-fix`
- 대화형 점검: `/code-review-walk`
- 백로그 관리: `/review-backlog`
```

`validation_warnings`가 있으면 상단에 경고 배너.

## 설정

### ignore 정책

`.harness/code-review.json`:

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
  "max_nits": 5,
  "deep_focus": {
    "max_categories": 3,
    "force": []
  }
}
```

- `ignore`: 리뷰 제외 파일 패턴
- `severity_threshold`: 이 레벨 미만 리포트 제외 (기본: 모두 포함)
- `max_nits`: Nit 최대 개수 (기본: 제한 없음)
- `deep_focus.max_categories`: Deep focus spawn 상한 (기본 3)
- `deep_focus.force`: 자동 감지와 무관하게 항상 deep 추가할 카테고리 (예: `["security"]`)

## 아키텍처 히스토리

| 버전 | 구조 | spawn 수 | 특징 |
|------|------|---------|------|
| v0.12.x | Main → Orchestrator → Supervisor → Experts (3단계 중첩) | N/A | Claude Code 미지원으로 in-context fallback 회귀 |
| v0.13.x | Main → 5 experts × Lens A/B + Comparator (flat) | 11 | 독립 spawn 작동하나 category 분할의 효용 낮음 |
| v0.14.x | `/code-review` (flat) + `/code-review-slim` (3-agent) 병렬 제공 | 11 / 3 | 측정용 duplicate |
| **v0.15+** | **Unified: Direct + Indirect + Deep(0~3) + Comparator** | **3~7** | 단일 스킬. 꼼꼼함 강화. 자동 deep focus. |

## 참조 문서

- [`references/severity-guide.md`](references/severity-guide.md) — 엄격 심각도 루브릭 + 캘리브레이션 체크리스트
- [`references/report-format.md`](references/report-format.md) — 출력 형식 상세 (reproduction/verification/reasoning 필수 필드)
- [`references/maintainability-rules.md`](references/maintainability-rules.md) — 유지보수성 판정 규칙
- [`agents/cr-direct-reviewer.md`](../../agents/cr-direct-reviewer.md) — Lens A baseline 통합 리뷰어
- [`agents/cr-indirect-reviewer.md`](../../agents/cr-indirect-reviewer.md) — Lens B 4축 리뷰어
- [`agents/cr-{correctness,reliability,security,performance,maintainability}.md`](../../agents/) — Deep-Focus 전문가
- [`agents/cr-report-comparator.md`](../../agents/cr-report-comparator.md) — 통합 + 캘리브레이션 + 파일 작성
