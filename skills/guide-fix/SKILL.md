---
name: guide-fix
description: "guide-check 결과의 불일치 항목을 .harness/guide.md에 반영하여 수정하고, 수정 기록을 저장한다."
---

# Guide Fix — 가이드 불일치 수정

`/guide-check`로 생성된 check 결과의 불일치 항목을 `.harness/guide.md`에 반영하고 수정 기록을 저장한다.

## 사용법

```
/guide-fix                                               # 가장 최근 check 결과 사용
/guide-fix .harness/guide/checks/20260410_143022-check.json  # 특정 check 결과 지정
```

## 실행 흐름

### Step 0: Check 결과 로드

1. **인자 있음** → 지정된 JSON 파일을 Read
2. **인자 없음** → `.harness/guide/checks/` 디렉토리에서 가장 최근 `*-check.json` 자동 탐지
3. JSON이 없으면 안내 후 중단:
   ```
   Check 결과를 찾을 수 없습니다.
   먼저 /guide-check 를 실행하세요.
   ```

### Step 1: 수정 계획 수립

`auto_fixable` 항목만 필터링하여 수정 계획을 사용자에게 보여준다:

```markdown
## 수정 계획

| ID | 섹션 | 내용 | 심각도 |
|----|------|------|--------|
| GC-001 | API 엔드포인트 | POST /api/v1/payments 추가 | Major |
| GC-002 | 데이터 모델 | Order.payment_method 필드 추가 | Minor |
| GC-003 | 디렉토리 구조 | src/integrations/ 추가 | Minor |

총 3건 수정 예정. 진행할까요?

수동 확인 필요 항목 (이번에 수정하지 않음):
- GC-004: 기술 스택 — stripe 의존성 목적 확인 필요 (수동)
```

사용자 확인 후 진행한다.

### Step 2: 섹션별 가이드 업데이트

각 issue의 `section`에 따라 `.harness/guide.md`의 해당 섹션을 수정한다:

#### `api_endpoints` — API 엔드포인트 섹션 수정
- `missing_in_guide`: 코드에서 실제 엔드포인트 정보를 읽어 표에 행 추가
- `removed_from_code`: 해당 행 삭제 (또는 `[삭제됨]` 표시)
- `path_changed`: 경로 업데이트

#### `data_models` — 데이터 모델 섹션 수정
- `field_mismatch`: 실제 타입/스키마 파일을 읽어 모델 설명 업데이트
- `model_added`: 새 모델 섹션 추가
- `model_removed`: 모델 섹션 삭제 또는 `[삭제됨]` 표시

#### `directory_structure` — 디렉토리 구조 섹션 수정
- 실제 디렉토리 목록 반영

#### `tech_stack` — 기술 스택 섹션 수정
- `package.json` 재읽어 버전/의존성 업데이트

#### `env_config` — 환경 설정 섹션 수정
- 코드에서 추출된 환경변수 목록 반영

수정 시 가이드 하단 **변경 이력** 표에 항목을 추가한다:

```markdown
| YYYY-MM-DD | guide-fix: GC-001, GC-002, GC-003 반영 | def5678 |
```

### Step 3: 결과 저장

`.harness/guide/fixes/{YYYYMMDD_HHmmss}-fix.json`과 `.harness/guide/fixes/{YYYYMMDD_HHmmss}-fix.md`를 저장한다.

JSON 형식:
```json
{
  "metadata": {
    "date": "YYYY-MM-DDTHH:mm:ss",
    "source_check": "YYYYMMDD_HHmmss-check.json",
    "total_issues": 4,
    "fixed": 3,
    "skipped": 1
  },
  "results": [
    {"id": "GC-001", "status": "fixed", "section": "api_endpoints", "description": "POST /api/v1/payments 추가"},
    {"id": "GC-002", "status": "fixed", "section": "data_models",   "description": "Order.payment_method 추가"},
    {"id": "GC-003", "status": "fixed", "section": "directory_structure", "description": "src/integrations/ 추가"},
    {"id": "GC-004", "status": "skipped", "reason": "manual_required", "description": "stripe 의존성 목적 확인 필요"}
  ]
}
```

### Step 4: 히스토리 갱신

`.harness/guide-history.json`에 fix 실행 이력을 추가한다:

```json
{
  "date": "YYYY-MM-DDTHH:mm:ss",
  "action": "fix",
  "commit": "def5678",
  "source_check": "YYYYMMDD_HHmmss-check.json",
  "result_file": "YYYYMMDD_HHmmss-fix.json",
  "fixed": 3,
  "skipped": 1
}
```

### Step 5: 완료 보고

```markdown
## Guide Fix 완료

### 수정 결과
| ID | 섹션 | 내용 | 결과 |
|----|------|------|------|
| GC-001 | API 엔드포인트 | POST /api/v1/payments 추가 | 수정 완료 |
| GC-002 | 데이터 모델 | Order.payment_method 추가 | 수정 완료 |
| GC-003 | 디렉토리 구조 | src/integrations/ 추가 | 수정 완료 |
| GC-004 | 기술 스택 | stripe 의존성 | 스킵 (수동 확인 필요) |

### 요약
- 수정 완료: 3건
- 스킵: 1건

저장:
- .harness/guide/fixes/YYYYMMDD_HHmmss-fix.md
- .harness/guide/fixes/YYYYMMDD_HHmmss-fix.json
- .harness/guide.md 업데이트됨

수동 확인 필요 항목:
- GC-004: stripe 의존성 추가 목적을 확인하고 기술 스택 섹션에 직접 추가하세요
```

## 안전 장치

1. **수정 전 사용자 확인 필수** — 수정 계획을 보여주고 승인 후 진행
2. **auto_fixable만 수정** — `manual_required` 항목은 절대 건드리지 않음
3. **가이드만 수정** — 실제 소스 코드는 절대 변경하지 않음
4. **실패 시 안내** — `git checkout -- .harness/guide.md`로 복구 가능함을 안내
