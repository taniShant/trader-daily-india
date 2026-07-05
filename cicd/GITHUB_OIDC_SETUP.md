# GitHub OIDC AWS Deployment Setup

This project should not use long-lived AWS access keys in GitHub.

The AWS account already has the GitHub OIDC provider. Its ARN is declared in `cicd/env/prod.json`. The CDK IAM stack imports that provider and creates one GitHub Actions OIDC deploy role. GitHub Actions then assumes that role directly.

Existing provider ARN:

```text
arn:aws:iam::632943041262:oidc-provider/token.actions.githubusercontent.com
```

Required trust:

- OIDC provider: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`
- Repository/branch subject: `repo:taniShant/trader-daily-india:ref:refs/heads/main`

Role name:

```text
svc-trd-github-deploy-role
```

The role needs enough permissions to run the deployment workflow:

- ECR image push
- CloudFormation/CDK deploy
- ECS service/task-definition updates
- IAM pass-role for existing ECS roles
- CloudWatch Logs/alarms
- EventBridge rules
- DynamoDB/S3 resources managed by CDK

Create/update the role from a local AWS identity that can manage IAM:

```bash
cdk deploy svc-trd-IamStack --require-approval never
```

Then run:

```text
Actions -> Deploy AWS Trading System -> Run workflow -> dry_run=true
```
