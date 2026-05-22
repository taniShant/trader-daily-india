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

    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

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
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-haiku-*",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-sonnet-*",
                    "arn:aws:bedrock:*::foundation-model/anthropic.claude-3-opus-*",
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

        print("\n" + "=" * 60)
        print("✅ IAM Stack Created - Single Unified Role")
        print(f"   Role ARN: {self.role.role_arn}")
        print("   This role can be used for both Execution and Task")
        print("=" * 60 + "\n")