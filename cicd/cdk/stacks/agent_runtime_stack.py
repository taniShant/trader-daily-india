from aws_cdk import (
    Stack, Duration, CfnOutput, RemovalPolicy,
    aws_iam as iam,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_cloudwatch as cloudwatch,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
    aws_events as events,
    aws_events_targets as events_targets,
    aws_logs as logs,
    aws_elasticloadbalancingv2 as elbv2,
    aws_ec2 as ec2,
)
from constructs import Construct

class TradingAgentRuntimeStack(Stack):
    """
    Agent Runtime Stack - Deploys ECS Fargate services for:
    - Trading Bot (runs in private subnet, uses NAT Gateway)
    - Dashboard (public facing via Load Balancer)
    
    Reads configuration from config file (dev.json or prod.json)
    """

    def __init__(
        self,
        scope: Construct,
        construct_id: str,
        vpc: ec2.Vpc,
        ecs_security_group: ec2.SecurityGroup,
        load_balancer_security_group: ec2.SecurityGroup,
        public_subnet: ec2.Subnet,
        private_subnet: ec2.Subnet,
        code_bucket: s3.IBucket,
        session_table: dynamodb.Table,
        trades_table: dynamodb.Table,
        learning_table: dynamodb.Table,
        market_state_table: dynamodb.Table,
        signals_table: dynamodb.Table,
        risk_events_table: dynamodb.Table,
        orders_table: dynamodb.Table,
        fills_table: dynamodb.Table,
        positions_table: dynamodb.Table,
        config: dict,
        role: iam.Role,  
        public_subnets: list[ec2.ISubnet] | None = None,
        private_subnets: list[ec2.ISubnet] | None = None,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        self.task_role = role
        self.execution_role = role
        public_subnets = public_subnets or [public_subnet]
        private_subnets = private_subnets or [private_subnet]

        # ============================================================
        # LOAD CONFIGURATION
        # ============================================================
        
        environment = config.get("environment", "dev")
        trading_config = config.get("trading", {})
        scheduled_tasks_config = config.get("scheduled_tasks", {})
        bedrock_config = config.get("bedrock", {})
        cross_account_bedrock_config = config.get("cross_account_bedrock", {})
        icici_config = config.get("icici", {})
        oracle_config = config.get("oracle", {})
        apis_config = config.get("apis", {})
        
        paper_trading = trading_config.get("paper_trading", True)
        capital = trading_config.get("capital", 100000)
        analysis_interval = trading_config.get("analysis_interval_seconds", 180)
        market_closed_poll_seconds = trading_config.get("market_closed_poll_seconds", 60)
        min_confidence = trading_config.get("min_confidence_threshold", 70)
        max_daily_loss_percent = trading_config.get("max_daily_loss_percent", 4)
        max_position_size_percent = trading_config.get("max_position_size_percent", 10)
        max_quantity_per_order = trading_config.get("max_quantity_per_order", 50)
        watchlist_size = trading_config.get("watchlist_size", 10)
        alpha_universe_size = trading_config.get("alpha_universe_size", max(40, watchlist_size))
        deep_analysis_size = trading_config.get("deep_analysis_size", watchlist_size)
        alpha_scan_workers = trading_config.get("alpha_scan_workers", 8)
        micro_trading_enabled = trading_config.get("micro_trading_enabled", False)
        micro_scan_interval_seconds = trading_config.get("micro_scan_interval_seconds", 30)
        micro_exit_check_interval_seconds = trading_config.get("micro_exit_check_interval_seconds", 30)
        micro_max_hold_minutes = trading_config.get("micro_max_hold_minutes", 10)
        micro_min_confidence = trading_config.get("micro_min_confidence", 72)
        micro_min_relative_volume = trading_config.get("micro_min_relative_volume", 1.5)
        micro_min_continuation_relative_volume = trading_config.get(
            "micro_min_continuation_relative_volume",
            3.0,
        )
        micro_require_continuation_confirmation = trading_config.get(
            "micro_require_continuation_confirmation",
            True,
        )
        micro_exceptional_continuation_relative_volume = trading_config.get(
            "micro_exceptional_continuation_relative_volume",
            8.0,
        )
        micro_max_continuation_vwap_extension_atr = trading_config.get(
            "micro_max_continuation_vwap_extension_atr",
            2.0,
        )
        micro_pullback_min_impulse_extension_atr = trading_config.get(
            "micro_pullback_min_impulse_extension_atr",
            2.0,
        )
        micro_pullback_max_entry_extension_atr = trading_config.get(
            "micro_pullback_max_entry_extension_atr",
            1.1,
        )
        micro_pullback_min_relative_volume = trading_config.get(
            "micro_pullback_min_relative_volume",
            1.2,
        )
        micro_max_candle_age_seconds = trading_config.get("micro_max_candle_age_seconds", 180)
        micro_max_symbols_per_cycle = trading_config.get("micro_max_symbols_per_cycle", 40)
        micro_reentry_cooldown_seconds = trading_config.get("micro_reentry_cooldown_seconds", 600)
        micro_diagnostic_top_n = trading_config.get("micro_diagnostic_top_n", 5)
        micro_continuation_target_pct = trading_config.get("micro_continuation_target_pct", 0.003)
        micro_continuation_stop_pct = trading_config.get("micro_continuation_stop_pct", 0.0015)
        micro_continuation_max_hold_minutes = trading_config.get("micro_continuation_max_hold_minutes", 6)
        micro_vwap_target_pct = trading_config.get("micro_vwap_target_pct", 0.0035)
        micro_vwap_stop_pct = trading_config.get("micro_vwap_stop_pct", 0.0018)
        micro_vwap_max_hold_minutes = trading_config.get("micro_vwap_max_hold_minutes", 8)
        micro_opening_range_target_pct = trading_config.get("micro_opening_range_target_pct", 0.005)
        micro_opening_range_stop_pct = trading_config.get("micro_opening_range_stop_pct", 0.0025)
        micro_opening_range_max_hold_minutes = trading_config.get("micro_opening_range_max_hold_minutes", 10)
        micro_early_exit_enabled = trading_config.get("micro_early_exit_enabled", True)
        micro_invalidation_min_hold_seconds = trading_config.get("micro_invalidation_min_hold_seconds", 120)
        micro_loss_throttle_count = trading_config.get("micro_loss_throttle_count", 2)
        micro_loss_throttle_window_minutes = trading_config.get("micro_loss_throttle_window_minutes", 30)
        micro_cost_brokerage_bps = trading_config.get("micro_cost_brokerage_bps", 1)
        micro_cost_taxes_bps = trading_config.get("micro_cost_taxes_bps", 2)
        micro_cost_slippage_bps = trading_config.get("micro_cost_slippage_bps", 2)
        micro_min_expected_net_profit = trading_config.get("micro_min_expected_net_profit", 0)
        micro_min_expected_net_profit_bps = trading_config.get("micro_min_expected_net_profit_bps", 0)
        micro_min_target_to_cost_ratio = trading_config.get("micro_min_target_to_cost_ratio", 0)
        micro_setup_loss_throttle_count = trading_config.get("micro_setup_loss_throttle_count", 2)
        micro_setup_loss_throttle_min_trades = trading_config.get("micro_setup_loss_throttle_min_trades", 2)
        position_reconciliation_enabled = trading_config.get("position_reconciliation_enabled", True)
        run_startup_overnight_analysis = trading_config.get("run_startup_overnight_analysis", False)
        
        static_ip = oracle_config.get("static_ip", icici_config.get("static_ip"))
        oracle_proxy_base_url = oracle_config.get("execution_proxy_base_url", "")
        oracle_proxy_health_url = oracle_config.get("execution_proxy_health_url", "")
        oracle_proxy_shared_secret = oracle_config.get("execution_proxy_shared_secret", "")
        oracle_collector_base_url = oracle_config.get("collector_base_url", "")
        oracle_collector_health_url = oracle_config.get("collector_health_url", "")
        bedrock_model = bedrock_config.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0")
        bedrock_fast_model = bedrock_config.get("fast_model_id", bedrock_model)
        bedrock_reasoning_model = bedrock_config.get("reasoning_model_id", bedrock_model)
        bedrock_deep_research_model = bedrock_config.get("deep_research_model_id", bedrock_model)
        bedrock_region = bedrock_config.get("region", "eu-west-2")
        
        print(f"\n📋 Agent Runtime Configuration:")
        print(f"   Environment: {environment}")
        print(f"   Paper Trading: {paper_trading}")
        print(f"   Capital: ₹{capital:,.2f}")
        print(f"   Analysis Interval: {analysis_interval} seconds")
        print(f"   Market Closed Poll: {market_closed_poll_seconds} seconds")
        print(f"   Min Confidence: {min_confidence}%")
        print(f"   Max Daily Loss: {max_daily_loss_percent}%")
        print(f"   Max Position Size: {max_position_size_percent}%")
        print(f"   Max Quantity Per Order: {max_quantity_per_order}")
        print(f"   Watchlist Size: {watchlist_size}")
        print(f"   Alpha Universe Size: {alpha_universe_size}")
        print(f"   Deep Analysis Size: {deep_analysis_size}")
        print(f"   Alpha Scan Workers: {alpha_scan_workers}")
        print(f"   Micro Trading Enabled: {micro_trading_enabled}")
        print(f"   Micro Scan Interval: {micro_scan_interval_seconds} seconds")
        print(f"   Micro Exit Check Interval: {micro_exit_check_interval_seconds} seconds")
        print(f"   Micro Symbols Per Cycle: {micro_max_symbols_per_cycle}")
        print(f"   Micro Min Relative Volume: {micro_min_relative_volume}")
        print(f"   Micro Continuation Min Relative Volume: {micro_min_continuation_relative_volume}")
        print(f"   Micro Continuation Confirmation: {micro_require_continuation_confirmation}")
        print(f"   Micro Exceptional Continuation RV: {micro_exceptional_continuation_relative_volume}")
        print(f"   Micro Continuation Max VWAP Extension: {micro_max_continuation_vwap_extension_atr} ATR")
        print(
            "   Micro VWAP Pullback: "
            f"impulse>={micro_pullback_min_impulse_extension_atr} ATR, "
            f"entry_ext<={micro_pullback_max_entry_extension_atr} ATR, "
            f"rv>={micro_pullback_min_relative_volume}x"
        )
        print(f"   Micro Max Candle Age: {micro_max_candle_age_seconds} seconds")
        print(
            "   Micro Setup Brackets: "
            f"continuation={micro_continuation_target_pct}/{micro_continuation_stop_pct}/{micro_continuation_max_hold_minutes}m, "
            f"vwap={micro_vwap_target_pct}/{micro_vwap_stop_pct}/{micro_vwap_max_hold_minutes}m, "
            f"orb={micro_opening_range_target_pct}/{micro_opening_range_stop_pct}/{micro_opening_range_max_hold_minutes}m"
        )
        print(f"   Micro Early Exit Enabled: {micro_early_exit_enabled}")
        print(f"   Micro Loss Throttle: {micro_loss_throttle_count} losses / {micro_loss_throttle_window_minutes} minutes")
        print(
            "   Micro Setup Loss Throttle: "
            f"{micro_setup_loss_throttle_count} losses after {micro_setup_loss_throttle_min_trades} trades"
        )
        print(
            "   Micro Entry Economics: "
            f"min_net=₹{micro_min_expected_net_profit}, "
            f"min_net_bps={micro_min_expected_net_profit_bps}, "
            f"target_cost_ratio>={micro_min_target_to_cost_ratio}"
        )
        print(f"   Position Reconciliation Enabled: {position_reconciliation_enabled}")
        print(f"   Startup Overnight Analysis: {run_startup_overnight_analysis}")
        print(f"   Oracle Static IP: {static_ip}")
        print(f"   Oracle Execution Proxy: {oracle_proxy_base_url}")
        print(f"   Oracle Collector: {oracle_collector_base_url}")
        print(f"   Bedrock Default Model: {bedrock_model}")
        print(f"   Bedrock Fast Model: {bedrock_fast_model}")
        print(f"   Bedrock Reasoning Model: {bedrock_reasoning_model}")
        print(f"   Bedrock Deep Research Model: {bedrock_deep_research_model}")

        # ============================================================
        # IAM ROLE FOR ECS TASKS
        # ============================================================

        self.agent_role = role.without_policy_updates()

        # ============================================================
        # ECR REPOSITORIES- Reuse (name from dev.json)
        # ============================================================
        ecr_repo_name = config.get("ecr", {}).get("repository_name", "trading-system")
        ecr_repo = ecr.Repository.from_repository_name(
            self,
            "ExistingTradingSystemRepository",
            repository_name=ecr_repo_name
        )

        print(f"📦 Using existing ECR repository: {ecr_repo_name}")

        # ============================================================
        # ECS CLUSTER
        # ============================================================
        
        cluster = ecs.Cluster(
            self, "TradingCluster",
            cluster_name=f"trading-cluster-{environment}",
            vpc=vpc
        )

        # ============================================================
        # TRADING BOT TASK DEFINITION (Runs in Private Subnet)
        # ============================================================
        
        trading_task = ecs.FargateTaskDefinition(
            self, "TradingTaskDefinition",
            memory_limit_mib=2048,
            cpu=1024,
            task_role=self.agent_role,
            execution_role=self.agent_role
        )

        # Environment variables for trading bot
        trading_env = {
            "AWS_REGION": self.region,
            "ENVIRONMENT": environment,
            "PAPER_TRADING": str(paper_trading),
            "CAPITAL": str(capital),
            "ANALYSIS_INTERVAL_SECONDS": str(analysis_interval),
            "MARKET_CLOSED_POLL_SECONDS": str(market_closed_poll_seconds),
            "MIN_CONFIDENCE_THRESHOLD": str(min_confidence),
            "MAX_DAILY_LOSS_PERCENT": str(max_daily_loss_percent),
            "MAX_POSITION_SIZE_PERCENT": str(max_position_size_percent),
            "MAX_QUANTITY_PER_ORDER": str(max_quantity_per_order),
            "WATCHLIST_SIZE": str(watchlist_size),
            "ALPHA_UNIVERSE_SIZE": str(alpha_universe_size),
            "DEEP_ANALYSIS_SIZE": str(deep_analysis_size),
            "ALPHA_SCAN_WORKERS": str(alpha_scan_workers),
            "MICRO_TRADING_ENABLED": str(micro_trading_enabled),
            "MICRO_SCAN_INTERVAL_SECONDS": str(micro_scan_interval_seconds),
            "MICRO_EXIT_CHECK_INTERVAL_SECONDS": str(micro_exit_check_interval_seconds),
            "MICRO_MAX_HOLD_MINUTES": str(micro_max_hold_minutes),
            "MICRO_MIN_CONFIDENCE": str(micro_min_confidence),
            "MICRO_MIN_RELATIVE_VOLUME": str(micro_min_relative_volume),
            "MICRO_MIN_CONTINUATION_RELATIVE_VOLUME": str(micro_min_continuation_relative_volume),
            "MICRO_REQUIRE_CONTINUATION_CONFIRMATION": str(micro_require_continuation_confirmation),
            "MICRO_EXCEPTIONAL_CONTINUATION_RELATIVE_VOLUME": str(micro_exceptional_continuation_relative_volume),
            "MICRO_MAX_CONTINUATION_VWAP_EXTENSION_ATR": str(micro_max_continuation_vwap_extension_atr),
            "MICRO_PULLBACK_MIN_IMPULSE_EXTENSION_ATR": str(micro_pullback_min_impulse_extension_atr),
            "MICRO_PULLBACK_MAX_ENTRY_EXTENSION_ATR": str(micro_pullback_max_entry_extension_atr),
            "MICRO_PULLBACK_MIN_RELATIVE_VOLUME": str(micro_pullback_min_relative_volume),
            "MICRO_MAX_CANDLE_AGE_SECONDS": str(micro_max_candle_age_seconds),
            "MICRO_MAX_SYMBOLS_PER_CYCLE": str(micro_max_symbols_per_cycle),
            "MICRO_REENTRY_COOLDOWN_SECONDS": str(micro_reentry_cooldown_seconds),
            "MICRO_DIAGNOSTIC_TOP_N": str(micro_diagnostic_top_n),
            "MICRO_CONTINUATION_TARGET_PCT": str(micro_continuation_target_pct),
            "MICRO_CONTINUATION_STOP_PCT": str(micro_continuation_stop_pct),
            "MICRO_CONTINUATION_MAX_HOLD_MINUTES": str(micro_continuation_max_hold_minutes),
            "MICRO_VWAP_TARGET_PCT": str(micro_vwap_target_pct),
            "MICRO_VWAP_STOP_PCT": str(micro_vwap_stop_pct),
            "MICRO_VWAP_MAX_HOLD_MINUTES": str(micro_vwap_max_hold_minutes),
            "MICRO_OPENING_RANGE_TARGET_PCT": str(micro_opening_range_target_pct),
            "MICRO_OPENING_RANGE_STOP_PCT": str(micro_opening_range_stop_pct),
            "MICRO_OPENING_RANGE_MAX_HOLD_MINUTES": str(micro_opening_range_max_hold_minutes),
            "MICRO_EARLY_EXIT_ENABLED": str(micro_early_exit_enabled),
            "MICRO_INVALIDATION_MIN_HOLD_SECONDS": str(micro_invalidation_min_hold_seconds),
            "MICRO_LOSS_THROTTLE_COUNT": str(micro_loss_throttle_count),
            "MICRO_LOSS_THROTTLE_WINDOW_MINUTES": str(micro_loss_throttle_window_minutes),
            "MICRO_COST_BROKERAGE_BPS": str(micro_cost_brokerage_bps),
            "MICRO_COST_TAXES_BPS": str(micro_cost_taxes_bps),
            "MICRO_COST_SLIPPAGE_BPS": str(micro_cost_slippage_bps),
            "MICRO_MIN_EXPECTED_NET_PROFIT": str(micro_min_expected_net_profit),
            "MICRO_MIN_EXPECTED_NET_PROFIT_BPS": str(micro_min_expected_net_profit_bps),
            "MICRO_MIN_TARGET_TO_COST_RATIO": str(micro_min_target_to_cost_ratio),
            "MICRO_SETUP_LOSS_THROTTLE_COUNT": str(micro_setup_loss_throttle_count),
            "MICRO_SETUP_LOSS_THROTTLE_MIN_TRADES": str(micro_setup_loss_throttle_min_trades),
            "POSITION_RECONCILIATION_ENABLED": str(position_reconciliation_enabled),
            "RUN_STARTUP_OVERNIGHT_ANALYSIS": str(run_startup_overnight_analysis),
            "STATIC_IP": static_ip,
            "ORACLE_STATIC_IP": static_ip,
            "ORACLE_EXECUTION_PROXY_BASE_URL": oracle_proxy_base_url,
            "ORACLE_EXECUTION_PROXY_HEALTH_URL": oracle_proxy_health_url,
            "ORACLE_PROXY_SHARED_SECRET": oracle_proxy_shared_secret,
            "ORACLE_COLLECTOR_BASE_URL": oracle_collector_base_url,
            "ORACLE_COLLECTOR_HEALTH_URL": oracle_collector_health_url,
            "BEDROCK_MODEL_ID": bedrock_model,
            "BEDROCK_FAST_MODEL_ID": bedrock_fast_model,
            "BEDROCK_REASONING_MODEL_ID": bedrock_reasoning_model,
            "BEDROCK_DEEP_RESEARCH_MODEL_ID": bedrock_deep_research_model,
            "BEDROCK_REGION": bedrock_region,
            "CROSS_ACCOUNT_BEDROCK_ENABLED": str(cross_account_bedrock_config.get("enabled", False)),
            "CROSS_ACCOUNT_BEDROCK_ROLE_ARN": cross_account_bedrock_config.get("role_arn", ""),
            "CROSS_ACCOUNT_BEDROCK_EXTERNAL_ID": cross_account_bedrock_config.get("external_id", ""),
            "CROSS_ACCOUNT_BEDROCK_REGION": cross_account_bedrock_config.get("region", bedrock_region),
            "CROSS_ACCOUNT_BEDROCK_SESSION_NAME": cross_account_bedrock_config.get(
                "session_name",
                "trd-bedrock-runtime",
            ),
            "SESSIONS_TABLE": session_table.table_name,
            "TRADES_TABLE": trades_table.table_name,
            "LEARNING_TABLE": learning_table.table_name,
            "MARKET_STATE_TABLE": market_state_table.table_name,
            "SIGNALS_TABLE": signals_table.table_name,
            "RISK_EVENTS_TABLE": risk_events_table.table_name,
            "ORDERS_TABLE": orders_table.table_name,
            "FILLS_TABLE": fills_table.table_name,
            "POSITIONS_TABLE": positions_table.table_name,
            "CODE_BUCKET": code_bucket.bucket_name,
            "NEWS_API_KEY": apis_config.get("news_api_key", ""),
            "TWITTER_BEARER_TOKEN": apis_config.get("twitter_bearer_token", ""),
            "REDDIT_CLIENT_ID": apis_config.get("reddit_client_id", ""),
            "REDDIT_CLIENT_SECRET": apis_config.get("reddit_client_secret", ""),
        }

        trading_log_group = logs.LogGroup(
            self,
            "TradingBotLogs",
            log_group_name=f"/ecs/trading-bot-{environment}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        trading_task.add_container(
            "TradingBotContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, "trading-bot-latest"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="trading-bot",
                log_group=trading_log_group
            ),
            environment=trading_env,
            port_mappings=[ecs.PortMapping(container_port=9090, name="metrics")]
        )

        # EventBridge one-shot scheduled task role.
        # This starts explicit scheduled actions without scaling the singleton service.
        schedule_role = iam.Role(
            self,
            "TradingScheduleEventRole",
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            description="Allows EventBridge to run scheduled trading ECS tasks",
        )
        schedule_role.add_to_policy(
            iam.PolicyStatement(
                actions=["ecs:RunTask"],
                resources=[trading_task.task_definition_arn],
            )
        )
        schedule_role.add_to_policy(
            iam.PolicyStatement(
                actions=["iam:PassRole"],
                resources=[self.agent_role.role_arn],
            )
        )

        # Trading Bot Service: public subnet egress. ICICI live execution still goes through Oracle.
        trading_service = ecs.FargateService(
            self, "TradingBotService",
            cluster=cluster,
            task_definition=trading_task,
            desired_count=1,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=100,
            max_healthy_percent=200,
            assign_public_ip=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[ecs_security_group],
            service_name=f"trading-bot-{environment}"
        )

        # A live trading bot must remain singleton unless a leader-lock is added.
        # Do not add task autoscaling here; multiple active tasks could place duplicate orders.

        # ============================================================
        # CLOUDWATCH ALARMS FOR TRADING SAFETY
        # ============================================================

        alarm_namespace = "TradingSystem/Safety"

        def add_log_alarm(
            metric_filter_id: str,
            alarm_id: str,
            metric_name: str,
            alarm_name: str,
            description: str,
            terms: list[str],
        ) -> cloudwatch.Alarm:
            metric_filter = logs.MetricFilter(
                self,
                metric_filter_id,
                log_group=trading_log_group,
                filter_pattern=logs.FilterPattern.any_term(*terms),
                metric_namespace=alarm_namespace,
                metric_name=metric_name,
                metric_value="1",
                default_value=0,
            )
            return cloudwatch.Alarm(
                self,
                alarm_id,
                alarm_name=alarm_name,
                alarm_description=description,
                metric=metric_filter.metric(
                    statistic="sum",
                    period=Duration.minutes(5),
                ),
                threshold=1,
                evaluation_periods=1,
                comparison_operator=cloudwatch.ComparisonOperator.GREATER_THAN_OR_EQUAL_TO_THRESHOLD,
                treat_missing_data=cloudwatch.TreatMissingData.NOT_BREACHING,
            )

        bot_stopped_alarm = cloudwatch.Alarm(
            self,
            "TradingBotStoppedAlarm",
            alarm_name=f"trading-bot-stopped-{environment}",
            alarm_description="Trading bot ECS service has no running tasks.",
            metric=trading_service.metric(
                "RunningTaskCount",
                statistic="Minimum",
                period=Duration.minutes(1),
            ),
            threshold=1,
            evaluation_periods=2,
            comparison_operator=cloudwatch.ComparisonOperator.LESS_THAN_THRESHOLD,
            treat_missing_data=cloudwatch.TreatMissingData.BREACHING,
        )
        stale_data_alarm = add_log_alarm(
            "StaleDataMetricFilter",
            "StaleDataAlarm",
            "StaleDataEvents",
            f"trading-stale-data-{environment}",
            "Trading bot reported stale or missing market data.",
            ["stale data", "stale market data", "missing market data", "data too old"],
        )
        order_failure_alarm = add_log_alarm(
            "OrderFailureMetricFilter",
            "OrderFailureAlarm",
            "OrderFailureEvents",
            f"trading-order-failure-{environment}",
            "Trading bot reported order placement or broker execution failure.",
            ["order failed", "place_order failed", "execution failed", "broker error"],
        )
        loss_breach_alarm = add_log_alarm(
            "LossBreachMetricFilter",
            "LossBreachAlarm",
            "LossBreachEvents",
            f"trading-loss-breach-{environment}",
            "Trading bot reported daily loss limit breach.",
            ["daily loss limit", "loss limit reached", "max daily loss", "loss breach"],
        )
        square_off_failure_alarm = add_log_alarm(
            "SquareOffFailureMetricFilter",
            "SquareOffFailureAlarm",
            "SquareOffFailureEvents",
            f"trading-square-off-failure-{environment}",
            "Trading bot reported square-off failure.",
            ["square off failed", "square-off failed", "failed to square off", "square_off failed"],
        )

        def add_scheduled_trading_task(
            rule_id: str,
            rule_name: str,
            description: str,
            schedule_expression: str,
            scheduled_action: str,
        ) -> events.Rule:
            rule = events.Rule(
                self,
                rule_id,
                rule_name=rule_name,
                description=description,
                schedule=events.Schedule.expression(schedule_expression),
                enabled=True,
            )
            rule.add_target(
                events_targets.EcsTask(
                    cluster=cluster,
                    task_definition=trading_task,
                    role=schedule_role,
                    task_count=1,
                    launch_type=ecs.LaunchType.FARGATE,
                    assign_public_ip=True,
                    subnet_selection=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
                    security_groups=[ecs_security_group],
                    container_overrides=[
                        events_targets.ContainerOverride(
                            container_name="TradingBotContainer",
                            environment=[
                                events_targets.TaskEnvironmentVariable(
                                    name="SCHEDULED_ACTION",
                                    value=scheduled_action,
                                ),
                                events_targets.TaskEnvironmentVariable(
                                    name="RUN_SOURCE",
                                    value="eventbridge",
                                ),
                            ],
                        )
                    ],
                )
            )
            return rule

        overnight_rule = add_scheduled_trading_task(
            "OvernightAnalysisSchedule",
            f"trading-overnight-analysis-{environment}",
            "Runs overnight macro/news/watchlist preparation for the trading bot.",
            scheduled_tasks_config.get(
                "overnight_analysis_expression",
                "cron(0 17 ? * MON-FRI *)",
            ),
            "overnight_analysis",
        )
        market_open_rule = add_scheduled_trading_task(
            "MarketOpenSchedule",
            f"trading-market-open-{environment}",
            "Runs the market-open control point before intraday trading.",
            scheduled_tasks_config.get(
                "market_open_expression",
                "cron(45 3 ? * MON-FRI *)",
            ),
            "market_open",
        )
        square_off_rule = add_scheduled_trading_task(
            "SquareOffSchedule",
            f"trading-square-off-{environment}",
            "Runs the square-off control point before Indian market close.",
            scheduled_tasks_config.get(
                "square_off_expression",
                "cron(50 9 ? * MON-FRI *)",
            ),
            "square_off",
        )

        # ============================================================
        # DASHBOARD TASK DEFINITION (Public facing via Load Balancer)
        # ============================================================
        
        dashboard_task = ecs.FargateTaskDefinition(
            self, "DashboardTaskDefinition",
            memory_limit_mib=512,
            cpu=256,
            task_role=self.agent_role,
            execution_role=self.agent_role
        )

        dashboard_env = {
            "AWS_REGION": self.region,
            "ENVIRONMENT": environment,
            "TRADES_TABLE": trades_table.table_name,
            "LEARNING_TABLE": learning_table.table_name,
            "MARKET_STATE_TABLE": market_state_table.table_name,
            "SIGNALS_TABLE": signals_table.table_name,
            "RISK_EVENTS_TABLE": risk_events_table.table_name,
            "ORDERS_TABLE": orders_table.table_name,
            "FILLS_TABLE": fills_table.table_name,
            "POSITIONS_TABLE": positions_table.table_name,
            "PORT": "8080",
        }

        dashboard_log_group = logs.LogGroup(
            self,
            "DashboardLogs",
            log_group_name=f"/ecs/dashboard-{environment}",
            retention=logs.RetentionDays.ONE_MONTH,
            removal_policy=RemovalPolicy.DESTROY,
        )

        dashboard_task.add_container(
            "DashboardContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, "dashboard-latest"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="dashboard",
                log_group=dashboard_log_group
            ),
            environment=dashboard_env,
            port_mappings=[ecs.PortMapping(container_port=8080, name="http")]
        )

        # Dashboard Service: public subnet egress, inbound traffic only through the ALB security group.
        dashboard_service = ecs.FargateService(
            self, "DashboardService",
            cluster=cluster,
            task_definition=dashboard_task,
            desired_count=1,
            circuit_breaker=ecs.DeploymentCircuitBreaker(rollback=True),
            min_healthy_percent=100,
            max_healthy_percent=200,
            assign_public_ip=True,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC),
            security_groups=[ecs_security_group],
            service_name=f"dashboard-{environment}"
        )

        # ============================================================
        # LOAD BALANCER FOR DASHBOARD
        # ============================================================
        
        lb = elbv2.ApplicationLoadBalancer(
            self, "DashboardLB",
            vpc=vpc,
            internet_facing=True,
            security_group=load_balancer_security_group,
            vpc_subnets=ec2.SubnetSelection(subnets=public_subnets)
        )

        listener = lb.add_listener("DashboardListener", port=80)
        listener.add_targets(
            "DashboardTarget",
            port=8080,
            targets=[dashboard_service],
            health_check=elbv2.HealthCheck(
                path="/api/health",
                healthy_http_codes="200",
            ),
        )

        # ============================================================
        # OUTPUTS
        # ============================================================
        
        CfnOutput(self, "DashboardUrl", value=f"http://{lb.load_balancer_dns_name}")
        CfnOutput(self, "EcrRepoUri", value=ecr_repo.repository_uri)
        CfnOutput(self, "EcrRepoName", value=ecr_repo.repository_name)
        CfnOutput(self, "TradingBotServiceName", value=trading_service.service_name)
        CfnOutput(self, "DashboardServiceName", value=dashboard_service.service_name)
        CfnOutput(self, "EcsClusterName", value=cluster.cluster_name)
        CfnOutput(self, "OvernightAnalysisScheduleName", value=overnight_rule.rule_name)
        CfnOutput(self, "MarketOpenScheduleName", value=market_open_rule.rule_name)
        CfnOutput(self, "SquareOffScheduleName", value=square_off_rule.rule_name)
        CfnOutput(self, "TradingBotStoppedAlarmName", value=bot_stopped_alarm.alarm_name)
        CfnOutput(self, "StaleDataAlarmName", value=stale_data_alarm.alarm_name)
        CfnOutput(self, "OrderFailureAlarmName", value=order_failure_alarm.alarm_name)
        CfnOutput(self, "LossBreachAlarmName", value=loss_breach_alarm.alarm_name)
        CfnOutput(self, "SquareOffFailureAlarmName", value=square_off_failure_alarm.alarm_name)
        
        print(f"\n✅ Agent Runtime Stack Deployed:")
        print(f"   Dashboard URL: http://{lb.load_balancer_dns_name}")
        print(f"   Trading Bot Service: {trading_service.service_name}")
        print(f"   ECS Cluster: {cluster.cluster_name}")
