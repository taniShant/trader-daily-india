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


def event_rules():
    template = agent_runtime_template()
    return [
        resource["Properties"]
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::Events::Rule"
    ]


def rule_by_name(name):
    return next(rule for rule in event_rules() if rule["Name"] == name)


def target_input(rule):
    return json.loads(rule["Targets"][0]["Input"])


def scheduled_action(rule):
    env = target_input(rule)["containerOverrides"][0]["environment"]
    return {item["name"]: item["value"] for item in env}


def test_eventbridge_defines_required_trading_schedules():
    schedules = {
        rule["Name"]: rule["ScheduleExpression"]
        for rule in event_rules()
    }

    assert schedules["trading-overnight-analysis-prod"] == "cron(0 17 ? * MON-FRI *)"
    assert schedules["trading-market-open-prod"] == "cron(45 3 ? * MON-FRI *)"
    assert schedules["trading-square-off-prod"] == "cron(50 9 ? * MON-FRI *)"


def test_schedules_run_single_private_fargate_task_with_action_override():
    expected_actions = {
        "trading-overnight-analysis-prod": "overnight_analysis",
        "trading-market-open-prod": "market_open",
        "trading-square-off-prod": "square_off",
    }

    for name, action in expected_actions.items():
        rule = rule_by_name(name)
        target = rule["Targets"][0]

        assert rule["State"] == "ENABLED"
        assert target["EcsParameters"]["LaunchType"] == "FARGATE"
        assert target["EcsParameters"]["TaskCount"] == 1
        assert (
            target["EcsParameters"]["NetworkConfiguration"]["AwsVpcConfiguration"]["AssignPublicIp"]
            == "DISABLED"
        )
        assert scheduled_action(rule) == {
            "SCHEDULED_ACTION": action,
            "RUN_SOURCE": "eventbridge",
        }


def test_trading_entrypoint_exits_after_scheduled_action_instead_of_main_loop():
    entrypoint = (ROOT / "containers" / "trading-bot" / "entrypoint.sh").read_text()

    assert 'if [ -n "$SCHEDULED_ACTION" ]; then' in entrypoint
    assert "bot._run_overnight_analysis()" in entrypoint
    assert "bot._square_off_all()" in entrypoint
    assert "Scheduled action completed" in entrypoint
    assert "Starting main trading loop" in entrypoint
