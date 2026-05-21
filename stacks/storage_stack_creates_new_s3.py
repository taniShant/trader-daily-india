from aws_cdk import (
    Stack, RemovalPolicy, CfnOutput,
    aws_s3 as s3,
    aws_dynamodb as dynamodb
)
from constructs import Construct

class TradingStorageStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ❌ DON'T create a new bucket - import existing one instead
        # self.code_bucket = s3.Bucket(...)  # REMOVE THIS
        
        # ✅ Import existing S3 bucket
        self.code_bucket = s3.Bucket.from_bucket_name(
            self, 
            "ExistingCodeBucket",
            bucket_name="svc-s3-dev-632943041262-modelartifact"  # Your existing bucket
        )

        # ✅ Keep DynamoDB tables (these are new)
        self.session_table = dynamodb.Table(
            self, "TradingSessionTable",
            partition_key=dynamodb.Attribute(name="sessionId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )

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