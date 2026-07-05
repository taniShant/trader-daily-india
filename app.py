#!/usr/bin/env python3
"""
AWS CDK Application for Multi-Agent Trading System

Stacks in order of deployment:
0. IAMStack - ECS Execution Role and Task Role
1. NetworkStack - VPC, subnets, security groups, AWS NAT Gateway reference
2. TradingAuthStack - Cognito user pool and identity pool
3. TradingStorageStack - DynamoDB tables (Trades, Sessions, Learning, MarketState)
4. TradingAgentRuntimeStack - ECS Fargate cluster, tasks, and load balancer

Usage:
    CDK_DEPLOY_ENV=dev cdk deploy --all
    CDK_DEPLOY_ENV=prod cdk deploy --all
"""

import json
import os
from pathlib import Path
from aws_cdk import App, Environment, CfnOutput

ROOT_DIR = Path(__file__).resolve().parent
CICD_DIR = ROOT_DIR / "cicd"

from cicd.stacks.iam_stack import IAMStack
from cicd.stacks.network_stack import NetworkStack
from cicd.stacks.auth_stack import TradingAuthStack
from cicd.stacks.storage_stack import TradingStorageStack
from cicd.stacks.agent_runtime_stack import TradingAgentRuntimeStack

# ============================================================
# LOAD CONFIGURATION FROM ENVIRONMENT FILE
# ============================================================

def load_config():
    """Load configuration from cicd/env/{dev,prod}.json based on CDK_DEPLOY_ENV"""
    
    # Get environment from CDK_DEPLOY_ENV (default: dev)
    env_name = os.environ.get("CDK_DEPLOY_ENV", "prod").lower()
    
    # Validate environment
    if env_name not in ["dev", "prod"]:
        raise ValueError(f"Invalid environment: {env_name}. Use 'dev' or 'prod'")
    
    # Path to config file
    config_path = CICD_DIR / "env" / f"{env_name}.json"
    
    if not config_path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    # Load and return config
    with config_path.open("r") as f:
        config = json.load(f)
    
    print(f"📋 Loaded configuration for environment: {env_name.upper()}")
    print(f"   Account: {config['aws']['account_id']}")
    print(f"   Region: {config['aws']['region']}")
    print(f"   Paper Trading: {config['trading']['paper_trading']}")
    print(f"   S3 Bucket: {config['s3']['code_bucket']}")
    print(f"   AWS NAT IP: {config.get('vpc', {}).get('nat_gateway_ip')}")
    print(f"   Oracle Static IP: {config.get('oracle', {}).get('static_ip')}")
    
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
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)
 

# ============================================================
# STACK 1: NETWORK (Imports existing VPC, subnets, AWS NAT Gateway reference)
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
    signals_table=storage_stack.signals_table,
    risk_events_table=storage_stack.risk_events_table,
    orders_table=storage_stack.orders_table,
    fills_table=storage_stack.fills_table,
    positions_table=storage_stack.positions_table,
    role=iam_stack.role,
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

app.synth()
