"""
Agent Runtime Stack - Creates IAM Role for your Strands Multi-Agent Trading System

Note: AgentCore Runtime deployment is handled separately using the AgentCore CLI.
This stack only creates the IAM role and permissions.
"""

from aws_cdk import (
    Stack, CfnOutput, 
    aws_iam as iam,
    aws_s3 as s3,
    aws_dynamodb as dynamodb
)
from constructs import Construct


class TradingAgentRuntimeStack(Stack):
    """
    Creates IAM Role with permissions for the Strands Multi-Agent Trading System.
    """
    
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        code_bucket: s3.IBucket,           # Existing S3 bucket (imported)
        session_table: dynamodb.Table,      # DynamoDB table for agent memory
        trades_table: dynamodb.Table,       # DynamoDB table for trade history
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # IAM ROLE FOR THE AGENT
        # ============================================================
        
        self.agent_role = iam.Role(
            self, "svc-trd-agent-role",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            description="IAM Role for Strands Multi-Agent Trading System",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
            ]
        )

        # ============================================================
        # BEDROCK PERMISSIONS (Claude Models)
        # ============================================================
        
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream"
                ],
                resources=[
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-haiku-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-sonnet-*",
                    f"arn:aws:bedrock:{self.region}::foundation-model/anthropic.claude-3-opus-*"
                ]
            )
        )

        # ============================================================
        # S3 PERMISSIONS (Existing Bucket)
        # ============================================================
        
        code_bucket.grant_read_write(self.agent_role)
        
        # ============================================================
        # DYNAMODB PERMISSIONS
        # ============================================================
        
        session_table.grant_read_write_data(self.agent_role)
        trades_table.grant_read_write_data(self.agent_role)

        # ============================================================
        # SECRETS MANAGER PERMISSIONS
        # ============================================================
        
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"],  # TODO: Restrict to specific secrets
            )
        )

        # ============================================================
        # OUTPUTS
        # ============================================================
        
        # Only ONE output with each unique name
        CfnOutput(
            self, "AgentRoleArnOutput",  # ← Unique name
            value=self.agent_role.role_arn,
            description="IAM Role ARN for the agent - use this when deploying with AgentCore CLI"
        )
        
        CfnOutput(
            self, "CodeBucketNameOutput",  # ← Unique name
            value=code_bucket.bucket_name,
            description="S3 Bucket name for agent code storage"
        )
        
        CfnOutput(
            self, "SessionTableNameOutput",  # ← Unique name
            value=session_table.table_name,
            description="DynamoDB Session Table name"
        )
        
        CfnOutput(
            self, "TradesTableNameOutput",  # ← Unique name
            value=trades_table.table_name,
            description="DynamoDB Trades Table name"
        )