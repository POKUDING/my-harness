---
name: handover-init
description: "프로젝트 인수인계 폴더(handover/)를 자동 생성하는 스킬. 코드 분석 + 클라우드 CLI(AWS 첫 구현) + 사용자 인터뷰의 3단계 파이프라인으로 ete-django 수준의 15절+Mermaid 인수인계 문서를 만든다. 신규 프로젝트 인수인계, handover 문서 생성 요청 시 사용."
---

# Handover Init — 인수인계 폴더 자동 생성

`/handover-init`은 ete-django 수준의 인수인계 문서를 3단계 자동/반자동 파이프라인으로 생성한다.

## 사용자 입력 UI (v0.21+)

절 후보 컨펌·Mermaid 일괄 검토는 **`AskUserQuestion`**. 절별 자유 텍스트 인터뷰는 일반 텍스트 prompt.

## 사용법

```
/handover-init                              # 인터뷰 진행, 기본 동작
/handover-init --skip-interview             # 인터뷰 생략, 빈 칸 [확인 필요]
/handover-init --output ./docs/handover     # 출력 위치 변경
/handover-init --provider aws,vercel        # 특정 provider만 활성
/handover-init --skip-mermaid               # Mermaid 자동 생성 끔
/handover-init --resume                     # 인터뷰 중단 후 재개
```

## 실행 흐름

### Step 0: 사용자 입력 + 초기화

1. CLI 인자 파싱: `--skip-interview` / `--output` / `--provider` / `--skip-mermaid` / `--resume`
2. 출력 위치 기본값 = `<project-root>/handover/`. `--output` 있으면 그 경로.
3. State 파일 경로: `.harness/handover-init/{TS}-state.json`
   - `--resume` 시: 가장 최근 state 자동 로드, 진행 중인 단계부터 재개.
   - 새 실행: `mkdir -p .harness/handover-init/` 후 state 신규 생성.
4. 사용자에게 시작 알림:

```
/handover-init 시작
- 프로젝트 루트: {pwd}
- 출력 위치: handover/
- 활성 provider: {--provider 인자 또는 all}
- 인터뷰: {진행 / 생략}
- Mermaid: {자동 / 끔}
```

### Step 1: 코드 분석 (1차)

다음 자료를 자동 추출:

1. **프레임워크 감지**
   - `package.json` → Node/React/Next/Express 등
   - `pyproject.toml` / `setup.py` / `requirements.txt` → Python/Django/FastAPI 등
   - `Cargo.toml` → Rust
   - `go.mod` → Go
   - `pubspec.yaml` → Flutter
   - `Gemfile` → Ruby

2. **폴더 구조**
   - `find . -type d -maxdepth 3 -not -path '*/node_modules/*' -not -path '*/.git/*' -not -path '*/__pycache__/*'`

3. **외부 통합 키워드**
   - `.env.example`, 설정 파일에서 다음 keyword 탐색:
   - AWS_*, SECRETS_MANAGER_*, EXPO_*, FCM_*, SES_*, MAILGUN_*, TWILIO_*, COOLSMS_*, SLACK_*, JWT_*, OAUTH_*, REDIS_*, ...

4. **git 컨벤션**
   - `git log --oneline -50` → 커밋 메시지 패턴 추출 (Conventional Commits 여부)
   - 브랜치 명명: `git branch -a | head -20`

5. **알려진 SDK 발견**
   - `package.json` dependencies 또는 `requirements.txt` 파싱
   - 매핑 표:
     - `axios` / `requests` → 외부 HTTP
     - `expo-server-sdk` / `firebase-admin` → 푸시
     - `nodemailer` / `@sendgrid/mail` → 이메일
     - `bullmq` / `celery` → 큐
     - `socket.io` / `ws` / `channels` → 실시간

결과를 state에 저장: `state.code_analysis = {...}`

### Step 2: 클라우드 자동 감지 + CLI 호출 (2차)

`skills/handover-init/providers/` 의 모든 plugin 순회:

```python
# 의사코드
for provider_file in providers/*.md:
    if provider in args.providers (or args.providers == "all"):
        plugin = read(provider_file)
        if plugin.body contains "Stub (Future Work)":
            log("provider {name} skipped (stub)")
            continue
        # Detect
        result = bash(plugin.Detect.command)
        if result.exit_code == 0:
            log("provider {name} active")
            # Commands 화이트리스트만 실행
            for cmd in plugin.Commands (whitelisted):
                output = bash(cmd)
                save_to_log(output)
                apply_output_mapping(cmd, output) → state.cloud_results
        else:
            log("provider {name} inactive")
```

**안전장치**:
- 화이트리스트 외 명령 호출 시 사용자에게 알림 후 중단.
- 출력에서 secret/credential 패턴(AKIA*, ARN secret 값) 자동 마스킹.
- 모든 호출 결과는 `.harness/handover-init/{TS}-cloud-output.log`에 저장.
- 50줄 초과 출력은 head 20 + tail 20.

