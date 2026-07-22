from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import boto3

from agent.config import CrossAccountBedrockConfig, settings


@dataclass(frozen=True)
class BedrockSessionInfo:
    boto_session: boto3.Session
    expiration: datetime | None


def build_bedrock_boto_session(config: CrossAccountBedrockConfig | None = None):
    """Return an assumed-role boto3 session for Bedrock, or None when disabled."""
    session_info = build_bedrock_session_info(config)
    return None if session_info is None else session_info.boto_session


def build_bedrock_session_info(config: CrossAccountBedrockConfig | None = None) -> BedrockSessionInfo | None:
    """Return a Bedrock boto session plus STS expiry metadata."""
    bedrock_config = config or settings.cross_account_bedrock
    if not bedrock_config.enabled:
        return None
    if not bedrock_config.role_arn:
        raise ValueError("CROSS_ACCOUNT_BEDROCK_ROLE_ARN is required when cross-account Bedrock is enabled")
    if not bedrock_config.external_id:
        raise ValueError("CROSS_ACCOUNT_BEDROCK_EXTERNAL_ID is required when cross-account Bedrock is enabled")

    sts = boto3.client("sts")
    response = sts.assume_role(
        RoleArn=bedrock_config.role_arn,
        RoleSessionName=bedrock_config.session_name,
        ExternalId=bedrock_config.external_id,
    )
    credentials: dict[str, Any] = response["Credentials"]
    session = boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=bedrock_config.region,
    )
    return BedrockSessionInfo(
        boto_session=session,
        expiration=credentials.get("Expiration"),
    )
