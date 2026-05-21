from aws_cdk import (
    Stack, RemovalPolicy, Duration, CfnOutput,
    aws_s3 as s3,
    aws_dynamodb as dynamodb
)
from constructs import Construct

# S3 + DynamoDB)

class TradingStorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # S3 Bucket for agent code and data
        self.code_bucket = s3.Bucket(
            self, "TradingCodeBucket",
            removal_policy=RemovalPolicy.DESTROY,
            auto_delete_objects=True,
            versioned=True,
        )

        # DynamoDB Table for session memory (Strands AgentCore)
        self.session_table = dynamodb.Table(
            self, "TradingSessionTable",
            partition_key=dynamodb.Attribute(name="sessionId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

        # DynamoDB Table for trade history
        self.trades_table = dynamodb.Table(
            self, "TradesTable",
            partition_key=dynamodb.Attribute(name="tradeId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )

        # Outputs
        CfnOutput(self, "CodeBucketName", value=self.code_bucket.bucket_name)
        CfnOutput(self, "SessionTableName", value=self.session_table.table_name)
        CfnOutput(self, "TradesTableName", value=self.trades_table.table_name)