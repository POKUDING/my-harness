---
name: proj-slack-setup
description: my-harness 플러그인의 프로젝트별 API 토큰/설정을 저장한다 (.harness/config.env)
---

# my-harness 설정

이 프로젝트에서 사용할 API 토큰을 `.harness/config.env`에 저장한다.
파일은 gitignore되어 로컬에만 보관된다.

## Step 1: 현재 설정 확인

`.harness/config.env` 파일이 존재하면 현재 저장된 키 목록을 읽어 사용자에게 보여준다 (값은 마스킹: `xoxb-****`).
파일이 없으면 "아직 설정이 없습니다"라고 안내한다.

## Step 2: 설정할 서비스 선택

사용자에게 어떤 서비스를 설정할지 묻는다:

```
어떤 서비스를 설정할까요?
1. Slack (slack-list-plan 스킬에 필요)
2. 종료
```

## Step 3: Slack 토큰 입력

Slack을 선택한 경우:
- "Slack Bot Token (xoxb-...) 또는 User Token (xoxp-...)을 입력하세요:" 라고 묻는다.
- 입력값이 `xoxb-` 또는 `xoxp-`로 시작하는지 검증한다.
- 유효하지 않으면 다시 묻는다.

Bot Token → `SLACK_BOT_TOKEN`으로 저장
User Token → `SLACK_USER_TOKEN`으로 저장

## Step 4: .harness/config.env 저장

Write 도구로 `.harness/config.env`를 생성/업데이트한다.

파일 형식:
```
# my-harness project config
# DO NOT COMMIT - this file is gitignored
SLACK_BOT_TOKEN=xoxb-...
```

기존 파일이 있으면 해당 키만 업데이트하고 나머지는 유지한다.
파일이 없으면 새로 생성한다.

## Step 5: .gitignore 확인 및 업데이트

`.gitignore`에 `.harness/` 또는 `.harness/config.env`가 포함되어 있는지 확인한다.
없으면 `.gitignore`에 `.harness/` 라인을 추가한다.

## Step 6: 완료 안내

저장된 키 이름 목록을 보여준다 (값은 마스킹).
"이제 /slack-list-plan을 사용할 수 있습니다." 라고 안내한다.
