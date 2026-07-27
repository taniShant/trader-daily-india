import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "cdk.out" / "svc-trd-AgentRuntimeStack.template.json"
_TEMPLATE_CACHE = None


def synth_template():
    global _TEMPLATE_CACHE
    if _TEMPLATE_CACHE is not None:
        return
    result = subprocess.run(
        ["bash", "scripts/verify_cdk_synth.sh"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout
    _TEMPLATE_CACHE = json.loads(TEMPLATE.read_text())


def contains_value(value, needle: str) -> bool:
    if isinstance(value, str):
        return needle in value
    if isinstance(value, dict):
        return any(contains_value(item, needle) for item in value.values())
    if isinstance(value, list):
        return any(contains_value(item, needle) for item in value)
    return False


def agent_runtime_template():
    synth_template()
    return _TEMPLATE_CACHE


def ecs_services():
    template = agent_runtime_template()
    return [
        resource
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::ECS::Service"
    ]


def test_trading_bot_service_is_singleton_without_task_autoscaling():
    source = (ROOT / "cicd" / "cdk" / "stacks" / "agent_runtime_stack.py").read_text()

    assert "TradingBotService" in source
    assert "desired_count=1" in source
    assert "auto_scale_task_count" not in source
    assert "scale_on_cpu_utilization" not in source
    assert "max_capacity=2" not in source


def test_trading_bot_cloudformation_desired_count_is_one():
    trading_services = [
        service
        for service in ecs_services()
        if contains_value(service["Properties"].get("ServiceName"), "trading-bot")
    ]

    assert len(trading_services) == 1
    assert trading_services[0]["Properties"]["DesiredCount"] == 1


def test_ecs_services_have_fast_rollback_deployment_configuration():
    for service in ecs_services():
        deployment = service["Properties"]["DeploymentConfiguration"]

        assert deployment["MinimumHealthyPercent"] == 100
        assert deployment["MaximumPercent"] == 200
        assert deployment["DeploymentCircuitBreaker"] == {
            "Enable": True,
            "Rollback": True,
        }


def test_ecs_services_use_public_subnet_egress_without_nat_gateway():
    for service in ecs_services():
        network = service["Properties"]["NetworkConfiguration"]["AwsvpcConfiguration"]

        assert network["AssignPublicIp"] == "ENABLED"
        assert len(network["Subnets"]) == 2


def test_agent_runtime_uses_single_iam_stack_role():
    source = (ROOT / "cicd" / "cdk" / "stacks" / "agent_runtime_stack.py").read_text()
    template = agent_runtime_template()
    role_names = [
        resource["Properties"].get("RoleName")
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::IAM::Role"
    ]

    assert "self.agent_role = role" in source
    assert "svc-trd-ecs-task-role" not in source
    assert "svc-trd-ecs-task-role" not in role_names
