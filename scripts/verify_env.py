#!/usr/bin/env python3
"""Verify the deployed trading environment.

This is a read-only operational check for P9-WP05. It validates the AWS
foundation, ECS runtime, Oracle static-IP services, and dashboard health from
the selected environment config.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin

import requests


ROOT = Path(__file__).resolve().parents[1]
PLATFORM_STACK = "svc-trd-PlatformStack"
RUNTIME_STACK = "svc-trd-AgentRuntimeStack"


@dataclass
class Check:
    name: str
    ok: bool
    detail: str
    severity: str = "fail"

    @property
    def failed(self) -> bool:
        return not self.ok and self.severity == "fail"


def load_config(environment: str) -> dict[str, Any]:
    config_path = ROOT / "cicd" / "env" / f"{environment}.json"
    if not config_path.exists():
        raise SystemExit(f"environment config not found: {config_path}")
    return json.loads(config_path.read_text())


def status_line(check: Check) -> str:
    if check.ok:
        prefix = "OK"
    elif check.severity == "warn":
        prefix = "WARN"
    else:
        prefix = "FAIL"
    return f"[{prefix}] {check.name}: {check.detail}"


def make_session(profile: str | None, region: str):
    import boto3

    kwargs: dict[str, str] = {"region_name": region}
    if profile:
        kwargs["profile_name"] = profile
    return boto3.Session(**kwargs)


def stack_outputs(cfn, stack_name: str) -> dict[str, str]:
    response = cfn.describe_stacks(StackName=stack_name)
    stacks = response.get("Stacks", [])
    if not stacks:
        return {}
    return {
        item["OutputKey"]: item["OutputValue"]
        for item in stacks[0].get("Outputs", [])
        if "OutputKey" in item and "OutputValue" in item
    }


def check_account(session, config: dict[str, Any]) -> Check:
    expected = config["aws"]["account_id"]
    sts = session.client("sts")
    identity = sts.get_caller_identity()
    actual = identity.get("Account")
    arn = identity.get("Arn", "unknown")
    return Check(
        "AWS caller",
        actual == expected,
        f"{arn} in account {actual}; expected {expected}",
    )


def check_stack(cfn, stack_name: str) -> Check:
    response = cfn.describe_stacks(StackName=stack_name)
    stack = response["Stacks"][0]
    status = stack["StackStatus"]
    ok = status.endswith("_COMPLETE") and not status.startswith("ROLLBACK")
    return Check(f"CloudFormation {stack_name}", ok, status)


def check_ecr(session, config: dict[str, Any]) -> Check:
    repo_name = config["ecr"]["repository_name"]
    ecr = session.client("ecr")
    ecr.describe_repositories(repositoryNames=[repo_name])
    return Check("ECR repository", True, repo_name)


def check_dynamodb_tables(session, config: dict[str, Any]) -> list[Check]:
    dynamodb = session.client("dynamodb")
    checks: list[Check] = []
    for logical_name, table_name in sorted(config["dynamodb"].items()):
        response = dynamodb.describe_table(TableName=table_name)
        status = response["Table"]["TableStatus"]
        checks.append(
            Check(
                f"DynamoDB {logical_name}",
                status == "ACTIVE",
                f"{table_name} status={status}",
            )
        )
    return checks


def service_rollout_ok(service: dict[str, Any]) -> tuple[bool, str]:
    desired = service.get("desiredCount", 0)
    running = service.get("runningCount", 0)
    deployments = service.get("deployments", [])
    primary = next((item for item in deployments if item.get("status") == "PRIMARY"), {})
    rollout = primary.get("rolloutState", "UNKNOWN")
    events = service.get("events", [])
    latest_event = events[0].get("message") if events else "no ECS events"
    ok = desired > 0 and running >= desired and rollout in {"COMPLETED", "IN_PROGRESS"}
    detail = f"desired={desired} running={running} rollout={rollout}; latest={latest_event}"
    return ok, detail


def check_ecs_services(session, config: dict[str, Any]) -> list[Check]:
    ecs = session.client("ecs")
    cluster = config["ecs"]["cluster_name"]
    service_names = [
        config["ecs"]["trading_service"],
        config["ecs"]["dashboard_service"],
    ]
    response = ecs.describe_services(cluster=cluster, services=service_names)
    failures = response.get("failures", [])
    checks = [
        Check("ECS describe-services", not failures, f"failures={failures}")
    ]
    for service in response.get("services", []):
        ok, detail = service_rollout_ok(service)
        checks.append(Check(f"ECS service {service['serviceName']}", ok, detail))
    return checks


def check_http_health(name: str, url: str, timeout: float) -> Check:
    try:
        response = requests.get(url, timeout=timeout)
    except requests.RequestException as exc:
        return Check(name, False, str(exc))
    return Check(name, response.ok, f"GET {url} -> {response.status_code}")


def dashboard_health_url(config: dict[str, Any], outputs: dict[str, str]) -> str | None:
    configured = config.get("load_balancer", {}).get("dns_name", "")
    if configured:
        return f"http://{configured}/api/health"
    dashboard_url = outputs.get("DashboardUrl", "")
    if dashboard_url:
        return urljoin(dashboard_url.rstrip("/") + "/", "api/health")
    return None


def dry_run_checks(config: dict[str, Any]) -> list[Check]:
    table_count = len(config.get("dynamodb", {}))
    oracle = config.get("oracle", {})
    ecs = config.get("ecs", {})
    return [
        Check("Config account", True, f"{config['aws']['account_id']} / {config['aws']['region']}"),
        Check("Planned CloudFormation stacks", True, f"{PLATFORM_STACK}, {RUNTIME_STACK}"),
        Check("Planned DynamoDB tables", True, f"{table_count} tables from cicd/env/{config['environment']}.json"),
        Check("Planned ECS services", True, f"{ecs.get('trading_service')}, {ecs.get('dashboard_service')}"),
        Check("Planned Oracle proxy health", True, oracle.get("execution_proxy_health_url", "not configured")),
        Check("Planned Oracle collector health", True, oracle.get("collector_health_url", "not configured")),
        Check("Planned dashboard health", True, "CloudFormation DashboardUrl + /api/health"),
    ]


def capture(name: str, action: Callable[[], Check]) -> Check:
    try:
        return action()
    except Exception as exc:  # pragma: no cover - exception type depends on AWS client internals.
        return Check(name, False, f"{type(exc).__name__}: {exc}")


def capture_many(name: str, action: Callable[[], list[Check]]) -> list[Check]:
    try:
        return action()
    except Exception as exc:  # pragma: no cover - exception type depends on AWS client internals.
        return [Check(name, False, f"{type(exc).__name__}: {exc}")]


def run_checks(args: argparse.Namespace) -> list[Check]:
    config = load_config(args.env)
    if args.dry_run:
        return dry_run_checks(config)

    region = config["aws"]["region"]
    profile = args.profile or config.get("aws", {}).get("profile") or None
    try:
        session = make_session(profile, region)
        cfn = session.client("cloudformation")
    except Exception as exc:
        return [Check("AWS session", False, f"{type(exc).__name__}: {exc}")]

    checks: list[Check] = [
        capture("AWS caller", lambda: check_account(session, config)),
        capture(f"CloudFormation {PLATFORM_STACK}", lambda: check_stack(cfn, PLATFORM_STACK)),
        capture(f"CloudFormation {RUNTIME_STACK}", lambda: check_stack(cfn, RUNTIME_STACK)),
        capture("ECR repository", lambda: check_ecr(session, config)),
    ]
    checks.extend(capture_many("DynamoDB tables", lambda: check_dynamodb_tables(session, config)))
    checks.extend(capture_many("ECS services", lambda: check_ecs_services(session, config)))

    try:
        runtime_outputs = stack_outputs(cfn, RUNTIME_STACK)
    except Exception:
        runtime_outputs = {}
    if not args.skip_http:
        oracle = config.get("oracle", {})
        checks.append(check_http_health("Oracle execution proxy", oracle["execution_proxy_health_url"], args.timeout))
        checks.append(check_http_health("Oracle collector", oracle["collector_health_url"], args.timeout))
        dashboard_url = dashboard_health_url(config, runtime_outputs)
        if dashboard_url:
            checks.append(check_http_health("Dashboard", dashboard_url, args.timeout))
        else:
            checks.append(Check("Dashboard", False, "no dashboard URL found", severity="warn"))
    return checks


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Verify the deployed trading environment.")
    parser.add_argument("--env", default="prod", help="Environment config name under cicd/env")
    parser.add_argument("--profile", default="", help="AWS profile override")
    parser.add_argument("--dry-run", action="store_true", help="Validate planned checks without calling AWS or HTTP endpoints")
    parser.add_argument("--skip-http", action="store_true", help="Skip Oracle and dashboard HTTP health checks")
    parser.add_argument("--timeout", type=float, default=3.0, help="HTTP timeout in seconds")
    parser.add_argument("--allow-degraded", action="store_true", help="Print failures but exit 0")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    checks = run_checks(args)
    for check in checks:
        print(status_line(check))

    failed = [check for check in checks if check.failed]
    if failed and not args.allow_degraded:
        print(f"environment verification failed: {len(failed)} failing check(s)")
        return 1
    print("environment verification passed" if not failed else "environment verification completed with degraded checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
