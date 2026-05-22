from aws_cdk import (
    Stack, RemovalPolicy, Duration, CfnOutput,
    aws_s3 as s3,
    aws_dynamodb as dynamodb
)
from constructs import Construct

class TradingStorageStack(Stack):
    """
    Storage Stack - Imports existing S3 bucket, creates DynamoDB tables.
    
    Reads S3 bucket name from config (imports existing, does not create).
    Creates 4 DynamoDB tables:
    - SessionTable: Agent memory and conversation history
    - TradesTable: Trade history and signals
    - LearningTable: Pattern analysis and confidence adjustments
    - MarketStateTable: Overnight analysis, global cues, pre-market watchlist
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # LOAD CONFIGURATION
        # ============================================================
        
        environment = config.get("environment", "dev")
        s3_config = config.get("s3", {})
        dynamodb_config = config.get("dynamodb", {})
        
        # S3 bucket name from config (imported, not created)
        bucket_name = s3_config.get("code_bucket")
        
        if not bucket_name:
            raise ValueError("S3 bucket name not found in config under 's3.code_bucket'")
        
        print(f"📦 Importing S3 bucket: {bucket_name}")
        
        # ============================================================
        # IMPORT EXISTING S3 BUCKET (NO CREATION)
        # ============================================================
        
        self.code_bucket = s3.Bucket.from_bucket_name(
            self, 
            "ExistingCodeBucket",
            bucket_name=bucket_name
        )

        # ============================================================
        # DYNAMODB TABLE 1: Session Table (Agent Memory)
        # ============================================================
        
        session_table_name = dynamodb_config.get(
            "session_table", 
            f"svc-trd-sessions-{environment}"
        )
        
        self.session_table = dynamodb.Table(
            self, "SessionTable",
            table_name=session_table_name,
            partition_key=dynamodb.Attribute(name="sessionId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            time_to_live_attribute="ttl",
        )
        
        print(f"✅ Created Session Table: {session_table_name}")

        # ============================================================
        # DYNAMODB TABLE 2: Trades Table (Trade History)
        # ============================================================
        
        trades_table_name = dynamodb_config.get(
            "trades_table", 
            f"svc-trd-trades-{environment}"
        )
        
        self.trades_table = dynamodb.Table(
            self, "TradesTable",
            table_name=trades_table_name,
            partition_key=dynamodb.Attribute(name="tradeId", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery=True,  # Enable for audit trail
        )
        
        # GSI for stock symbol queries
        self.trades_table.add_global_secondary_index(
            index_name="stock-index",
            partition_key=dynamodb.Attribute(name="stock_symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
        )
        
        # GSI for P&L analysis
        self.trades_table.add_global_secondary_index(
            index_name="pnl-index",
            partition_key=dynamodb.Attribute(name="action", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="pnl", type=dynamodb.AttributeType.NUMBER),
        )
        
        print(f"✅ Created Trades Table: {trades_table_name}")

        # ============================================================
        # DYNAMODB TABLE 3: Learning Table (Pattern Analysis)
        # ============================================================
        
        learning_table_name = dynamodb_config.get(
            "learning_table", 
            f"svc-trd-learning-{environment}"
        )
        
        self.learning_table = dynamodb.Table(
            self, "LearningTable",
            table_name=learning_table_name,
            partition_key=dynamodb.Attribute(name="pattern_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        
        # GSI for win rate analysis
        self.learning_table.add_global_secondary_index(
            index_name="winrate-index",
            partition_key=dynamodb.Attribute(name="pattern_type", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="win_rate", type=dynamodb.AttributeType.NUMBER),
        )
        
        print(f"✅ Created Learning Table: {learning_table_name}")

        # ============================================================
        # DYNAMODB TABLE 4: Market State Table (Overnight Analysis)
        # ============================================================
        
        market_state_table_name = dynamodb_config.get(
            "market_state_table", 
            f"svc-trd-market-state-{environment}"
        )
        
        self.market_state_table = dynamodb.Table(
            self, "MarketStateTable",
            table_name=market_state_table_name,
            partition_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="timestamp", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
        )
        
        # GSI for sentiment analysis
        self.market_state_table.add_global_secondary_index(
            index_name="sentiment-index",
            partition_key=dynamodb.Attribute(name="global_sentiment", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
        )
        
        print(f"✅ Created Market State Table: {market_state_table_name}")

        # ============================================================
        # OUTPUTS
        # ============================================================
        
        CfnOutput(self, "CodeBucketName", value=self.code_bucket.bucket_name)
        CfnOutput(self, "SessionTableName", value=self.session_table.table_name)
        CfnOutput(self, "TradesTableName", value=self.trades_table.table_name)
        CfnOutput(self, "LearningTableName", value=self.learning_table.table_name)
        CfnOutput(self, "MarketStateTableName", value=self.market_state_table.table_name)
        
        print(f"\n📋 Storage Stack Summary:")
        print(f"   S3 Bucket (imported): {bucket_name}")
        print(f"   Session Table: {session_table_name}")
        print(f"   Trades Table: {trades_table_name}")
        print(f"   Learning Table: {learning_table_name}")
        print(f"   Market State Table: {market_state_table_name}")