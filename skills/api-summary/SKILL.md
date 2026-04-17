---
name: api-summary
description: "작업이 끝난 뒤 협업팀과 공유하기 위한 API 변경 요약 문서를 생성하는 스킬. 지정된 범위(또는 최근 작업 커밋)에서 추가/수정/삭제된 API 엔드포인트를 자동 파싱하여 신규/수정/삭제로 분류한 Markdown을 만든다. Express, NestJS, FastAPI, Django REST, Flask 등 자동 감지. API 변경 공유, 팀 공유, 릴리즈 노트, PR 설명, API changelog 요청 시 이 스킬을 사용할 것."
---

# API Summary — 협업팀 공유용 API 변경 요약

코드 리뷰 반영, 새 기능 구현, 리팩토링 등 **어떤 종류의 작업이든 끝난 뒤** 그 작업으로 발생한 API 변경을 협업팀에 공유할 문서로 정리한다.

**사용 맥락 (독립 스킬, 특정 워크플로우에 종속되지 않음):**
- PR을 열기 전 PR 설명에 붙일 요약이 필요할 때
- 프론트엔드/모바일/QA 팀에 Slack으로 공유할 체크리스트가 필요할 때
- 릴리즈 노트/변경 로그 초안이 필요할 때
- 외부 소비자(파트너 API 등)에게 breaking change를 고지해야 할 때

원하는 작업이 끝난 **어느 시점에서나** 독립적으로 실행할 수 있다. 특정 스킬 실행 직후에만 쓰는 것이 아니다.

## 사용법

```
/api-summary                                     # 최근 변경 범위 자동 탐지
/api-summary --since <commit>                    # 특정 커밋 이후
/api-summary --range main..HEAD                  # diff 범위 지정
/api-summary --files src/api/*.ts                # 특정 파일만
/api-summary --plan-execute <execute.json>       # plan-execute 결과 기반
/api-summary --format md|json                    # 출력 형식 (기본: md)
```

## 실행 흐름

### Step 0: 범위 결정

다음 우선순위로 변경 범위를 정한다:

1. `--since`/`--range`/`--files` 플래그 → 명시적 범위
2. `--plan-execute` → 해당 실행의 `files_changed` 합집합을 범위로
3. `.harness/api-summaries/`에 이전 요약 있으면 → 해당 이후 커밋 범위
4. `.harness/reviews/` 최근 리뷰 이후 범위 (fallback)
5. 모두 없으면 → `git log --since="7 days ago"` 범위

범위가 결정되면 사용자에게 확인:
```
변경 범위: main..HEAD (12 커밋, 23 파일)
API 관련 파일 추정: 5개
  - src/api/orders.ts
  - src/api/payments.ts
  - src/routes/index.ts
  - ...
진행할까요? [Y/n]
```

### Step 1: 프레임워크 감지

레포를 훑어 API 프레임워크를 식별한다:

| 시그니처 | 프레임워크 |
|----------|-----------|
| `package.json`에 `express` | Express |
| `package.json`에 `@nestjs/core` | NestJS |
| `package.json`에 `fastify` | Fastify |
| `package.json`에 `hono`, `next` App Router `route.ts` | Hono / Next.js |
| `requirements.txt`/`pyproject.toml`에 `fastapi` | FastAPI |
| `requirements.txt`에 `djangorestframework` | Django REST |
| `requirements.txt`에 `flask` | Flask |
| `go.mod`에 `gin-gonic/gin`, `labstack/echo` | Gin / Echo |
| `*.yaml`/`*.json` OpenAPI 스키마 | OpenAPI spec |

여러 개 감지되면 모두 처리 (모노레포 대응). 하나도 못 찾으면 사용자에게 프레임워크 지정 요청.

### Step 2: 엔드포인트 추출

**변경 전(base)과 변경 후(head) 각각에서 엔드포인트 목록을 추출한다.**

프레임워크별 파싱 패턴:

#### Express / Fastify / Hono
```
router.get|post|put|patch|delete('/path', handler)
app.METHOD('/path', ...)
```
- Zod 스키마 연결: `.parse(req.body)` 근처 스키마 식별
- JSDoc 주석에서 설명 추출