### Step 3: 절 후보 선별 + 컨펌

1차+2차 결과를 종합해 절 후보를 자동 판정:

| 절 ID | 자동 포함 조건 |
|-------|---------------|
| A·B·C·M | 항상 |
| D | `.github/workflows/` 또는 `.gitlab-ci.yml` 또는 `bitbucket-pipelines.yml` 발견 |
| E | IaC(CloudFormation/Terraform/CDK/Pulumi) 또는 클라우드 CLI 성공 |
| F | `.env.example`, secrets 디렉토리, `process.env`/`os.environ` 다수 발견 |
| G | HTTP 클라이언트 + 알려진 SDK 발견 |
| H | Expo/FCM/SES/Mailgun/Twilio/Coolsms 발견 |
| I | ORM 또는 `migrations/` 발견 |
| J | JWT/OAuth/Passport/NextAuth/SimpleJWT 발견 |
| K | celery beat/EventBridge/node-cron/BullMQ 발견 |
| L | WebSocket/SSE/Channels/Socket.io/API Gateway WS 발견 |
| N | Bastion/SSH config/VPN 단서 또는 E 절 포함 시 |
| O | Django admin/Strapi/내부 어드민 라우트 발견 |
| P | `vercel.json`/`netlify.toml`/`next.config.js`/Vite 등 |
| Q | `eas.json`/Expo/Flutter/`Podfile`/`build.gradle` |

자동 검출된 절 + 항상 절(A·B·C·M)을 사용자에게 컨펌:

```python
AskUserQuestion({
  questions: [{
    question: "다음 절들이 자동 감지되었습니다. 진행할 절을 확인해주세요 (제외할 절은 unselect).",
    header: "Section pick",
    multiSelect: true,
    options: [
      { label: "A. 프로젝트 개요 (항상)", description: "프레임워크/스택 자동" },
      { label: "B. 폴더 구조 (항상)", description: "폴더 트리 자동" },
      { label: "C. 로컬 개발 (항상)", description: "패키지 매니저·명령 자동" },
      { label: "D. CI/CD", description: "GitHub Actions YAML 발견" },
      ...
    ]
  }]
})
```

선택된 절을 `state.sections = [...]`에 저장.

### Step 4: 사용자 인터뷰 (3차) — `--skip-interview` 아닐 때

활성 절마다 자유 텍스트 prompt:

```
## 인터뷰 N/{total} — {절 제목}

다음 항목을 자유 텍스트로 한 번에 적어주세요. 빠진 항목은 그대로 [확인 필요] 처리됩니다.

- {빈 칸 항목 1}:
- {빈 칸 항목 2}:
- {빈 칸 항목 3}:

(패스하려면 "skip", 한 번에 끝내려면 "skip all")
```

빈 칸 항목은 `references/section-templates.md`의 절별 "인터뷰 빈 칸" 목록에서 가져옴.

사용자 응답 처리:
- "skip" → 해당 절 모두 [확인 필요]
- "skip all" → 남은 모든 절 [확인 필요], Step 5로 진행
- 자유 텍스트 → LLM이 항목별로 파싱·매핑

매 절 종료 시 state 즉시 저장 (`interview_progress[id] = {status, answers}`).

### Step 5: 절 본문 생성 (병렬 subagent)

활성 절마다 `general-purpose` subagent를 `run_in_background: true`로 spawn:

```python
Agent(
  description: "Generate section {id}",
  subagent_type: "general-purpose",
  model: "sonnet",
  run_in_background: true,
  prompt: """
  이 task는 인수인계 절 {id} ({title})의 본문을 생성한다.

  ## section-templates.md 골격
  {Task 1 reference의 해당 절 본문}

  ## 1·2차 자동 추출 결과
  {state.code_analysis.relevant_part}
  {state.cloud_results.relevant_part}

  ## 인터뷰 답변
  {state.interview_progress[id].answers}

  ## 출력
  완성된 마크다운 절 본문을 반환하라.
  - 골격을 그대로 따른다.
  - 자동 추출 못 한 자리는 [확인 필요] 표기.
  - Mermaid 다이어그램이 있으면 자동 생성 시도. 자신 없으면 `<!-- 자동 생성 실패 — 수동 추가 권장. (이유: ...) -->`로 placeholder만.
  - 모든 Mermaid 위에 `<!-- AI-generated — 검토 필요 -->` 부착.
  """
)
```

`--skip-mermaid` 인자가 있으면 Mermaid 생성 부분 모두 placeholder만.

병렬 spawn 후 모든 subagent 완료까지 대기. 각 결과를 state에 저장.

### Step 6: Mermaid 일괄 검토 — `--skip-mermaid` 아닐 때

