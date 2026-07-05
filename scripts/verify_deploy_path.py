#!/usr/bin/env python3
"""Validate the selected deployment path for P0-WP05.

This is a static guard. It proves the repo has one active AWS deployment route:
GitHub Actions builds images, then CDK owns AWS infra and ECS services.
"""

from __future__ import annotations

import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text()


def fail(message: str) -> None:
    raise SystemExit(f"deploy-path check failed: {message}")


def assert_contains(text: str, needle: str, path: str) -> None:
    if needle not in text:
        fail(f"{path} must contain {needle!r}")


def assert_not_contains(text: str, needle: str, path: str) -> None:
    if needle in text:
        fail(f"{path} must not contain {needle!r}")


def main() -> int:
    deploy = read(".github/workflows/deploy.yml")
    daily = read(".github/workflows/daily-trading.yml")
    app = read("app.py")
    runtime_stack = read("cicd/stacks/agent_runtime_stack.py")
    config = json.loads(read("cicd/env/prod.json"))

    assert_contains(deploy, "name: Deploy AWS Trading System", ".github/workflows/deploy.yml")
    assert_contains(deploy, "docker build", ".github/workflows/deploy.yml")
    assert_contains(deploy, "containers/trading-bot/Dockerfile", ".github/workflows/deploy.yml")
    assert_contains(deploy, "containers/dashboard/Dockerfile", ".github/workflows/deploy.yml")
    assert_contains(deploy, "docker push", ".github/workflows/deploy.yml")
    assert_contains(deploy, "aws ecs update-service", ".github/workflows/deploy.yml")
    assert_contains(deploy, "--force-new-deployment", ".github/workflows/deploy.yml")
    assert_contains(deploy, "cdk synth", ".github/workflows/deploy.yml")
    assert_contains(deploy, "cdk deploy --all", ".github/workflows/deploy.yml")
    assert_not_contains(deploy, "aws ecs register-task-definition", ".github/workflows/deploy.yml")
    assert_not_contains(deploy, "aws ecs create-service", ".github/workflows/deploy.yml")
    assert_not_contains(deploy, "bedrock-agentcore invoke-runtime", ".github/workflows/deploy.yml")
    assert_not_contains(deploy, "cicd/ecstasks_unused/", ".github/workflows/deploy.yml")

    assert_contains(daily, "Runtime is owned by ECS", ".github/workflows/daily-trading.yml")
    assert_not_contains(daily, "schedule:", ".github/workflows/daily-trading.yml")
    assert_not_contains(daily, "bedrock-agentcore invoke-runtime", ".github/workflows/daily-trading.yml")
    assert_not_contains(daily, "Analyze RELIANCE", ".github/workflows/daily-trading.yml")

    assert_contains(app, "TradingAgentRuntimeStack", "app.py")
    assert_contains(runtime_stack, "ORACLE_EXECUTION_PROXY_BASE_URL", "cicd/stacks/agent_runtime_stack.py")
    assert_contains(runtime_stack, "ORACLE_EXECUTION_PROXY_HEALTH_URL", "cicd/stacks/agent_runtime_stack.py")

    oracle = config.get("oracle", {})
    icici = config.get("icici", {})
    if oracle.get("static_ip") != "80.225.242.6":
        fail("cicd/env/prod.json oracle.static_ip must be 80.225.242.6")
    if icici.get("static_ip") != oracle.get("static_ip"):
        fail("cicd/env/prod.json icici.static_ip must match oracle.static_ip")
    if not oracle.get("use_for_live_execution"):
        fail("cicd/env/prod.json oracle.use_for_live_execution must be true")

    for path in [
        "cicd/ecstasks_unused/trading-bot.json",
        "cicd/ecstasks_unused/dashboard.json",
        "cicd/ecstasks_unused/overnight-analysis.json",
    ]:
        if not (ROOT / path).exists():
            fail(f"{path} must remain present as legacy/reference material")

    print("deploy-path check passed: CDK is authoritative for AWS; Oracle is the ICICI static-IP boundary.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