#### NestJS
```
@Get('/path'), @Post('/path'), @Controller('/base')
```
- Controller base path + method path 조합
- DTO 클래스 분석 (`@Body() dto: CreateOrderDto` → DTO 필드 추출)
- `@ApiOperation`, `@ApiResponse` 데코레이터 활용

#### FastAPI
```
@app.get("/path"), @router.post("/path")
```
- Pydantic 모델 분석 (response_model, 파라미터 타입)
- docstring에서 설명 추출

#### Django REST
- `urls.py`의 path() 패턴
- ViewSet의 action, Serializer 필드
- `@action` 데코레이터

#### Flask
```
@app.route('/path', methods=['GET'])
```

#### OpenAPI spec
- `paths.*.*` 직접 파싱

**각 엔드포인트에서 추출할 정보:**
- `method` (GET/POST/...)
- `path` (정규화: `/api/v1/docs`)
- `description` (주석/데코레이터/docstring)
- `request.params` (path params)
- `request.query` (쿼리 파라미터)
- `request.body` (요청 바디 스키마)
- `request.headers` (요구되는 커스텀 헤더)
- `response` (응답 스키마 / 상태 코드)
- `file` (정의 위치)

### Step 3: 변경 분류

base와 head의 엔드포인트 집합을 비교:

- **신규**: head에만 있음
- **삭제**: base에만 있음
- **수정**: 양쪽에 같은 `method + path`가 있으나 내용이 다름
  - 비교 항목: request/response 스키마, 쿼리/파라미터, 상태 코드, 핸들러 로직 해시
  - 단순 스타일 변경(포맷팅, 변수명)은 제외

path 변경 감지:
- 같은 핸들러 함수인데 path가 다름 → "path 변경"으로 수정 카테고리에 기록

### Step 4: 변경 내용 상세 분석 (수정 항목)

"수정" 분류된 각 엔드포인트에 대해 무엇이 변경됐는지 구체화:

- 쿼리 파라미터: 추가/삭제/타입 변경
- 요청 바디: 필드 추가/삭제, 필수/선택 변경, 타입 변경
- 응답 바디: 필드 추가/삭제
- 상태 코드: 추가된 에러 케이스
- 인증/권한: 스코프 변경

커밋 메시지를 참고하여 변경 의도 추정 (단, 단정하지 않고 "추정"으로 표기).

### Step 5: Markdown 생성

출력 파일: `.harness/api-summaries/{YYYYMMDD_HHmmss}-summary.md`

```markdown
# API 스펙 변경 요약

생성일: YYYY-MM-DD
범위: {commit range 또는 plan-execute 파일}
감지 프레임워크: NestJS, FastAPI

---

## 신규 생성

### POST /api/v1/orders
결제 대기 상태의 주문을 생성한다.

- **요청 방법**
  - Body: `CreateOrderDto`
    - `items: OrderItem[]` (필수) — 상품 목록
    - `shippingAddress: string` (필수)
    - `couponCode?: string` (선택)
  - Headers: `Authorization: Bearer <token>` (필수)
- **응답 값 설명**
  - `200 OK`: `{ orderId: string, status: 'pending_payment', totalAmount: number }`
  - `400 Bad Request`: 재고 부족 또는 검증 실패
  - `401 Unauthorized`: 인증 누락
- **구현**: [src/api/orders.ts:34](src/api/orders.ts#L34)

### GET /api/v1/orders/:id
... (동일 구조)

---

## 수정 사항

### GET /api/v1/docs
문서를 불러오는 api

- **변경 내용**: 쿼리 파라미터 형식 변경 (`ids=1,2,3` → `id=1&id=2&id=3`)
- **요청 방법**
  - Query: `id: number[]` (중복 허용, 기존 `ids: string` 단일값)
- **응답 값 설명** (변경 없음)
  - `200 OK`: `Doc[]`
- **구현**: [src/api/docs.ts:12](src/api/docs.ts#L12)
- **호환성**: Breaking — 기존 클라이언트 `ids=...` 사용 불가
- **추정 사유** (커밋 `abc1234`): "query param을 표준 배열 형식으로 통일"

---

## 삭제 사항

### DELETE /api/v1/legacy/sync
과거 동기화 엔드포인트

- **삭제 사유** (추정): legacy 경로 정리, 새 엔드포인트 `/api/v2/sync`로 대체됨
- **마지막 구현 위치**: src/api/legacy.ts (삭제됨)
- **영향**: 외부 클라이언트 사용 여부 확인 필요

---

## 요약

| 구분 | 건수 |
|------|------|
| 신규 | 3 |
| 수정 | 2 |
| 삭제 | 1 |
| **합계** | 6 |

**Breaking changes**: 1건 (GET /api/v1/docs 쿼리 형식 변경)

## 메타

- 분석 범위: `<base_sha>..<head_sha>`
- 커밋 수: 12
- 파싱된 엔드포인트: base 37개, head 39개
```

