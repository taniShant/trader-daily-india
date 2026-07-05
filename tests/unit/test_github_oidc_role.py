import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = ROOT / "cdk.out" / "svc-trd-IamStack.template.json"


def synth_template():
    result = subprocess.run(
        ["bash", "scripts/verify_cdk_synth.sh"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout


def iam_template():
    synth_template()
    return json.loads(TEMPLATE.read_text())


def resources_of_type(resource_type: str):
    return [
        resource
        for resource in iam_template()["Resources"].values()
        if resource.get("Type") == resource_type
    ]


def test_prod_config_declares_existing_github_oidc_provider_arn():
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())

    assert (
        config["github"]["oidc_provider_arn"]
        == "arn:aws:iam::632943041262:oidc-provider/token.actions.githubusercontent.com"
    )


def test_iam_stack_imports_existing_github_actions_oidc_provider():
    providers = resources_of_type("Custom::AWSCDKOpenIdConnectProvider")

    assert providers == []


def test_github_deploy_role_trust_is_limited_to_repo_main_branch():
    roles = resources_of_type("AWS::IAM::Role")
    role = next(role for role in roles if role["Properties"].get("RoleName") == "svc-trd-github-deploy-role")
    statements = role["Properties"]["AssumeRolePolicyDocument"]["Statement"]
    trust = statements[0]

    assert trust["Action"] == "sts:AssumeRoleWithWebIdentity"
    assert trust["Condition"]["StringEquals"]["token.actions.githubusercontent.com:aud"] == "sts.amazonaws.com"
    assert (
        trust["Condition"]["StringLike"]["token.actions.githubusercontent.com:sub"]
        == "repo:taniShant/trader-daily-india:ref:refs/heads/main"
    )
