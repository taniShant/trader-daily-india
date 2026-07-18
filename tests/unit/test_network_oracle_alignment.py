import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
NETWORK_TEMPLATE = ROOT / "cdk.out" / "svc-trd-PlatformStack.template.json"


def test_prod_config_separates_aws_nat_ip_from_oracle_static_ip():
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())

    assert config["vpc"]["vpc_name"] == "trd-vpc"
    assert config["vpc"]["has_nat_gateway"] is False
    assert config["vpc"]["nat_gateways"] == 0
    assert config["oracle"]["static_ip"] == "80.225.242.6"
    assert config["icici"]["static_ip"] == "80.225.242.6"
    assert config["oracle"]["use_for_live_execution"] is True


def test_prod_config_names_created_trading_subnets():
    config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())

    assert config["vpc"]["public_subnet_name"] == "trd-pub-subnet"
    assert config["vpc"]["private_subnet_name"] == "trd-pri-subnet"
    assert config["vpc"]["max_azs"] == 2


def test_network_stack_creates_vpc_and_security_groups():
    source = (ROOT / "cicd" / "stacks" / "platform_stack.py").read_text()

    assert "ec2.Vpc(" in source
    assert "vpc_name=vpc_name" in source
    assert "ec2.SubnetType.PUBLIC" in source
    assert "ec2.SubnetType.PRIVATE_ISOLATED" in source
    assert "TradingEcsSecurityGroup" in source
    assert "DashboardLoadBalancerSecurityGroup" in source
    assert "OracleStaticIp" in source
    assert "self.oracle_static_ip_address = oracle_static_ip" in source
    assert "from_vpc_attributes" not in source
    assert "from_security_group_id" not in source


def test_network_stack_synthesizes_created_vpc_without_nat_gateway():
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

    assert "AWS::EC2::VPC" in resource_types
    assert "AWS::EC2::Subnet" in resource_types
    assert "AWS::EC2::InternetGateway" in resource_types
    assert "AWS::EC2::NatGateway" not in resource_types
    assert "AWS::EC2::EIP" not in resource_types


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
