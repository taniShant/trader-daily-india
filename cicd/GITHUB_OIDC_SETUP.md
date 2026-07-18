# GitHub OIDC AWS Deployment Setup

This project should not use long-lived AWS access keys in GitHub.

`svc-trd-PlatformStack` creates the GitHub OIDC provider and the GitHub Actions deploy role. GitHub Actions then assumes that role directly.

Provider URL:

```text
https://token.actions.githubusercontent.com
```

Required trust:

- OIDC provider: `https://token.actions.githubusercontent.com`
- Audience: `sts.amazonaws.com`
- Repository/branch subject: `repo:taniShant/trader-daily-india:ref:refs/heads/main`

Role name:

```text
trd-prod-github-deploy-role
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
CDK_DEPLOY_ENV=prod cdk deploy svc-trd-PlatformStack --profile default --require-approval never
```

Then run:

```text
Actions -> Deploy AWS Trading System -> Run workflow
```
