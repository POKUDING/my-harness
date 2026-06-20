# AWS Provider

`/handover-init`의 멀티클라우드 plugin 중 첫 구현 (read-only).

## Detect

활성 여부 감지 명령:

```bash
aws sts get-caller-identity 2>/dev/null
```

성공 조건:
- exit code 0
- JSON 응답에 `Account` 필드 존재

실패 시 (자격증명 없음·CLI 미설치·권한 부족 등) → 즉시 skip, 사용자 인터뷰로 fallback.

## Scope Map

| 절 ID | AWS 수집 |
|-------|----------|
| E (인프라) | VPC, ECS Fargate 서비스, ALB, RDS, S3, API Gateway, EventBridge, SQS, CloudFront |
| F (Secrets) | Secrets Manager secret 이름 (값 제외) |
| N (Bastion) | EC2 Bastion + SSM Session Manager |
| D (CICD, 보강) | CodePipeline / CodeBuild가 있으면 GitHub Actions와 함께 |
| K (Scheduler, 보강) | EventBridge rules가 cron이면 |

## Commands (화이트리스트)

### 자격증명/계정

- `aws sts get-caller-identity`

### 컴퓨트 (ECS)

- `aws ecs list-clusters`
- `aws ecs list-services --cluster <CLUSTER_ARN>`
- `aws ecs describe-services --cluster <CLUSTER_ARN> --services <SERVICE_ARN>`
- `aws ecs describe-task-definition --task-definition <TASK_DEF_ARN>` (컨테이너 이미지·환경변수 키만; 값 X)

### 네트워크 / ALB

- `aws ec2 describe-vpcs`
- `aws ec2 describe-subnets`
- `aws ec2 describe-security-groups`
- `aws elbv2 describe-load-balancers`
- `aws elbv2 describe-target-groups`

### DB / 저장소

- `aws rds describe-db-instances`
- `aws rds describe-db-clusters`
- `aws s3 ls` (top-level only)
- `aws s3 ls s3://<bucket>` (top-level objects 노출 X — 카운트만)

### Secrets (이름만)

- `aws secretsmanager list-secrets`
- `aws ssm describe-parameters` (이름만)

### API Gateway

- `aws apigatewayv2 get-apis`
- `aws apigatewayv2 get-routes --api-id <ID>`
- `aws apigateway get-rest-apis`

### Scheduler / Events

- `aws events list-rules`
- `aws events describe-rule --name <NAME>`
- `aws events list-targets-by-rule --rule <NAME>`
- `aws scheduler list-schedules` (EventBridge Scheduler)

### Queue / Messaging

- `aws sqs list-queues`
- `aws sqs get-queue-attributes --queue-url <URL>` (attribute 일부만)
- `aws sns list-topics`

### CDN / 정적

- `aws cloudfront list-distributions`

### CICD

- `aws codepipeline list-pipelines`
- `aws codebuild list-projects`

### Bastion / SSM

- `aws ec2 describe-instances --filters "Name=tag:Name,Values=*bastion*"`
- `aws ssm describe-instance-information`

## 금지 명령

- 모든 `*-create-*`, `*-delete-*`, `*-update-*`, `*-put-*`
- `aws iam *` (권한 변경 가능성)
- `aws secretsmanager get-secret-value` (값 노출)
- `aws ssm get-parameter --with-decryption` (값 노출)
- `aws ce *`, `aws cost-explorer *` (비용 발생)
- `aws s3 sync`, `aws s3 cp` (대량 다운로드)

이외 명령이 필요하면 사용자에게 물어보고 추가하라. 임의 실행 금지.

## Output Mapping

### 절 E (인프라)

- `aws ec2 describe-vpcs` → VPC ID·CIDR·태그를 표로
- `aws ecs list-services` + `describe-services` → 서비스 이름·태스크 수·로드 밸런서를 표로
- `aws rds describe-db-instances` → 인스턴스명·엔진·multi-AZ·storage를 표로
- `aws s3 ls` → 버킷 목록을 한 줄씩
- `aws apigatewayv2 get-apis` → API 이름·프로토콜·엔드포인트를 표로
- `aws events list-rules` → cron 스케줄 목록을 표로
- `aws sqs list-queues` → 큐 URL 목록

Mermaid: 위 수집 결과를 `graph TB`로 자동 생성. ALB → ECS → RDS/S3/SQS 흐름.

### 절 F (Secrets)

- `aws secretsmanager list-secrets` → secret 이름·ARN·tag만. 값 절대 노출 X.
- `aws ssm describe-parameters` → parameter 이름만.

### 절 N (Bastion)

- `aws ec2 describe-instances` (bastion 필터) → 인스턴스 ID, key pair 이름.
- `aws ssm describe-instance-information` → SSM 가능 여부.

### 절 D (보강)

- CodePipeline 있으면 GitHub Actions 표 옆에 별도 sub-section.

### 절 K (보강)

- EventBridge rules가 cron이면 절 K에 cron 잡 목록 추가.

## 안전장치

1. 모든 출력은 `.harness/handover-init/{TS}-cloud-output.log`에 저장 (디버깅용).
2. 자격증명·secret 값 노출 시 자동 마스킹:
   - `AKIA[0-9A-Z]{16}` → `AKIA****`
   - Secrets Manager ARN의 secret 값 부분 → 마스킹
3. 화이트리스트 외 명령은 사용자에게 알림 후 중단.
4. 출력이 50줄 초과 시 `head 20` + `tail 20` + `… (전체는 로그 파일)`.
