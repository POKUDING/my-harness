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

**핵심 원칙: 위 Commands 화이트리스트에 명시되지 않은 모든 명령은 자동으로 금지된다.** 아래는 자주 시도되지만 절대 호출하면 안 되는 명령을 명시적으로 나열한 것 — 화이트리스트와 이 목록을 모두 확인하라.

### Mutation 명령 (생성/수정/삭제/등록 — 모두 금지)

다음 동사로 시작하거나 포함하는 명령은 모두 mutation으로 간주하고 금지:
`create-*`, `delete-*`, `update-*`, `put-*`, `run-instances`, `start-*`, `stop-*`, `terminate-*`, `reboot-*`, `register-*`, `deregister-*`, `attach-*`, `detach-*`, `associate-*`, `disassociate-*`, `modify-*`, `restore-*`, `rotate-*`, `enable-*`, `disable-*`, `tag-*`, `untag-*`

예시 (모두 금지):
- `aws ec2 run-instances`, `aws ec2 terminate-instances`, `aws ec2 reboot-instances`
- `aws ec2 create-vpc`, `aws ec2 delete-security-group`
- `aws iam create-role`, `aws iam put-role-policy`, `aws iam attach-role-policy`
- `aws rds create-db-instance`, `aws rds modify-db-instance`, `aws rds delete-db-instance`
- `aws s3api put-object`, `aws s3api delete-object`
- `aws ecs register-task-definition`, `aws ecs update-service`, `aws ecs run-task`
- `aws events put-rule`, `aws events put-targets`
- `aws sqs send-message`, `aws sns publish`

### 권한 변경 (전부 금지)

- `aws iam *` (모든 IAM 명령 — read도 권한 발급 트리거 가능)

### Secret/Parameter 값 노출 (전부 금지)

- `aws secretsmanager get-secret-value`
- `aws ssm get-parameter --with-decryption`
- `aws ssm get-parameters --with-decryption`
- `aws kms decrypt`, `aws kms encrypt`

### 비용 발생 명령

- `aws ce *`, `aws cost-explorer *` (재무 정보 노출 + 호출당 비용)
- `aws athena start-query-execution` (쿼리 비용)
- `aws s3 sync`, `aws s3 cp` (대량 다운로드/업로드)

### 그 외 임의 실행 금지

위에 명시되지 않았어도 **Commands 화이트리스트에 없으면 모두 금지**. 새 명령이 필요하면 사용자에게 묻고 화이트리스트에 추가한 다음 실행하라.

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
