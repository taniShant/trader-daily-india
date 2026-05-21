#!/usr/bin/env python3
from aws_cdk import App, Environment
from stacks.auth_stack import TradingAuthStack
from stacks.storage_stack import TradingStorageStack
from stacks.agent_runtime_stack import TradingAgentRuntimeStack

# Define AWS account and region
# Replace with your actual account ID and region
ACCOUNT_ID = "YOUR_ACCOUNT_ID"  # Get from `aws sts get-caller-identity`
REGION = "us-east-1"

app = App()

# Stack 1: Authentication (Cognito)
auth_stack = TradingAuthStack(
    app, 
    "TradingAuthStack",
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# Stack 2: Storage (S3 + DynamoDB)
storage_stack = TradingStorageStack(
    app, 
    "TradingStorageStack",
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

# Stack 3: Agent Runtime (Bedrock AgentCore)
agent_stack = TradingAgentRuntimeStack(
    app, 
    "TradingAgentRuntimeStack",
    code_bucket=storage_stack.code_bucket,
    session_table=storage_stack.session_table,
    trades_table=storage_stack.trades_table,
    env=Environment(account=ACCOUNT_ID, region=REGION)
)

app.synth()