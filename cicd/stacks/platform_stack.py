from aws_cdk import (
    CfnOutput,
    RemovalPolicy,
    Stack,
    Tags,
    aws_cognito as cognito,
    aws_dynamodb as dynamodb,
    aws_ec2 as ec2,
    aws_ecr as ecr,
    aws_iam as iam,
    aws_s3 as s3,
)
from constructs import Construct


class PlatformStack(Stack):
    """Foundation stack for the trading platform.

    Owns the long-lived AWS platform resources:
    VPC, public/private subnets, NAT, security groups, IAM roles, ECR, S3,
    DynamoDB tables, and dashboard auth.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        self.config = config
        self.deploy_environment = config.get("environment", "prod")

        self._create_network()
        self._create_iam()
        self._create_ecr()
        self._create_storage()
        self._create_auth()
        self._add_outputs(construct_id)

    def _create_network(self) -> None:
        aws_config = self.config.get("aws", {})
        vpc_config = self.config.get("vpc", {})
        oracle_config = self.config.get("oracle", {})

        region = aws_config.get("region", self.region)
        oracle_static_ip = oracle_config.get("static_ip", "")
        vpc_name = vpc_config.get("vpc_name", "trd-vpc")
        vpc_cidr = vpc_config.get("cidr", "10.60.0.0/16")
        availability_zones = vpc_config.get("availability_zones") or [f"{region}a", f"{region}b"]

        self.vpc = ec2.Vpc(
            self,
            "TradingVpc",
            vpc_name=vpc_name,
            ip_addresses=ec2.IpAddresses.cidr(vpc_cidr),
            availability_zones=availability_zones,
            nat_gateways=int(vpc_config.get("nat_gateways", 1)),
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name=vpc_config.get("public_subnet_name", "trd-pub-subnet"),
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=int(vpc_config.get("public_subnet_cidr_mask", 24)),
                ),
                ec2.SubnetConfiguration(
                    name=vpc_config.get("private_subnet_name", "trd-pri-subnet"),
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=int(vpc_config.get("private_subnet_cidr_mask", 24)),
                ),
            ],
        )
        Tags.of(self.vpc).add("Project", "trader-daily-india")
        Tags.of(self.vpc).add("ManagedBy", "cdk")

        self.public_subnets = list(self.vpc.public_subnets)
        self.private_subnets = list(self.vpc.private_subnets)
        self.public_subnet = self.public_subnets[0]
        self.private_subnet = self.private_subnets[0]

        self.ecs_security_group = ec2.SecurityGroup(
            self,
            "TradingEcsSecurityGroup",
            vpc=self.vpc,
            security_group_name=vpc_config.get("ecs_security_group_name", "trd-ecs-sg"),
            description="Trading ECS tasks security group",
            allow_all_outbound=True,
        )
        self.load_balancer_security_group = ec2.SecurityGroup(
            self,
            "DashboardLoadBalancerSecurityGroup",
            vpc=self.vpc,
            security_group_name=vpc_config.get("load_balancer_security_group_name", "trd-dashboard-lb-sg"),
            description="Trading dashboard load balancer security group",
            allow_all_outbound=True,
        )
        self.load_balancer_security_group.add_ingress_rule(
            ec2.Peer.any_ipv4(),
            ec2.Port.tcp(80),
            "Allow dashboard HTTP access",
        )
        self.ecs_security_group.add_ingress_rule(
            self.load_balancer_security_group,
            ec2.Port.tcp(8080),
            "Allow dashboard load balancer to reach ECS tasks",
        )

        self.bastion_security_group = self.ecs_security_group
        self.oracle_static_ip_address = oracle_static_ip

    def _create_iam(self) -> None:
        iam_config = self.config.get("iam", {})

        self.role = iam.Role(
            self,
            "TradingSystemRole",
            role_name=iam_config.get("role_name", "trd-prod-ecs-taskexecute-role"),
            assumed_by=iam.ServicePrincipal("ecs-tasks.amazonaws.com"),
            description="Unified ECS Task Role for trading system (execution + task)",
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "ecr:GetAuthorizationToken",
                    "ecr:BatchCheckLayerAvailability",
                    "ecr:GetDownloadUrlForLayer",
                    "ecr:BatchGetImage",
                    "logs:CreateLogGroup",
                    "logs:CreateLogStream",
                    "logs:PutLogEvents",
                    "logs:DescribeLogStreams",
                    "cloudwatch:PutMetricData",
                    "cloudwatch:GetMetricData",
                    "ec2:DescribeNetworkInterfaces",
                    "ec2:CreateNetworkInterface",
                    "ec2:AttachNetworkInterface",
                    "ec2:DescribeSubnets",
                    "ec2:DescribeSecurityGroups",
                    "ec2:DescribeVpcs",
                    "secretsmanager:GetSecretValue",
                ],
                resources=["*"],
            )
        )
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
                resources=["arn:aws:dynamodb:*:*:table/svc-trd-*"],
            )
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "sqs:GetQueueAttributes",
                    "sqs:GetQueueUrl",
                    "sqs:ReceiveMessage",
                    "sqs:SendMessage",
                    "sqs:DeleteMessage",
                    "sqs:ChangeMessageVisibility",
                ],
                resources=["arn:aws:sqs:*:*:svc-trd-*"],
            )
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["bedrock:InvokeModel", "bedrock:InvokeModelWithResponseStream"],
                resources=["arn:aws:bedrock:*::foundation-model/anthropic.claude-*"],
            )
        )
        self.role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
                resources=["arn:aws:s3:::svc-s3-*", "arn:aws:s3:::svc-s3-*/*"],
            )
        )

        self.eventbridge_role = iam.Role(
            self,
            "EventBridgeRole",
            role_name=iam_config.get("eventbridge_role_name", "trd-prod-eventbridge-ecs-role"),
            assumed_by=iam.ServicePrincipal("events.amazonaws.com"),
            description="Role for EventBridge to start ECS tasks",
        )
        self.eventbridge_role.add_to_policy(
            iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["ecs:RunTask"], resources=["*"])
        )
        self.eventbridge_role.add_to_policy(
            iam.PolicyStatement(effect=iam.Effect.ALLOW, actions=["iam:PassRole"], resources=[self.role.role_arn])
        )

        github_config = self.config.get("github", {})
        github_oidc_provider_arn = github_config.get("oidc_provider_arn", "")
        if github_oidc_provider_arn:
            github_provider = iam.OpenIdConnectProvider.from_open_id_connect_provider_arn(
                self,
                "GitHubActionsOidcProvider",
                github_oidc_provider_arn,
            )
        else:
            github_provider = iam.OpenIdConnectProvider(
                self,
                "GitHubActionsOidcProvider",
                url="https://token.actions.githubusercontent.com",
                client_ids=["sts.amazonaws.com"],
            )

        github_repository = github_config.get("repository", "taniShant/trader-daily-india")
        github_branch = github_config.get("deploy_branch", "main")
        self.github_deploy_role = iam.Role(
            self,
            "GitHubDeployRole",
            role_name=github_config.get("deploy_role_name", "trd-prod-github-deploy-role"),
            assumed_by=iam.WebIdentityPrincipal(
                github_provider.open_id_connect_provider_arn,
                conditions={
                    "StringEquals": {"token.actions.githubusercontent.com:aud": "sts.amazonaws.com"},
                    "StringLike": {
                        "token.actions.githubusercontent.com:sub": f"repo:{github_repository}:ref:refs/heads/{github_branch}"
                    },
                },
            ),
            description=f"GitHub Actions deploy role for {github_repository}:{github_branch}",
        )
        self.github_deploy_role.add_managed_policy(
            iam.ManagedPolicy.from_aws_managed_policy_name("AdministratorAccess")
        )

    def _create_ecr(self) -> None:
        self.ecr_repository = ecr.Repository(
            self,
            "TradingSystemRepository",
            repository_name=self.config.get("ecr", {}).get("repository_name", "trading-system"),
            image_scan_on_push=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

    def _create_storage(self) -> None:
        s3_config = self.config.get("s3", {})
        dynamodb_config = self.config.get("dynamodb", {})
        bucket_name = s3_config.get("code_bucket")
        if not bucket_name:
            raise ValueError("S3 bucket name not found in config under 's3.code_bucket'")

        self.code_bucket = s3.Bucket(
            self,
            "CodeBucket",
            bucket_name=bucket_name,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            encryption=s3.BucketEncryption.S3_MANAGED,
            versioned=True,
            removal_policy=RemovalPolicy.RETAIN,
        )

        self.session_table = self._table(
            "SessionTable",
            dynamodb_config.get("session_table", f"svc-trd-sessions-{self.deploy_environment}"),
            "sessionId",
            "timestamp",
            ttl="ttl",
        )
        self.trades_table = self._table(
            "TradesTable",
            dynamodb_config.get("trades_table", f"svc-trd-trades-{self.deploy_environment}"),
            "tradeId",
            "date",
            pitr=True,
        )
        self.trades_table.add_global_secondary_index(
            index_name="stock-index",
            partition_key=dynamodb.Attribute(name="stock_symbol", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
        )
        self.trades_table.add_global_secondary_index(
            index_name="pnl-index",
            partition_key=dynamodb.Attribute(name="action", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="pnl", type=dynamodb.AttributeType.NUMBER),
        )

        self.learning_table = self._table(
            "LearningTable",
            dynamodb_config.get("learning_table", f"svc-trd-learning-{self.deploy_environment}"),
            "pattern_id",
            "date",
        )
        self.learning_table.add_global_secondary_index(
            index_name="winrate-index",
            partition_key=dynamodb.Attribute(name="pattern_type", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="win_rate", type=dynamodb.AttributeType.NUMBER),
        )

        self.market_state_table = self._table(
            "MarketStateTable",
            dynamodb_config.get("market_state_table", f"svc-trd-market-state-{self.deploy_environment}"),
            "date",
            "timestamp",
        )
        self.market_state_table.add_global_secondary_index(
            index_name="sentiment-index",
            partition_key=dynamodb.Attribute(name="global_sentiment", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="date", type=dynamodb.AttributeType.STRING),
        )

        self.signals_table = self._table(
            "SignalsTable",
            dynamodb_config.get("signals_table", f"svc-trd-signals-{self.deploy_environment}"),
            "signal_id",
            "created_at",
            pitr=True,
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

        self.risk_events_table = self._table(
            "RiskEventsTable",
            dynamodb_config.get("risk_events_table", f"svc-trd-risk-events-{self.deploy_environment}"),
            "risk_decision_id",
            "created_at",
            pitr=True,
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

        self.orders_table = self._table(
            "OrdersTable",
            dynamodb_config.get("orders_table", f"svc-trd-orders-{self.deploy_environment}"),
            "client_order_id",
            "updated_at",
            pitr=True,
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

        self.fills_table = self._table(
            "FillsTable",
            dynamodb_config.get("fills_table", f"svc-trd-fills-{self.deploy_environment}"),
            "fill_id",
            "filled_at",
            pitr=True,
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

        self.positions_table = self._table(
            "PositionsTable",
            dynamodb_config.get("positions_table", f"svc-trd-positions-{self.deploy_environment}"),
            "symbol",
            "session_id",
            pitr=True,
        )
        self.positions_table.add_global_secondary_index(
            index_name="session-symbol-index",
            partition_key=dynamodb.Attribute(name="session_id", type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name="symbol", type=dynamodb.AttributeType.STRING),
        )

    def _table(
        self,
        construct_id: str,
        table_name: str,
        partition_key: str,
        sort_key: str,
        *,
        pitr: bool = False,
        ttl: str | None = None,
    ) -> dynamodb.Table:
        kwargs = {}
        if pitr:
            kwargs["point_in_time_recovery_specification"] = dynamodb.PointInTimeRecoverySpecification(
                point_in_time_recovery_enabled=True
            )
        if ttl:
            kwargs["time_to_live_attribute"] = ttl
        return dynamodb.Table(
            self,
            construct_id,
            table_name=table_name,
            partition_key=dynamodb.Attribute(name=partition_key, type=dynamodb.AttributeType.STRING),
            sort_key=dynamodb.Attribute(name=sort_key, type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,
            removal_policy=RemovalPolicy.DESTROY,
            **kwargs,
        )

    def _create_auth(self) -> None:
        self.user_pool = cognito.UserPool(
            self,
            "TradingUserPool",
            self_sign_up_enabled=False,
            sign_in_aliases=cognito.SignInAliases(email=True),
            removal_policy=RemovalPolicy.DESTROY,
        )
        self.user_pool_client = cognito.UserPoolClient(
            self,
            "TradingUserPoolClient",
            user_pool=self.user_pool,
            generate_secret=True,
            auth_flows=cognito.AuthFlow(user_password=True),
        )
        self.identity_pool = cognito.CfnIdentityPool(
            self,
            "TradingIdentityPool",
            allow_unauthenticated_identities=False,
            cognito_identity_providers=[
                {
                    "clientId": self.user_pool_client.user_pool_client_id,
                    "providerName": self.user_pool.user_pool_provider_name,
                }
            ],
        )
        self.authenticated_role = iam.Role(
            self,
            "TradingAuthRole",
            assumed_by=iam.FederatedPrincipal(
                "cognito-identity.amazonaws.com",
                {
                    "StringEquals": {"cognito-identity.amazonaws.com:aud": self.identity_pool.ref},
                    "ForAnyValue:StringLike": {"cognito-identity.amazonaws.com:amr": "authenticated"},
                },
                "sts:AssumeRoleWithWebIdentity",
            ),
        )
        cognito.CfnIdentityPoolRoleAttachment(
            self,
            "TradingIdentityPoolAttachment",
            identity_pool_id=self.identity_pool.ref,
            roles={"authenticated": self.authenticated_role.role_arn},
        )

    def _add_outputs(self, construct_id: str) -> None:
        CfnOutput(self, "VpcId", value=self.vpc.vpc_id, export_name=f"{construct_id}:VpcId")
        CfnOutput(self, "PublicSubnetId", value=self.public_subnet.subnet_id)
        CfnOutput(self, "PrivateSubnetId", value=self.private_subnet.subnet_id)
        CfnOutput(self, "EcsSecurityGroupId", value=self.ecs_security_group.security_group_id)
        CfnOutput(self, "LoadBalancerSecurityGroupId", value=self.load_balancer_security_group.security_group_id)
        CfnOutput(self, "OracleStaticIp", value=self.oracle_static_ip_address)
        CfnOutput(self, "RoleArn", value=self.role.role_arn)
        CfnOutput(self, "EventBridgeRoleArn", value=self.eventbridge_role.role_arn)
        CfnOutput(self, "GitHubDeployRoleArn", value=self.github_deploy_role.role_arn)
        CfnOutput(self, "EcrRepoUri", value=self.ecr_repository.repository_uri)
        CfnOutput(self, "EcrRepoName", value=self.ecr_repository.repository_name)
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
        CfnOutput(self, "UserPoolId", value=self.user_pool.user_pool_id)
        CfnOutput(self, "UserPoolClientId", value=self.user_pool_client.user_pool_client_id)
        CfnOutput(self, "IdentityPoolId", value=self.identity_pool.ref)
