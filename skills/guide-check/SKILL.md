---
name: guide-check
description: ".harness/guide.md 가이드 문서와 현재 코드를 비교하여 불일치 항목을 찾고 결과를 저장한다. 히스토리 기반으로 이전 check 이후 변경된 범위만 자동 추적한다."
---

# Guide Check — 가이드 일치 여부 확인

`.harness/guide.md`와 현재 코드를 비교하여 불일치 항목을 찾아 `.harness/guide/checks/`에 저장한다.

## 사용법

```
/guide-check             # 마지막 check 이후 변경된 범위만 확인 (히스토리 기반)
/guide-check --full      # 가이드 전체 범위 확인
/guide-check src/api/    # 특정 디렉토리/파일만 확인
```

## 실행 흐름

### Step 0: 사전 확인

`.harness/guide.md`가 존재하는지 확인한다.

없으면 안내 후 중단:
```
가이드 문서가 없습니다.
먼저 /guide-init 를 실행하여 가이드를 생성하세요.
```

### Step 1: 확인 범위 결정

`.harness/guide-history.json`에서 마지막 check 실행 정보를 읽는다.

**범위 결정 로직:**
- `--full` 플래그 → 가이드 전체 범위
- 특정 경로 지정 → 해당 경로만
- 이력 있음 → 마지막 check의 `commit` 이후 변경된 파일만
  ```bash
  git diff {last_check_commit}...HEAD --name-only
  ```
- 이력 없음 → 가이드 전체 범위

사용자에게 범위를 보여준다:
```
확인 범위: 마지막 check(2026-04-10) 이후 변경된 파일 7개
  - src/api/orders.ts
  - src/services/payment.ts
  - ...
```

### Step 2: 섹션별 비교

가이드의 각 섹션을 실제 코드와 비교한다:

#### 2-1. API 엔드포인트

가이드의 엔드포인트 목록과 실제 라우트 파일을 비교:
```bash
grep -r "router\.\(get\|post\|put\|patch\|delete\)" src/ --include="*.ts"
```

불일치 유형:
- **가이드에만 있음** (코드에서 삭제됨)
- **코드에만 있음** (가이드에 미등록)
- **경로 변경** (같은 핸들러, 다른 경로)

#### 2-2. 데이터 모델

가이드의 모델 구조와 실제 스키마/타입 파일 비교.

불일치 유형:
- **필드 추가/삭제**
- **타입 변경**
- **모델 추가/삭제**

#### 2-3. 디렉토리 구조

가이드의 디렉토리 설명과 실제 구조 비교.

불일치 유형:
- **디렉토리 추가/삭제**
- **역할 설명 불일치**

#### 2-4. 기술 스택

가이드의 스택 정보와 현재 `package.json` 등 비교.

불일치 유형:
- **버전 변경**
- **의존성 추가/삭제**

#### 2-5. 환경 설정

가이드의 환경변수 목록과 코드에서 사용되는 `process.env.*` 비교.

불일치 유형:
- **사용하지 않는 환경변수** (가이드에만 있음)
- **문서화 안 된 환경변수** (코드에만 있음)

### Step 3: 결과 저장

`.harness/guide/checks/{YYYYMMDD_HHmmss}-check.json`과 `.harness/guide/checks/{YYYYMMDD_HHmmss}-check.md`를 저장한다.

JSON 형식:
```json
{
  "metadata": {
    "date": "YYYY-MM-DDTHH:mm:ss",
    "scope": "incremental",
    "base_commit": "abc1234",
    "head_commit": "def5678",
    "files_checked": 7,
    "total_issues": 4,
    "auto_fixable": 3,
    "manual_required": 1
  },
  "issues": [
    {
      "id": "GC-001",
      "section": "api_endpoints",
      "type": "missing_in_guide",
      "severity": "major",
      "description": "POST /api/v1/payments 엔드포인트가 코드에 있으나 가이드에 없음",
      "file": "src/api/payments.ts",
      "line": 42,
      "fix_type": "auto",
      "suggested_fix": "가이드 API 섹션에 추가"
    },
    {
      "id": "GC-002",
      "section": "data_models",
      "type": "field_mismatch",
      "severity": "minor",
      "description": "Order 모델에 `payment_method` 필드 추가됨 (가이드 미반영)",
      "file": "src/models/order.ts",
      "fix_type": "auto",
      "suggested_fix": "가이드 데이터 모델 섹션 업데이트"
    }
  ]
}
```

### Step 4: 히스토리 갱신

`.harness/guide-history.json`에 check 실행 이력을 추가한다:

```json
{
  "date": "YYYY-MM-DDTHH:mm:ss",
  "action": "check",
  "commit": "def5678",
  "scope": "incremental",
  "result_file": "YYYYMMDD_HHmmss-check.json",
  "total_issues": 4,
  "auto_fixable": 3
}
```

### Step 5: 결과 보고

```markdown
## Guide Check 결과

### 확인 범위
- 기준: 마지막 check(2026-04-10) 이후 변경
- 확인 파일: 7개 | 확인 섹션: 5개

### 불일치 항목 (4건)

| ID | 섹션 | 내용 | 심각도 | 수정 |
|----|------|------|--------|------|
| GC-001 | API 엔드포인트 | POST /api/v1/payments 미등록 | Major | 자동 |
| GC-002 | 데이터 모델 | Order.payment_method 필드 미반영 | Minor | 자동 |
| GC-003 | 디렉토리 구조 | src/integrations/ 디렉토리 미등록 | Minor | 자동 |
| GC-004 | 기술 스택 | stripe 의존성 추가됨 (v12.3.0) | Minor | 자동 |

### 요약
- 자동 수정 가능: 3건
- 수동 확인 필요: 1건

저장: .harness/guide/checks/YYYYMMDD_HHmmss-check.md/.json

다음: /guide-fix 로 자동 수정 가능한 항목을 반영하세요
```
