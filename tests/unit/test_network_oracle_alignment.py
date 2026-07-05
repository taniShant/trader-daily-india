import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NETWORK_TEMPLATE = ROOT / "cdk.out" / "svc-trd-NetworkStack.template.json"


def test_prod_config_separates_aws_nat_ip_from_oracle_static_ip():
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())

    assert config["vpc"]["nat_gateway_ip"] == "35.177.116.82"
    assert config["oracle"]["static_ip"] == "80.225.242.6"
    assert config["icici"]["static_ip"] == "80.225.242.6"
    assert config["vpc"]["nat_gateway_ip"] != config["oracle"]["static_ip"]
    assert config["oracle"]["use_for_live_execution"] is True


def test_network_stack_exports_distinct_aws_nat_and_oracle_static_outputs():
    source = (ROOT / "cicd" / "stacks" / "network_stack.py").read_text()

    assert "AwsNatGatewayIp" in source
    assert "OracleStaticIp" in source
    assert "self.aws_nat_gateway_ip = NAT_GATEWAY_IP" in source
    assert "self.oracle_static_ip_address = ORACLE_STATIC_IP" in source
    assert 'CfnOutput(self, "ElasticIpAddress"' not in source
    assert "icici_config" not in source


def test_network_stack_does_not_mutate_existing_security_groups():
    result = subprocess.run(
        ["bash", "scripts/verify_cdk_synth.sh"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr or result.stdout

    template = json.loads(NETWORK_TEMPLATE.read_text())
    resource_types = {resource.get("Type") for resource in template["Resources"].values()}

    assert "AWS::EC2::SecurityGroupIngress" not in resource_types
    assert "AWS::EC2::SecurityGroupEgress" not in resource_types


def test_runtime_text_does_not_describe_oracle_static_ip_as_aws_nat():
    checked_files = [
        ROOT / "agent" / "main.py",
        ROOT / "agent" / "mcp_integration.py",
        ROOT / "containers" / "trading-bot" / "entrypoint.sh",
        ROOT / "cicd" / "stacks" / "agent_runtime_stack.py",
    ]

    combined = "\n".join(path.read_text() for path in checked_files)

    assert "3.8.245.57" not in combined
    assert "NAT Gateway - traffic appears from this IP" not in combined
    assert "Static IP (NAT)" not in combined
