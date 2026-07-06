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


def agent_runtime_template():
    synth_template()
    return _TEMPLATE_CACHE


def test_dashboard_docker_healthcheck_uses_real_api_health_path():
    dockerfile = (ROOT / "containers" / "dashboard" / "Dockerfile").read_text()

    assert "http://localhost:8080/api/health" in dockerfile
    assert "http://localhost:8080/health" not in dockerfile


def test_dashboard_root_serves_copied_index_file_location():
    api_source = (ROOT / "containers" / "dashboard" / "api_server.py").read_text()
    dockerfile = (ROOT / "containers" / "dashboard" / "Dockerfile").read_text()

    assert "dashboard_root / \"index.html\"" in api_source
    assert "COPY containers/dashboard/index.html ." in dockerfile


def test_dashboard_alb_target_group_uses_api_health_path():
    template = agent_runtime_template()
    target_groups = [
        resource
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::ElasticLoadBalancingV2::TargetGroup"
    ]

    assert target_groups
    assert any(
        group["Properties"].get("HealthCheckPath") == "/api/health"
        and group["Properties"].get("Matcher", {}).get("HttpCode") == "200"
        for group in target_groups
    )


def test_dashboard_alb_is_public_and_spans_created_public_subnets():
    template = agent_runtime_template()
    load_balancers = [
        resource
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::ElasticLoadBalancingV2::LoadBalancer"
    ]

    assert load_balancers
    dashboard_lb = load_balancers[0]["Properties"]

    assert dashboard_lb["Scheme"] == "internet-facing"
    assert len(dashboard_lb["Subnets"]) == 2
