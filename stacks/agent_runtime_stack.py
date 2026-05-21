from aws_cdk import (
    Stack, Duration, CfnOutput, 
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
    aws_dynamodb as dynamodb
)
from constructs import Construct

# Agent Runtime Stack (Bedrock AgentCore)

class TradingAgentRuntimeStack(Stack):
    def __init__(
        self, 
        scope: Construct, 
        construct_id: str,
        code_bucket: s3.Bucket,
        session_table: dynamodb.Table,
        trades_table: dynamodb.Table,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # IAM Role for Agent Runtime
        self.agent_role = iam.Role(
            self, "AgentRuntimeRole",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
            ]
        )

        # Grant S3 permissions
        code_bucket.grant_read_write(self.agent_role)
        
        # Grant DynamoDB permissions
        session_table.grant_read_write_data(self.agent_role)
        trades_table.grant_read_write_data(self.agent_role)

        # Additional permissions for external APIs
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"]  # Restrict to specific secrets in production
            )
        )

        # Note: AgentCore Runtime is currently available through the CDK L1 construct
        # For Python, we use CfnResource for the AgentCore runtime
        # As of now, the AgentCore Python CDK constructs are in developer preview
        
        from aws_cdk import CustomResource
        
        # Custom resource to invoke AgentCore runtime creation
        # This is a placeholder - the actual AgentCore Python CDK module
        # will be available via `@cdklabs/bedrock-agentcore`
        
        CfnOutput(self, "AgentRoleArn", value=self.agent_role.role_arn)