자동 생성된 모든 Mermaid 다이어그램 목록을 사용자에게 보여주고 각각 컨펌:

```
다음 N개의 다이어그램이 자동 생성되었습니다:

1. 절 A — 도메인 모듈 맵 (모듈 8개)
2. 절 D — CICD 파이프라인 (job 5개)
3. 절 E — 인프라 구조도 (리소스 12개)
...
```

각 다이어그램에 AskUserQuestion:

```python
AskUserQuestion({
  questions: [{
    question: "다이어그램 {N} — {제목}. 어떻게 처리할까요?",
    header: "Diagram",
    options: [
      { label: "유지 (Recommended)",
        description: "현재 다이어그램을 그대로 사용.",
        preview: "```mermaid\n{diagram body}\n```" },
      { label: "수정",
        description: "수정 지시를 자유 텍스트로 입력 → 다시 생성." },
      { label: "제거",
        description: "다이어그램 제거, 주석만 남김 (`<!-- 다이어그램 제거됨 -->`)." }
    ],
    multiSelect: false
  }]
})
```

수정 선택 시 자유 텍스트 prompt로 지시 받고 LLM이 재생성.

### Step 7: README.md + INDEX 생성

`{output_dir}/README.md`를 자동 생성:

```markdown
# {프로젝트명} 인수인계 문서

> {프로젝트 1줄 설명}

## 대상 리포지토리

- **프레임워크**: {Step 1 추출}
- **DB**: ...
- **배포 환경**: ...

## 문서 구성 (절별)

| # | 파일 | 내용 |
|---|------|------|
| 01 | [01-{slug}.md](01-{slug}.md) | ... |
...

## 다이어그램 표기 규칙

- 모든 구조도/플로우는 **Mermaid**로 작성되어 있어 GitHub/VS Code 등에서 렌더링됩니다.
- ⚠️ **AI-generated 다이어그램은 별도 검토가 필요합니다.** `<!-- AI-generated -->` 주석이 있는 다이어그램은 사용자 확인 후 배포하세요.
- 코드 경로는 프로젝트 루트 기준 상대 경로(`src/...`)를 사용합니다.

## 읽는 순서 권장

1. 처음이라면 **01 → 05 → 12** 순서로 읽고 로컬 구동까지 끝낼 것.
2. 배포/운영 담당이라면 **02 → 03 → 04 → 13**을 먼저 볼 것.

## 자동 생성 정보

- 생성 도구: `/handover-init` (my-harness)
- 생성 일시: {YYYY-MM-DD}
- [확인 필요] 마커 개수: {count}
- AI-generated 다이어그램 개수: {count}
```

절 파일은 `{output_dir}/01-{slug}.md` ~ `{output_dir}/NN-{slug}.md` 순서. slug는 절 제목에서 자동 생성(소문자·하이픈).

### Step 8: 결과 보고

````markdown
## Handover Init 완료

### 생성 파일

```
handover/
├── README.md
├── 01-project-overview.md
├── 02-cicd.md
...
└── NN-{slug}.md
```

### 통계

- 생성된 절: {N}개
- [확인 필요] 마커: {N}개 (절별: ...)
- 자동 Mermaid: {N}개 (유지/수정/제거: ...)
- AWS provider: {활성/skip}
- 코드 분석 결과: {추출 항목 수}

### 다음 단계

- [확인 필요] 마커를 채우세요.
- AI-generated Mermaid를 검토하세요.
- 인수인계 폴더를 GitHub Wiki 등에 미러링하세요.
- 변경이 생기면 (future) `/handover-update` 또는 수동 보완.

### state 파일

- `.harness/handover-init/{TS}-state.json` — 재실행/디버깅용
- `.harness/handover-init/{TS}-cloud-output.log` — 클라우드 CLI 출력 로그
````

## 안전 장치

1. **mutation 명령 금지** — 클라우드 CLI는 plugin Commands 화이트리스트만.
2. **Secrets 값 노출 금지** — Secrets Manager·SSM Parameter는 이름만, 값 절대 호출 안 함.
3. **자동 마스킹** — AWS access key ID, ARN의 secret 값 부분.
4. **state 즉시 저장** — 매 단계 종료 시 즉시 저장하여 중단·재개 안전.
5. **Mermaid hallucination 차단** — 모든 자동 생성 다이어그램에 `<!-- AI-generated — 검토 필요 -->` 부착. Step 6 사용자 컨펌.
6. **출력 위치 안전** — `<project-root>/handover/`가 이미 있으면 사용자에게 덮어쓰기 확인 받음.

## 설정

`.harness/handover-init.json` (선택):

```json
{
  "max_parallel_sections": 5,
  "default_output": "handover/",
  "always_include": ["A", "B", "C", "M"],
  "auto_mask_patterns": ["AKIA[0-9A-Z]{16}"]
}
```
