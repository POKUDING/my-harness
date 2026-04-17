---
name: proj-status
description: 현재 프로젝트 상태 분석 - git, 파일, 의존성, 건강 상태
---

# 프로젝트 상태 분석

현재 프로젝트의 상태를 종합 리포트로 제공한다.

## 분석 항목

1. **Git 상태**: 현재 브랜치, 미커밋 변경사항, 최근 커밋 이력
2. **의존성**: `package.json`에서 구식/누락된 의존성 확인
3. **파일 구조**: 프로젝트 구조와 주요 디렉토리 개요
4. **건강 체크**: 일반적인 이슈 확인 (`.gitignore` 누락 항목, TODO/FIXME 수, TypeScript 에러 등)

## 출력 형식

```markdown
## 프로젝트 상태 리포트

### Git
- 브랜치: {branch}
- 미커밋 변경: {count}건
- 마지막 커밋: {message} ({time ago})

### 의존성
- 총 패키지: {count}
- 이슈: {outdated 또는 missing}

### 코드 건강
- TODO/FIXME: {count}
- TypeScript 에러: {count}
- 테스트 커버리지: {가능하면}

### 권장 사항
- {실행 가능한 개선 항목}
```

## 실행 방법

- `git status`, `git log`, 파일 Read로 데이터 수집
- `package.json`이 있으면 `npm outdated` 실행
- Grep으로 TODO/FIXME 카운트
- `tsconfig.json`이 있으면 `npx tsc --noEmit` 실행
- 리포트는 간결하고 실행 가능한 수준으로 유지
