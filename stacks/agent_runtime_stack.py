from aws_cdk import (
    Stack, Duration, CfnOutput, RemovalPolicy,
    aws_iam as iam,
    aws_s3 as s3,
    aws_dynamodb as dynamodb,
    aws_ecs as ecs,
    aws_ecs_patterns as ecs_patterns,
    aws_ecr as ecr,
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
        config: dict,
        **kwargs
    ) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # LOAD CONFIGURATION
        # ============================================================
        
        environment = config.get("environment", "dev")
        trading_config = config.get("trading", {})
        bedrock_config = config.get("bedrock", {})
        icici_config = config.get("icici", {})
        
        paper_trading = trading_config.get("paper_trading", True)
        capital = trading_config.get("capital", 100000)
        analysis_interval = trading_config.get("analysis_interval_seconds", 180)
        min_confidence = trading_config.get("min_confidence_threshold", 70)
        max_daily_loss_percent = trading_config.get("max_daily_loss_percent", 4)
        max_position_size_percent = trading_config.get("max_position_size_percent", 10)
        watchlist_size = trading_config.get("watchlist_size", 10)
        
        static_ip = icici_config.get("static_ip")
        bedrock_model = bedrock_config.get("model_id", "anthropic.claude-3-haiku-20240307-v1:0")
        bedrock_region = bedrock_config.get("region", "eu-west-2")
        
        print(f"\n📋 Agent Runtime Configuration:")
        print(f"   Environment: {environment}")
        print(f"   Paper Trading: {paper_trading}")
        print(f"   Capital: ₹{capital:,.2f}")
        print(f"   Analysis Interval: {analysis_interval} seconds")
        print(f"   Min Confidence: {min_confidence}%")
        print(f"   Max Daily Loss: {max_daily_loss_percent}%")
        print(f"   Max Position Size: {max_position_size_percent}%")
        print(f"   Watchlist Size: {watchlist_size}")
        print(f"   Static IP (NAT): {static_ip}")
        print(f"   Bedrock Model: {bedrock_model}")

        # ============================================================
        # IAM ROLE FOR ECS TASKS
        # ============================================================
        
        self.agent_role = iam.Role(
            self, "svc-trd-ecs-task-role",
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="IAM Role for ECS Trading Bot Tasks",
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("CloudWatchFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
            ]
        )

        # Bedrock permissions for Claude models
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

        # S3 permissions for code bucket
        code_bucket.grant_read_write(self.agent_role)
        
        # DynamoDB permissions for all tables
        session_table.grant_read_write_data(self.agent_role)
        trades_table.grant_read_write_data(self.agent_role)
        learning_table.grant_read_write_data(self.agent_role)
        market_state_table.grant_read_write_data(self.agent_role)

        # Secrets Manager permissions for ICICI credentials
        self.agent_role.add_to_policy(
            iam.PolicyStatement(
                actions=["secretsmanager:GetSecretValue"],
                resources=["*"]  # TODO: Restrict to specific secret ARNs
            )
        )

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
            "MIN_CONFIDENCE_THRESHOLD": str(min_confidence),
            "MAX_DAILY_LOSS_PERCENT": str(max_daily_loss_percent),
            "MAX_POSITION_SIZE_PERCENT": str(max_position_size_percent),
            "WATCHLIST_SIZE": str(watchlist_size),
            "STATIC_IP": static_ip,
            "BEDROCK_MODEL_ID": bedrock_model,
            "BEDROCK_REGION": bedrock_region,
            "SESSIONS_TABLE": session_table.table_name,
            "TRADES_TABLE": trades_table.table_name,
            "LEARNING_TABLE": learning_table.table_name,
            "MARKET_STATE_TABLE": market_state_table.table_name,
            "CODE_BUCKET": code_bucket.bucket_name,
        }

        trading_task.add_container(
            "TradingBotContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, "trading-bot-latest"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="trading-bot",
                log_group=logs.LogGroup(self, "TradingBotLogs", log_group_name=f"/ecs/trading-bot-{environment}")
            ),
            environment=trading_env,
            port_mappings=[ecs.PortMapping(container_port=9090, name="metrics")]
        )

        # Trading Bot Service (Private Subnet - uses NAT Gateway for internet)
        trading_service = ecs.FargateService(
            self, "TradingBotService",
            cluster=cluster,
            task_definition=trading_task,
            desired_count=1,
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnet]),
            security_groups=[ecs_security_group],
            service_name=f"trading-bot-{environment}"
        )

        # Auto-scaling for trading bot
        scaling = trading_service.auto_scale_task_count(min_capacity=1, max_capacity=2)
        scaling.scale_on_cpu_utilization("CpuScaling", target_utilization_percent=70)

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
            "PORT": "8080",
        }

        dashboard_task.add_container(
            "DashboardContainer",
            image=ecs.ContainerImage.from_ecr_repository(ecr_repo, "dashboard-latest"),
            logging=ecs.LogDriver.aws_logs(
                stream_prefix="dashboard",
                log_group=logs.LogGroup(self, "DashboardLogs", log_group_name=f"/ecs/dashboard-{environment}")
            ),
            environment=dashboard_env,
            port_mappings=[ecs.PortMapping(container_port=8080, name="http")]
        )

        # Dashboard Service (Public facing)
        dashboard_service = ecs.FargateService(
            self, "DashboardService",
            cluster=cluster,
            task_definition=dashboard_task,
            desired_count=1,
            assign_public_ip=False,
            vpc_subnets=ec2.SubnetSelection(subnets=[private_subnet]),
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
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )

        listener = lb.add_listener("DashboardListener", port=80)
        listener.add_targets(
            "DashboardTarget",
            port=8080,
            targets=[dashboard_service]
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
        
        print(f"\n✅ Agent Runtime Stack Deployed:")
        print(f"   Dashboard URL: http://{lb.load_balancer_dns_name}")
        print(f"   Trading Bot Service: {trading_service.service_name}")
        print(f"   ECS Cluster: {cluster.cluster_name}")