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
    Creates DynamoDB tables:
    - SessionTable: Agent memory and conversation history
    - TradesTable: Trade history and signals
    - LearningTable: Pattern analysis and confidence adjustments
    - MarketStateTable: Overnight analysis, global cues, pre-market watchlist
    - SignalsTable: every signal emitted by the signal engine
    - RiskEventsTable: deterministic risk approvals/rejections
    - OrdersTable: broker/proxy order state
    - FillsTable: execution fills
    - PositionsTable: latest intraday position state
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
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
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
        # DYNAMODB TABLE 5: Signals Table (Pre-risk Signal Audit)
        # ============================================================

        signals_table_name = dynamodb_config.get(
            "signals_table",
            f"svc-trd-signals-{environment}"
        )

        self.signals_table = dynamodb.Table(
            self, "SignalsTable",
            table_name=signals_table_name,
            partition_key=dynamodb.Attribute(name="signal_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        self.signals_table.add_global_secondary_index(
            index_name="symbol-created-index",
            partition_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
        )

        self.signals_table.add_global_secondary_index(
            index_name="session-created-index",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
        )

        print(f"✅ Created Signals Table: {signals_table_name}")

        # ============================================================
        # DYNAMODB TABLE 6: Risk Events Table (Risk Decision Audit)
        # ============================================================

        risk_events_table_name = dynamodb_config.get(
            "risk_events_table",
            f"svc-trd-risk-events-{environment}"
        )

        self.risk_events_table = dynamodb.Table(
            self, "RiskEventsTable",
            table_name=risk_events_table_name,
            partition_key=dynamodb.Attribute(name="risk_decision_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        self.risk_events_table.add_global_secondary_index(
            index_name="signal-created-index",
            partition_key=dynamodb.Attribute(name="signal_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
        )

        self.risk_events_table.add_global_secondary_index(
            index_name="status-created-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="created_at", type=dynamodb.AttributeType.STRING),
        )

        print(f"✅ Created Risk Events Table: {risk_events_table_name}")

        # ============================================================
        # DYNAMODB TABLE 7: Orders Table (Order State Audit)
        # ============================================================

        orders_table_name = dynamodb_config.get(
            "orders_table",
            f"svc-trd-orders-{environment}"
        )

        self.orders_table = dynamodb.Table(
            self, "OrdersTable",
            table_name=orders_table_name,
            partition_key=dynamodb.Attribute(name="client_order_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        self.orders_table.add_global_secondary_index(
            index_name="symbol-updated-index",
            partition_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
        )

        self.orders_table.add_global_secondary_index(
            index_name="status-updated-index",
            partition_key=dynamodb.Attribute(name="status", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="updated_at", type=dynamodb.AttributeType.STRING),
        )

        print(f"✅ Created Orders Table: {orders_table_name}")

        # ============================================================
        # DYNAMODB TABLE 8: Fills Table (Execution Fill Audit)
        # ============================================================

        fills_table_name = dynamodb_config.get(
            "fills_table",
            f"svc-trd-fills-{environment}"
        )

        self.fills_table = dynamodb.Table(
            self, "FillsTable",
            table_name=fills_table_name,
            partition_key=dynamodb.Attribute(name="fill_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filled_at", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        self.fills_table.add_global_secondary_index(
            index_name="client-order-filled-index",
            partition_key=dynamodb.Attribute(name="client_order_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filled_at", type=dynamodb.AttributeType.STRING),
        )

        self.fills_table.add_global_secondary_index(
            index_name="symbol-filled-index",
            partition_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="filled_at", type=dynamodb.AttributeType.STRING),
        )

        print(f"✅ Created Fills Table: {fills_table_name}")

        # ============================================================
        # DYNAMODB TABLE 9: Positions Table (Latest Position State)
        # ============================================================

        positions_table_name = dynamodb_config.get(
            "positions_table",
            f"svc-trd-positions-{environment}"
        )

        self.positions_table = dynamodb.Table(
            self, "PositionsTable",
            table_name=positions_table_name,
            partition_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            point_in_time_recovery_specification=dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            ),
        )

        self.positions_table.add_global_secondary_index(
            index_name="session-symbol-index",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
        )

        print(f"✅ Created Positions Table: {positions_table_name}")

        # ============================================================
        # OUTPUTS
        # ============================================================
        
        CfnOutput(self, "CodeBucketName", value=self.code_bucket.bucket_name)
        CfnOutput(self, "SessionTableName", value=self.session_table.table_name)
        CfnOutput(self, "TradesTableName", value=self.trades_table.table_name)
        CfnOutput(self, "LearningTableName", value=self.learning_table.table_name)
        CfnOutput(self, "MarketStateTableName", value=self.market_state_table.table_name)
        CfnOutput(self, "SignalsTableName", value=self.signals_table.table_name)
        CfnOutput(self, "RiskEventsTableName", value=self.risk_events_table.table_name)
        CfnOutput(self, "OrdersTableName", value=self.orders_table.table_name)
        CfnOutput(self, "FillsTableName", value=self.fills_table.table_name)
        CfnOutput(self, "PositionsTableName", value=self.positions_table.table_name)
        
        print(f"\n📋 Storage Stack Summary:")
        print(f"   S3 Bucket (imported): {bucket_name}")
        print(f"   Session Table: {session_table_name}")
        print(f"   Trades Table: {trades_table_name}")
        print(f"   Learning Table: {learning_table_name}")
        print(f"   Market State Table: {market_state_table_name}")
        print(f"   Signals Table: {signals_table_name}")
        print(f"   Risk Events Table: {risk_events_table_name}")
        print(f"   Orders Table: {orders_table_name}")
        print(f"   Fills Table: {fills_table_name}")
        print(f"   Positions Table: {positions_table_name}")
