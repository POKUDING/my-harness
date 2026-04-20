# Severity Guide — 심각도 판정 기준 (v0.15+)

**원칙:** 심각도는 **감정·의도가 아니라 관찰 가능한 영향**으로 판정한다. "중요해 보인다" 금지. "어떤 조건에서 무슨 일이 벌어지는가"를 구체화할 수 있는 경우에만 등급 부여.

---

## Critical

**정의:** 현재 또는 합리적으로 예상되는 즉각적 환경에서 아래 중 하나 이상을 발생시킨다.

**반드시 해당해야 함 (하나 이상):**
- **데이터 손실/손상**: 기존 DB 레코드가 깨지거나 삭제되거나 잘못된 값으로 덮어써짐 (예: `URLField → ImageField` 타입 변경에 RunPython 없음 → 기존 URL이 storage prefix와 결합되어 깨짐)
- **서비스 전면 장애**: 무한 루프, OOM 직결, 주요 API가 모든 요청에 500 반환
- **인증/인가 완전 우회**: 우회 조건이 복잡한 전제 없이 간단히 만족되는 경우
- **RCE / 임의 SQL 실행**: 사용자 입력이 eval/exec/raw-SQL에 주입
- **핵심 기능의 silent dead code**: 설계 의도된 경로가 **절대 실행되지 않음** (예: model 필드 부재로 직렬화된 값이 항상 None → safety-net이 dead)
- **결제·금액·권한 같은 외부에 금전적·법적 영향 있는 오류**

**Critical 판정 전 자문:**
- "이게 production에서 일어나면 on-call이 깨어날 사안인가?" → Yes 면 Critical
- "어떤 전제 조건 몇 개가 맞아야 발생하는가?" → 3개 이상이면 Major로 강등 고려

---

## Major

**정의:** 특정 조건에서 유의미한 오동작·리스크·비용을 초래한다. 프로덕션에서 언젠가 터지거나, 구조적 부채로 다음 변경을 어렵게 만든다.

**전형적 해당:**
- 조건부 오동작 (특정 입력·환경·동시성 상황에서 버그)
- 데이터 정합성 일시 깨짐 + 자동/수동 복구 경로 있음
- 보안 취약점 + 선결 조건 필요 (예: 인증된 공격자, 특정 URL 제공 등)
- 성능 저하가 사용자 체감 수준
- race condition + 사용자 영향
- 재시도/retry 선언이 실제로는 무력화되는 구조 (데코레이터-예외 경로)
- SSRF 우회 + 특정 프로토콜/IP 대역 조건
- SRP 중대한 위반, 핵심 중복 로직
- 계약 모호성 (빈 응답 vs 에러) — 클라이언트가 잘못 해석 가능

**Major 판정 전 자문:**
- "impact·why·recommendation을 **구체적 시나리오 1개 이상**으로 서술할 수 있는가?" → No 면 Minor
- "실제로 이 경로가 production 트래픽에서 trigger 가능한가?" → No 면 followup으로 강등

---

## Minor

**정의:** 개선하면 품질 향상이지만 즉각 위험 낮음.

**전형적 해당:**
- 극히 드문 edge case (예: 100만 건 중 1건)
- 경미한 네이밍/가독성
- 관측성 회귀 (auto_now 우회로 updated_at 누락 등 — 디버깅 비용↑)
- 2곳 미만 중복
- 향후 확장 시 깨질 패턴인데 현재는 안전 (future-risk 대부분)
- 에러 메시지 개선
- 작은 성능 최적화 (현재 규모 영향 미미)

---

## Nit

취향·스타일. 팀 컨벤션에 따라 무시 가능.

- 변수명 선호도
- 공백·정렬
- import 순서
- 주석 유무

---

## 심각도 캘리브레이션 체크리스트 (리뷰어 필수)

모든 finding 제출 전에 **반드시** 다음을 자문하고 answer를 `reasoning` 필드에 짧게 기록:

1. **관찰 가능한 영향이 있는가?** (아니면 Minor로 강등)
2. **특정 재현 시나리오 1개를 서술 가능한가?** (아니면 Minor로 강등)
3. **Critical이라면: 위 7개 기준 중 어느 것에 해당하는가?** (해당 없으면 Major로 강등)
4. **Major라면: 단일 시나리오인가 다중 시나리오인가?** (단일 + 낮은 확률이면 Minor 재검토)

## Cross-review 캘리브레이션 (Comparator 전담)

Direct와 Indirect(+ Deep 에이전트들)의 등급이 동일 finding에서 다르면:
- **더 높은 등급 채택 (보수적)**: 단, Critical 주장 쪽이 7개 기준 중 **명시 인용**한 경우에만. 인용 없으면 Major로 타협
- 두 리뷰 모두 Critical → 자동으로 consensus high confidence
- 한쪽만 Critical, 다른 쪽 Major/Minor → 한 단계 낮춤 (Major)

---

## scope 판정 (fix_now vs followup)

| scope | 기준 |
|-------|------|
| **fix_now** | 이 PR에서 수정 가능 + 미수정 시 병합 후 문제 악화 |
| **followup** | 기존 구조 문제 + 이 PR에서 해결하기엔 범위 과도 |

### 판정 원칙
- Critical은 거의 항상 `fix_now` (예외: 이전 릴리스에 이미 존재 + 이번 PR로 악화 없음 → followup 가능하나 증거 필요)
- Major 중 이 PR의 변경이 도입한 문제 → `fix_now`
- Major 중 기존에 존재하던 문제 → `followup` (단, 악화시키면 `fix_now`)
- Minor/Nit는 거의 항상 `followup`

---

## 참고: 에이전트별 severity 경향 (historical)

| 에이전트 | 주로 Critical | 주로 Major | 주로 Minor |
|---------|-------------|-----------|-----------|
| Correctness | 장애 직결 로직, dead code | 조건부 오동작 | 드문 edge case |
| Reliability | 서비스 중단, 데이터 손실 | 에러 처리 누락, retry 무력화 | 로깅 부족 |
| Security | 인증 우회, Injection, RCE | XSS 전제 조건부, SSRF 우회 | 보안 모범사례 |
| Performance | OOM, 타임아웃 | N+1, 유의미한 지연 | 마이크로 최적화 |
| Maintainability | (거의 없음) | SRP 위반, 핵심 중복, dead code | 선택적 개선 |
