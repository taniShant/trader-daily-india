#!/usr/bin/env python3
"""
AWS CDK Application for Multi-Agent Trading System

Stacks in order of deployment:
0. PlatformStack - VPC, subnets, NAT, IAM, ECR, S3, DynamoDB, Cognito
1. TradingAgentRuntimeStack - ECS Fargate cluster, tasks, schedules, alarms, dashboard ALB

Usage:
    CDK_DEPLOY_ENV=dev cdk deploy --all
    CDK_DEPLOY_ENV=prod cdk deploy --all
"""

import json
import os
from pathlib import Path
from aws_cdk import App, Environment

ROOT_DIR = Path(__file__).resolve().parent
CICD_DIR = ROOT_DIR / "cicd"

from cicd.cdk.stacks.platform_stack import PlatformStack
from cicd.cdk.stacks.agent_runtime_stack import TradingAgentRuntimeStack

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
    print(f"   Account Name: {config['aws'].get('account_name', env_name)}")
    print(f"   Account: {config['aws']['account_id']}")
    print(f"   Region: {config['aws']['region']}")
    print(f"   Paper Trading: {config['trading']['paper_trading']}")
    print(f"   S3 Bucket: {config['s3']['code_bucket']}")
    print(f"   VPC Name: {config.get('vpc', {}).get('vpc_name')}")
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
# STACK 0: PLATFORM (Network, IAM, ECR, S3, DynamoDB, Auth)
# ============================================================

platform_stack = PlatformStack(
    app,
    "svc-trd-PlatformStack",
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# ============================================================
# STACK 1: AGENT RUNTIME (ECS Fargate)
# ============================================================

agent_stack = TradingAgentRuntimeStack(
    app, 
    "svc-trd-AgentRuntimeStack",
    vpc=platform_stack.vpc,
    ecs_security_group=platform_stack.ecs_security_group,
    load_balancer_security_group=platform_stack.load_balancer_security_group,
    public_subnet=platform_stack.public_subnet,
    private_subnet=platform_stack.private_subnet,
    public_subnets=platform_stack.public_subnets,
    private_subnets=platform_stack.private_subnets,
    code_bucket=platform_stack.code_bucket,
    session_table=platform_stack.session_table,
    trades_table=platform_stack.trades_table,
    learning_table=platform_stack.learning_table,
    market_state_table=platform_stack.market_state_table,
    signals_table=platform_stack.signals_table,
    risk_events_table=platform_stack.risk_events_table,
    orders_table=platform_stack.orders_table,
    fills_table=platform_stack.fills_table,
    positions_table=platform_stack.positions_table,
    role=platform_stack.role,
    config=CONFIG,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)
agent_stack.add_dependency(platform_stack)

app.synth()
