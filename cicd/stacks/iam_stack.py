"""
IAM Stack - Creates a single ECS Task Role with all permissions
- Can be used as both Execution Role and Task Role
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_iam as iam,
)
from constructs import Construct


class IAMStack(Stack):
    """
    Creates a single IAM role for ECS Fargate tasks.
    Has permissions for:
    - ECR (pull images)
    - CloudWatch Logs (send logs)
    - DynamoDB (all trading tables)
    - Bedrock (Claude models)
    - S3 (code bucket)
    - Secrets Manager (API keys)
    - EC2/VPC (ENI attachment)
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict | None = None, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        config = config or {}

        # ============================================================
        # SINGLE UNIFIED ROLE
        # ============================================================

        self.role = iam.Role(
            self,
            "TradingSystemRole",
            role_name="svc-trd-ecs-taskexecute-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Unified ECS Task Role for trading system (execution + task)",
        )

        # ============================================================
        # ECR PERMISSIONS (for pulling images)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                ],
                resources=["*"],
            )
        )

        # ============================================================
        # CLOUDWATCH LOGS PERMISSIONS (for sending logs)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                ],
                resources=["arn:aws:logs:*:*:*"],
            )
        )

        # ============================================================
        # DYNAMODB PERMISSIONS (all trading tables)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "dynamodb:GetItem",
                    "dynamodb:PutItem",
                    "dynamodb:UpdateItem",
                    "dynamodb:DeleteItem",
                    "dynamodb:Query",
                    "dynamodb:Scan",
                    "dynamodb:BatchGetItem",
                    "dynamodb:BatchWriteItem",
                ],
                resources=[
                    "arn:aws:dynamodb:*:*:table/svc-trd-trades-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-sessions-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-learning-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-market-state-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-signals-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-risk-events-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-orders-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-fills-*",
                    "arn:aws:dynamodb:*:*:table/svc-trd-positions-*",
                ],
            )
        )

        # ============================================================
        # BEDROCK PERMISSIONS (Claude models)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                ],
                resources=[
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-*",
                ],
            )
        )

        # ============================================================
        # S3 PERMISSIONS (code bucket)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "s3:GetObject",
                    "s3:PutObject",
                    "s3:ListBucket",
                ],
                resources=[
                    "arn:aws:s3:::svc-s3-*",
                    "arn:aws:s3:::svc-s3-*/*",
                ],
            )
        )

        # ============================================================
        # SECRETS MANAGER PERMISSIONS (API keys)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"],  # TODO: Restrict to specific secrets in production
            )
        )

        # ============================================================
        # CLOUDWATCH METRICS PERMISSIONS
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "cloudwatch:PutMetricData",
                    "cloudwatch:GetMetricData",
                ],
                resources=["*"],
            )
        )

        # ============================================================
        # EC2/VPC PERMISSIONS (for ENI attachment - required for Fargate)
        # ============================================================

        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:CreateNetworkInterface",
                    "ec2:AttachNetworkInterface",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeVpcs",
                ],
                resources=["*"],
            )
        )

        # EventBridge Role (for scheduling overnight tasks)
        self.eventbridge_role = iam.Role(
            self,
            "EventBridgeRole",
            role_name="eventbridge-ecs-role",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            description="Role for EventBridge to start ECS tasks",
        )

        self.eventbridge_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["ecs:RunTask"],
                resources=["*"],
            )
        )

        self.eventbridge_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["iam:PassRole"],
                resources=[self.role.role_arn],
            )
        )

        # Add output
        CfnOutput(self, "EventBridgeRoleArn", value=self.eventbridge_role.role_arn)

        # ============================================================
        # OUTPUTS
        # ============================================================

        CfnOutput(
            self,
            "RoleArn",
            value=self.role.role_arn,
            description="ECS Task Role ARN (use for both execution and task)",
            export_name=f"{construct_id}:RoleArn",
        )

        CfnOutput(
            self,
            "RoleName",
            value=self.role.role_name,
            description="ECS Task Role Name",
        )

        # ============================================================
        # GITHUB ACTIONS OIDC DEPLOY ROLE
        # ============================================================

        github_config = config.get("github", {})
        github_repository = github_config.get("repository", "taniShant/trader-daily-india")
        github_branch = github_config.get("deploy_branch", "main")
        github_role_name = github_config.get("deploy_role_name", "svc-trd-github-deploy-role")
        github_oidc_provider_arn = github_config.get(
            "oidc_provider_arn",
            "arn:aws:iam::632943041262:oidc-provider/token.actions.githubusercontent.com",
        )

        github_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
            self,
            "GitHubActionsOidcProvider",
            github_oidc_provider_arn,
        )

        self.github_deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name=github_role_name,
            assumed_by=iam.WebIdentityPrincipal(
                github_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {
                        "token.actions.githubusercontent.com:aud": "sts.amazonaws.com",
                    },
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repository}:ref:refs/heads/{github_branch}",
                    },
                },
            ),
            description=f"GitHub Actions deploy role for {github_repository}:{github_branch}",
        )
        self.github_deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

        CfnOutput(
            self,
            "GitHubDeployRoleArn",
            value=self.github_deploy_role.role_arn,
            description="GitHub Actions OIDC role ARN for AWS deployment",
        )

        print("\n" + "=" * 60)
        print("✅ IAM Stack Created - Single Unified Role")
        print(f"   Role ARN: {self.role.role_arn}")
        print("   This role can be used for both Execution and Task")
        print("=" * 60 + "\n")
