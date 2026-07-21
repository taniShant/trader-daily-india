from __future__ import annotations

from aws_cdk import CfnOutput, Stack, aws_iam as iam
from constructs import Construct


class BedrockProviderRoleStack(Stack):
    """Creates the Bedrock invoke role in the provider account.

    This sidecar stack is intentionally independent from the normal trading
    PlatformStack and AgentRuntimeStack. Removing this file and its companion
    app/config leaves the single-account deployment path unchanged.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        consumer = config["consumer"]
        provider = config["provider"]
        external_id = config["security"]["external_id"]
        model_ids = config["bedrock"]["model_ids"]

        consumer_task_role_arn = (
            f"arn:aws:iam::{consumer['account_id']}:role/{consumer['ecs_task_role_name']}"
        )
        model_arns = [
            f"arn:aws:bedrock:{provider['region']}::foundation-model/{model_id}"
            for model_id in model_ids
        ]

        self.bedrock_invoke_role = iam.Role(
            self,
            "CrossAccountBedrockInvokeRole",
            role_name=provider["bedrock_invoke_role_name"],
            assumed_by=iam.ArnPrincipal(consumer_task_role_arn).with_conditions(
                {"StringEquals": {"sts:ExternalId": external_id}}
            ),
            description=(
                "Allows the trading ECS task role in the consumer account to "
                "invoke approved Bedrock models from this provider account."
            ),
        )
        self.bedrock_invoke_role.add_to_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=[
                    "bedrock:InvokeModel",
                    "bedrock:InvokeModelWithResponseStream",
                    "bedrock:Converse",
                    "bedrock:ConverseStream",
                ],
                resources=model_arns,
            )
        )

        CfnOutput(self, "BedrockProviderRoleArn", value=self.bedrock_invoke_role.role_arn)
        CfnOutput(self, "TrustedConsumerTaskRoleArn", value=consumer_task_role_arn)
        CfnOutput(self, "ExternalId", value=external_id)


class BedrockConsumerPermissionStack(Stack):
    """Adds assume-role permission to the existing ECS task role.

    This stack imports, but does not own, the ECS role created by PlatformStack.
    It is safe to delete this sidecar stack without deleting the ECS role.
    """

    def __init__(self, scope: Construct, construct_id: str, config: dict, **kwargs) -> None:
        super().__init__(scope, construct_id, **kwargs)
        consumer = config["consumer"]
        provider = config["provider"]
        external_id = config["security"]["external_id"]
        provider_role_arn = (
            f"arn:aws:iam::{provider['account_id']}:role/{provider['bedrock_invoke_role_name']}"
        )
        consumer_task_role_arn = (
            f"arn:aws:iam::{consumer['account_id']}:role/{consumer['ecs_task_role_name']}"
        )

        consumer_task_role = iam.Role.from_role_arn(
            self,
            "ImportedTradingEcsTaskRole",
            consumer_task_role_arn,
            mutable=True,
        )
        consumer_task_role.add_to_principal_policy(
            iam.PolicyStatement(
                effect=iam.Effect.ALLOW,
                actions=["sts:AssumeRole"],
                resources=[provider_role_arn],
                conditions={"StringEquals": {"sts:ExternalId": external_id}},
            )
        )

        CfnOutput(self, "ConsumerTaskRoleArn", value=consumer_task_role_arn)
        CfnOutput(self, "AssumableBedrockProviderRoleArn", value=provider_role_arn)
        CfnOutput(self, "ExternalId", value=external_id)
