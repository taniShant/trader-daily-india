"""
Network Stack - IMPORTS all existing resources (no creation)

This stack imports:
- VPC
- Public and Private Subnets
- Security Groups (ECS, Load Balancer, Bastion)
- AWS NAT Gateway and NAT public IP (reference only)

Oracle owns the ICICI Breeze whitelisted static IP. AWS NAT is not used as the
ICICI execution boundary.

No new resources are created - all come from cicd/env/dev.json or cicd/env/prod.json
"""

from aws_cdk import (
    Stack,
    CfnOutput,
    aws_ec2 as ec2,
)
from constructs import Construct

class NetworkStack(Stack):
    """
    Network Stack that imports existing VPC, subnets, and security groups.
    Creates NO new resources - strictly imports.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)

        # ============================================================
        # LOAD CONFIGURATION
        # ============================================================
        
        vpc_config = config.get("vpc", {})
        sg_config = config.get("security_groups", {})
        oracle_config = config.get("oracle", {})
        
        VPC_ID = vpc_config.get("vpc_id")
        PUBLIC_SUBNET_ID = vpc_config.get("public_subnet_id")
        PRIVATE_SUBNET_ID = vpc_config.get("private_subnet_id")
        
        ECS_SG_ID = sg_config.get("ecs_sg_id")
        LB_SG_ID = sg_config.get("load_balancer_sg_id")
        BASTION_SG_ID = sg_config.get("bastion_sg_id")
        
        NAT_GATEWAY_IP = vpc_config.get("nat_gateway_ip", "")
        ORACLE_STATIC_IP = oracle_config.get("static_ip", "")
        NAT_GATEWAY_ID = vpc_config.get("nat_gateway_id")
        NAT_EIP_ALLOCATION_ID = vpc_config.get("nat_eip_allocation_id")
        
        print(f"📋 Environment: {config.get('environment', 'unknown')}")
        print(f"📍 VPC ID: {VPC_ID}")
        print(f"🌐 Public Subnet: {PUBLIC_SUBNET_ID}")
        print(f"🔒 Private Subnet: {PRIVATE_SUBNET_ID}")
        print(f"🔐 ECS Security Group: {ECS_SG_ID}")
        print(f"🔐 Load Balancer Security Group: {LB_SG_ID}")
        print(f"🌍 AWS NAT Gateway IP: {NAT_GATEWAY_IP}")
        print(f"🌐 Oracle ICICI Static IP: {ORACLE_STATIC_IP}")
        print(f"🖥️  NAT Gateway ID: {NAT_GATEWAY_ID}")
        
        # ============================================================
        # IMPORT EXISTING VPC
        # ============================================================
        
        self.vpc = ec2.Vpc.from_vpc_attributes(
            self, "ExistingVPC",
            vpc_id=VPC_ID,
            availability_zones=["eu-west-2a"],
            public_subnet_ids=[PUBLIC_SUBNET_ID],
            private_subnet_ids=[PRIVATE_SUBNET_ID],
        )
        
        # ============================================================
        # IMPORT EXISTING SUBNETS
        # ============================================================
        
        self.public_subnet = ec2.Subnet.from_subnet_attributes(
            self, "PublicSubnet",
            subnet_id=PUBLIC_SUBNET_ID,
            availability_zone="eu-west-2a",
        )
        
        self.private_subnet = ec2.Subnet.from_subnet_attributes(
            self, "PrivateSubnet",
            subnet_id=PRIVATE_SUBNET_ID,
            availability_zone="eu-west-2a",
        )
        
        # ============================================================
        # IMPORT EXISTING SECURITY GROUPS (NO CREATION)
        # ============================================================
        
        self.ecs_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ExistingECSSG",
            security_group_id=ECS_SG_ID,
            mutable=False,
        )
        
        self.load_balancer_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ExistingLBSG",
            security_group_id=LB_SG_ID,
            mutable=False,
        )
        
        self.bastion_security_group = ec2.SecurityGroup.from_security_group_id(
            self, "ExistingBastionSG",
            security_group_id=BASTION_SG_ID,
            mutable=False,
        )
        
        # ============================================================
        # REFERENCE EXISTING NAT GATEWAY AND EIP (NO CREATION)
        # ============================================================
        
        # Store for reference by other stacks
        self.nat_gateway_id = NAT_GATEWAY_ID
        self.aws_nat_gateway_ip = NAT_GATEWAY_IP
        self.oracle_static_ip_address = ORACLE_STATIC_IP
        self.nat_eip_allocation_id = NAT_EIP_ALLOCATION_ID
        
        # ============================================================
        # NO EC2 NAT INSTANCE - Using existing NAT Gateway
        # ============================================================
        self.nat_instance = None
        
        # ============================================================
        # EXPORTS (for other stacks to use)
        # ============================================================
        
        CfnOutput(self, "VpcId", 
            value=self.vpc.vpc_id, 
            export_name=f"{construct_id}:VpcId"
        )
        
        CfnOutput(self, "PublicSubnetId", 
            value=PUBLIC_SUBNET_ID, 
            export_name=f"{construct_id}:PublicSubnetId"
        )
        
        CfnOutput(self, "PrivateSubnetId", 
            value=PRIVATE_SUBNET_ID, 
            export_name=f"{construct_id}:PrivateSubnetId"
        )
        
        CfnOutput(self, "EcsSecurityGroupId", 
            value=ECS_SG_ID, 
            export_name=f"{construct_id}:EcsSecurityGroupId"
        )
        
        CfnOutput(self, "LoadBalancerSecurityGroupId", 
            value=LB_SG_ID, 
            export_name=f"{construct_id}:LoadBalancerSecurityGroupId"
        )
        
        CfnOutput(self, "BastionSecurityGroupId", 
            value=BASTION_SG_ID, 
            export_name=f"{construct_id}:BastionSecurityGroupId"
        )
        
        CfnOutput(self, "AwsNatGatewayIp", 
            value=NAT_GATEWAY_IP, 
            export_name=f"{construct_id}:AwsNatGatewayIp"
        )

        CfnOutput(self, "OracleStaticIp", 
            value=ORACLE_STATIC_IP, 
            export_name=f"{construct_id}:OracleStaticIp"
        )
        
        CfnOutput(self, "NatGatewayId", 
            value=NAT_GATEWAY_ID, 
            export_name=f"{construct_id}:NatGatewayId"
        )
        
        print("\n" + "="*60)
        print("✅ Network Stack Configured (Import Only - No Creation)")
        print(f"🌐 VPC: {VPC_ID}")
        print(f"🔒 Private Subnet: {PRIVATE_SUBNET_ID}")
        print(f"🌍 AWS NAT Gateway IP: {NAT_GATEWAY_IP}")
        print(f"🌐 Oracle ICICI Static IP: {ORACLE_STATIC_IP}")
        print(f"🖥️  NAT Gateway ID: {NAT_GATEWAY_ID}")
        print("="*60 + "\n")
