#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

from aws_cdk import App, Environment

ROOT_DIR = Path(__file__).resolve().parents[2]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from cicd.cdk.stacks.cross_account_bedrock_stack import (
    BedrockConsumerPermissionStack,
    BedrockProviderRoleStack,
)


CONFIG_PATH = ROOT_DIR / "cicd" / "env" / "cross-account-bedrock.json"


def load_config() -> dict:
    with CONFIG_PATH.open("r", encoding="utf-8") as file:
        return json.load(file)


config = load_config()
consumer = config["consumer"]
provider = config["provider"]

app = App()

BedrockProviderRoleStack(
    app,
    "svc-trd-BedrockProviderRoleStack",
    config=config,
    env=Environment(
        account=provider["account_id"],
        region=provider["region"],
    ),
)

BedrockConsumerPermissionStack(
    app,
    "svc-trd-BedrockConsumerPermissionStack",
    config=config,
    env=Environment(
        account=consumer["account_id"],
        region=consumer["region"],
    ),
)

app.synth()