### JSON 출력 (`--format json`)

`.harness/api-summaries/{ts}-summary.json`:
```json
{
  "metadata": {
    "date": "YYYY-MM-DDTHH:mm:ss",
    "range": "main..HEAD",
    "frameworks": ["NestJS", "FastAPI"],
    "summary": { "added": 3, "modified": 2, "removed": 1 },
    "breaking_changes": 1
  },
  "added": [
    {
      "method": "POST",
      "path": "/api/v1/orders",
      "description": "결제 대기 상태의 주문을 생성",
      "request": { "body": {...}, "headers": {...} },
      "response": { "200": {...}, "400": {...} },
      "file": "src/api/orders.ts",
      "line": 34
    }
  ],
  "modified": [
    {
      "method": "GET",
      "path": "/api/v1/docs",
      "changes": ["query_param_format_changed"],
      "breaking": true,
      "before": {...},
      "after": {...},
      "suspected_reason": "query param 표준화",
      "commit": "abc1234"
    }
  ],
  "removed": [...]
}
```

### Step 6: 결과 안내

요약 파일 경로와 활용 힌트를 표시한다. 이 스킬은 체인의 일부가 아니라 **공유 목적의 독립 산출물**을 만드는 스킬이다. 따라서 다음 단계를 강제하지 않는다.

```
저장: .harness/api-summaries/YYYYMMDD_HHmmss-summary.md

요약 통계:
  - 신규 3건 / 수정 2건 / 삭제 1건
  - Breaking change: 1건

이 문서는 다음 용도로 바로 활용할 수 있습니다:
  - PR 설명: 내용 복사 또는 파일 링크
  - Slack/Jira 공유: Markdown 블록 그대로 붙여넣기
  - 릴리즈 노트: `### API 변경` 섹션으로 편입
  - 외부 소비자 공지: breaking change 항목만 발췌
```

Breaking change가 있으면 상단에 명시적 경고를 한 번 더 표시한다.

## 검증 원칙

1. **단정하지 않음** — 파싱 실패한 부분은 "(추출 실패, 수동 확인 필요)"로 표기
2. **주석/데코레이터 우선** — 코드보다 개발자가 적은 설명을 우선 (OpenAPI 데코레이터, JSDoc 등)
3. **일관된 path 정규화** — trailing slash, `/api/` prefix 변형 통일
4. **수정 판정은 보수적** — 단순 리팩토링(변수명 변경, 포맷팅)은 "수정"으로 분류하지 않음
5. **Breaking 판정 기준**:
   - path 또는 method 변경
   - 필수 파라미터/필드 추가
   - 응답 필드 삭제 또는 타입 변경
   - 기존 상태 코드가 다른 의미로 변경

## 제약

- 동적으로 생성되는 라우트(런타임 등록)는 감지 불가
- 프레임워크 외부의 커스텀 라우터는 패턴을 사용자가 직접 제공해야 함
- 스키마가 런타임 조립되면 정적 분석으로 한계 — 가능한 수준에서만 요약

## 설정

`.harness/api-summary.json` (선택):

```json
{
  "api_path_prefix": "/api",
  "ignore_paths": ["/api/internal/*", "/api/debug/*"],
  "include_private_endpoints": false,
  "framework_override": null
}
```

- `api_path_prefix`: 이 prefix로 시작하는 경로만 API로 간주
- `ignore_paths`: 요약에서 제외할 경로 glob
- `include_private_endpoints`: 내부 전용 경로 포함 여부
- `framework_override`: 자동 감지 대신 고정 (`"express"`, `"nestjs"` 등)
