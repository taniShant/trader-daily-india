import json
import os
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "cicd" / "env" / "cross-account-bedrock.json"
APP = ROOT / "cicd" / "apps" / "cross_account_bedrock_app.py"
OUT = ROOT / "cdk.out"
PROVIDER_TEMPLATE = OUT / "svc-trd-BedrockProviderRoleStack.template.json"
CONSUMER_TEMPLATE = OUT / "svc-trd-BedrockConsumerPermissionStack.template.json"


def synth_sidecar():
    python_bin = ROOT / ".venv" / "bin" / "python"
    interpreter = str(python_bin) if python_bin.exists() else "python"
    env = dict(os.environ)
    env["HOME"] = str(ROOT / ".tmp-home")
    env["XDG_CACHE_HOME"] = str(ROOT / ".cdk-cache")
    (ROOT / ".tmp-home").mkdir(exist_ok=True)
    (ROOT / ".cdk-cache").mkdir(exist_ok=True)
    result = subprocess.run(
        ["cdk", "-a", f"{interpreter} {APP}", "synth"],
        cwd=ROOT,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def test_cross_account_bedrock_config_is_separate_from_prod_runtime_config():
    config = json.loads(CONFIG.read_text())
    app_source = (ROOT / "app.py").read_text()
    doc = (ROOT / "docs" / "cross_account_bedrock_sidecar.md").read_text()

    assert "cross_account_bedrock" not in app_source
    assert "Deleting these files removes the sidecar" in doc
    assert config["consumer"]["account_id"] == "873660758628"
    assert config["provider"]["account_id"] == "632943041262"
    assert config["provider"]["bedrock_invoke_role_name"] == "trd-bedrock-invoke-from-873-role"
    assert config["security"]["external_id"] == "trd-bedrock-prod-632-from-873"


def test_sidecar_app_synthesizes_provider_and_consumer_templates():
    synth_sidecar()

    assert PROVIDER_TEMPLATE.exists()
    assert CONSUMER_TEMPLATE.exists()


def test_provider_role_trusts_only_consumer_ecs_task_role_with_external_id():
    synth_sidecar()
    config = json.loads(CONFIG.read_text())
    template = json.loads(PROVIDER_TEMPLATE.read_text())
    roles = [
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Role"
    ]
    role = roles[0]
    statement = role["Properties"]["AssumeRolePolicyDocument"]["Statement"][0]

    assert role["Properties"]["RoleName"] == config["provider"]["bedrock_invoke_role_name"]
    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Principal"]["AWS"] == (
        f"arn:aws:iam::{config['consumer']['account_id']}:role/{config['consumer']['ecs_task_role_name']}"
    )
    assert statement["Condition"]["StringEquals"]["sts:ExternalId"] == config["security"]["external_id"]


def test_provider_role_allows_only_configured_bedrock_models():
    synth_sidecar()
    config = json.loads(CONFIG.read_text())
    template = json.loads(PROVIDER_TEMPLATE.read_text())
    policies = [
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
    ]
    statement = policies[0]["Properties"]["PolicyDocument"]["Statement"][0]

    assert set(statement["Action"]) == {
        "bedrock:InvokeModel",
        "bedrock:InvokeModelWithResponseStream",
        "bedrock:Converse",
        "bedrock:ConverseStream",
    }
    assert set(statement["Resource"]) == {
        f"arn:aws:bedrock:{config['provider']['region']}::foundation-model/{model_id}"
        for model_id in config["bedrock"]["model_ids"]
    }


def test_consumer_policy_only_allows_assuming_provider_role_with_external_id():
    synth_sidecar()
    config = json.loads(CONFIG.read_text())
    template = json.loads(CONSUMER_TEMPLATE.read_text())
    policies = [
        resource
        for resource in template["Resources"].values()
        if resource["Type"] == "AWS::IAM::Policy"
    ]
    statement = policies[0]["Properties"]["PolicyDocument"]["Statement"][0]

    assert statement["Action"] == "sts:AssumeRole"
    assert statement["Resource"] == (
        f"arn:aws:iam::{config['provider']['account_id']}:role/{config['provider']['bedrock_invoke_role_name']}"
    )
    assert statement["Condition"]["StringEquals"]["sts:ExternalId"] == config["security"]["external_id"]
