#!/usr/bin/env python3
"""
AWS CDK Application for Multi-Agent Trading System

Stacks in order of deployment:
0. IAMStack - ECS Execution Role and Task Role
1. NetworkStack - VPC, subnets, security groups, NAT Gateway
2. TradingAuthStack - Cognito user pool and identity pool
3. TradingStorageStack - DynamoDB tables (Trades, Sessions, Learning, MarketState)
4. TradingAgentRuntimeStack - ECS Fargate cluster, tasks, and load balancer

Usage:
    CDK_DEPLOY_ENV=dev cdk deploy --all
    CDK_DEPLOY_ENV=prod cdk deploy --all
"""

import os
import json
from aws_cdk import App, Environment
from stacks.iam_stack import IAMStack
from stacks.network_stack import NetworkStack
from stacks.auth_stack import TradingAuthStack
from stacks.storage_stack import TradingStorageStack
from stacks.agent_runtime_stack import TradingAgentRuntimeStack

# ============================================================
# LOAD CONFIGURATION FROM ENVIRONMENT FILE
# ============================================================

def load_config():
    """Load configuration from env/{dev,prod}.json based on CDK_DEPLOY_ENV"""
    
    # Get environment from CDK_DEPLOY_ENV (default: dev)
    env_name = os.environ.get("CDK_DEPLOY_ENV", "dev").lower()
    
    # Validate environment
    if env_name not in ["dev", "prod"]:
        raise ValueError(f"Invalid environment: {env_name}. Use 'dev' or 'prod'")
    
    # Path to config file
    config_path = os.path.join(os.path.dirname(__file__), "env", f"{env_name}.json")
    
    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Load and return config
    with open(config_path, "r") as f:
        config = json.load(f)
    
    print(f"📋 Loaded configuration for environment: {env_name.upper()}")
    print(f"   Account: {config['aws']['account_id']}")
    print(f"   Region: {config['aws']['region']}")
    print(f"   Paper Trading: {config['trading']['paper_trading']}")
    print(f"   S3 Bucket: {config['s3']['code_bucket']}")
    print(f"   Static IP: {config['icici']['static_ip']}")
    
    return config, env_name

# Load configuration
CONFIG, ENVIRONMENT = load_config()

# ============================================================
# AWS ACCOUNT AND REGION FROM CONFIG
# ============================================================

ACCOUNT_ID = CONFIG["aws"]["account_id"]
REGION = CONFIG["aws"]["region"]

app = App()

# ============================================================
# STACK 0: IAM ROLES (Execution Role + Task Role)
# ============================================================

iam_stack = IAMStack(
    app,
    "svc-trd-IamStack",
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# ============================================================
# STACK 1: NETWORK (Imports existing VPC, subnets, NAT Gateway)
# ============================================================

network_stack = NetworkStack(
    app, 
    "svc-trd-NetworkStack",
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# ============================================================
# STACK 2: AUTHENTICATION (Cognito for Dashboard)
# ============================================================

auth_stack = TradingAuthStack(
    app, 
    "svc-trd-AuthStack",
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# ============================================================
# STACK 3: STORAGE (DynamoDB Tables + Import S3 Bucket)
# ============================================================

storage_stack = TradingStorageStack(
    app, 
    "svc-trd-StorageStack",
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# ============================================================
# STACK 4: AGENT RUNTIME (ECS Fargate)
# ============================================================
# Note: Depends on IAM stack for roles

agent_stack = TradingAgentRuntimeStack(
    app, 
    "svc-trd-AgentRuntimeStack",
    vpc=network_stack.vpc,
    ecs_security_group=network_stack.ecs_security_group,
    load_balancer_security_group=network_stack.load_balancer_security_group,
    public_subnet=network_stack.public_subnet,
    private_subnet=network_stack.private_subnet,
    code_bucket=storage_stack.code_bucket,
    session_table=storage_stack.session_table,
    trades_table=storage_stack.trades_table,
    learning_table=storage_stack.learning_table,
    market_state_table=storage_stack.market_state_table,
    role=iam_stack.role,
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

app.synth()