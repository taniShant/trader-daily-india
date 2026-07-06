import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "cdk.out" / "svc-trd-PlatformStack.template.json"


def synth_if_needed():
    if TEMPLATE.exists():
        return
    result = subprocess.run(
        ["bash", "scripts/verify_cdk_synth.sh"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def storage_tables():
    synth_if_needed()
    template = json.loads(TEMPLATE.read_text())
    return {
        resource["Properties"]["TableName"]: resource["Properties"]
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::DynamoDB::Table"
    }


def test_storage_stack_creates_private_artifact_bucket():
    synth_if_needed()
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())
    template = json.loads(TEMPLATE.read_text())
    buckets = [
        resource["Properties"]
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::S3::Bucket"
    ]

    assert len(buckets) == 1
    assert buckets[0]["BucketName"] == config["s3"]["code_bucket"]
    assert buckets[0]["VersioningConfiguration"]["Status"] == "Enabled"


def gsi_names(table):
    return {index["IndexName"] for index in table.get("GlobalSecondaryIndexes", [])}


def test_storage_stack_defines_required_audit_tables():
    tables = storage_tables()

    for table_name in [
        "svc-trd-signals-prod",
        "svc-trd-risk-events-prod",
        "svc-trd-orders-prod",
        "svc-trd-fills-prod",
        "svc-trd-positions-prod",
    ]:
        assert table_name in tables
        assert tables[table_name]["BillingMode"] == "PAY_PER_REQUEST"


def test_audit_tables_have_query_indexes_for_operations_and_dashboard():
    tables = storage_tables()

    assert {"symbol-created-index", "session-created-index"} <= gsi_names(tables["svc-trd-signals-prod"])
    assert {"signal-created-index", "status-created-index"} <= gsi_names(tables["svc-trd-risk-events-prod"])
    assert {"symbol-updated-index", "status-updated-index"} <= gsi_names(tables["svc-trd-orders-prod"])
    assert {"client-order-filled-index", "symbol-filled-index"} <= gsi_names(tables["svc-trd-fills-prod"])
    assert {"session-symbol-index"} <= gsi_names(tables["svc-trd-positions-prod"])


def test_trade_and_execution_audit_tables_have_point_in_time_recovery():
    tables = storage_tables()

    for table_name in [
        "svc-trd-trades-prod",
        "svc-trd-signals-prod",
        "svc-trd-risk-events-prod",
        "svc-trd-orders-prod",
        "svc-trd-fills-prod",
        "svc-trd-positions-prod",
    ]:
        assert tables[table_name]["PointInTimeRecoverySpecification"]["PointInTimeRecoveryEnabled"] is True


def test_runtime_task_gets_audit_table_environment_variables():
    synth_if_needed()
    template = json.loads((ROOT / "cdk.out" / "svc-trd-AgentRuntimeStack.template.json").read_text())
    task_defs = [
        resource
        for resource in template["Resources"].values()
        if resource.get("Type") == "AWS::ECS::TaskDefinition"
    ]
    env_names = {
        env["Name"]
        for task in task_defs
        for container in task["Properties"]["ContainerDefinitions"]
        for env in container.get("Environment", [])
    }

    assert {
        "SIGNALS_TABLE",
        "RISK_EVENTS_TABLE",
        "ORDERS_TABLE",
        "FILLS_TABLE",
        "POSITIONS_TABLE",
    } <= env_names
