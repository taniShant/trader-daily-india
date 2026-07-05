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


def resources_of_type(resource_type):
    template = agent_runtime_template()
    return [
        resource["Properties"]
        for resource in template["Resources"].values()
        if resource.get("Type") == resource_type
    ]


def test_required_trading_safety_alarms_exist():
    alarms = {
        alarm["AlarmName"]: alarm
        for alarm in resources_of_type("AWS::CloudWatch::Alarm")
    }

    assert {
        "trading-bot-stopped-prod",
        "trading-stale-data-prod",
        "trading-order-failure-prod",
        "trading-loss-breach-prod",
        "trading-square-off-failure-prod",
    } <= set(alarms)

    assert alarms["trading-bot-stopped-prod"]["MetricName"] == "RunningTaskCount"
    assert alarms["trading-bot-stopped-prod"]["Namespace"] == "AWS/ECS"
    assert alarms["trading-bot-stopped-prod"]["ComparisonOperator"] == "LessThanThreshold"
    assert alarms["trading-bot-stopped-prod"]["TreatMissingData"] == "breaching"


def test_log_metric_filters_cover_safety_events():
    filters = {
        item["MetricTransformations"][0]["MetricName"]: item
        for item in resources_of_type("AWS::Logs::MetricFilter")
    }

    assert {
        "StaleDataEvents",
        "OrderFailureEvents",
        "LossBreachEvents",
        "SquareOffFailureEvents",
    } <= set(filters)

    for metric_filter in filters.values():
        transformation = metric_filter["MetricTransformations"][0]
        assert transformation["MetricNamespace"] == "TradingSystem/Safety"
        assert transformation["MetricValue"] == "1"
        assert metric_filter["LogGroupName"]["Ref"]

    assert "stale market data" in filters["StaleDataEvents"]["FilterPattern"]
    assert "order failed" in filters["OrderFailureEvents"]["FilterPattern"]
    assert "daily loss limit" in filters["LossBreachEvents"]["FilterPattern"]
    assert "failed to square off" in filters["SquareOffFailureEvents"]["FilterPattern"]


def test_log_derived_alarms_trigger_on_single_safety_event():
    alarms = {
        alarm["MetricName"]: alarm
        for alarm in resources_of_type("AWS::CloudWatch::Alarm")
        if alarm.get("Namespace") == "TradingSystem/Safety"
    }

    for metric_name in [
        "StaleDataEvents",
        "OrderFailureEvents",
        "LossBreachEvents",
        "SquareOffFailureEvents",
    ]:
        alarm = alarms[metric_name]
        assert alarm["Threshold"] == 1
        assert alarm["EvaluationPeriods"] == 1
        assert alarm["ComparisonOperator"] == "GreaterThanOrEqualToThreshold"
        assert alarm["TreatMissingData"] == "notBreaching"
