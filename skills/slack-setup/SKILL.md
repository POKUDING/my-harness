---
name: slack-setup
description: 프로젝트 단위 API 토큰을 .harness/config.env에 저장 (gitignored)
---

# 프로젝트 서비스 설정

프로젝트별 API 토큰을 `.harness/config.env`에 저장한다 (gitignored, 로컬 전용).

## Step 1: 기존 설정 확인

`.harness/config.env`가 존재하면 Read한다. 저장된 키 목록을 사용자에게 보여준다 (값은 마스킹). 파일이 없으면 "설정이 없습니다"라고 안내한다.

## Step 2: 서비스 선택

사용자에게 질문한다: "어떤 서비스를 설정하시겠습니까? 1. Slack  2. 종료"

## Step 3: Slack 토큰 입력

Slack을 선택하면 질문한다: "Slack Bot Token (xoxb-...) 또는 User Token (xoxp-...)을 입력하세요:"

입력값이 `xoxb-` 또는 `xoxp-`로 시작하는지 검증한다. 아니면 다시 요청.

- Bot Token → `SLACK_BOT_TOKEN`으로 저장
- User Token → `SLACK_USER_TOKEN`으로 저장

## Step 3b: Slack List URL 입력

질문: "Slack List URL을 등록하시겠습니까? (선택사항, 나중에 추가 가능)"

등록한다면: "Slack List URL을 입력하세요 (https://...slack.com/lists/T.../F...):"

입력값이 `https://*.slack.com/lists/*/F*` 패턴과 일치하는지 검증한다. 아니면 다시 요청.

`SLACK_LIST_URL`로 저장.

## Step 4: .harness/config.env 저장

Write 도구로 프로젝트 루트의 `.harness/config.env`를 생성하거나 업데이트한다.

형식: 한 줄에 `KEY=value` 하나씩. 파일 상단에 주석 추가: `# DO NOT COMMIT - this file is gitignored`.

파일이 이미 있으면 해당 키만 업데이트하고 다른 항목은 보존한다.

## Step 5: .gitignore 확인

`.harness/`가 `.gitignore`에 있는지 확인한다. 없으면 추가한다.

## Step 6: 완료 확인

저장된 키 이름을 보여준다 (값은 마스킹). `/slack-plan`을 실행할 수 있다고 안내한다.
