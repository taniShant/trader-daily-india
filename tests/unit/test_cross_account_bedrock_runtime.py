import sys
import types
from datetime import datetime, timedelta, timezone

import pytest

from agent.bedrock_session import build_bedrock_boto_session, build_bedrock_session_info
from agent.config import CrossAccountBedrockConfig, load_settings


def test_cross_account_bedrock_base_defaults_are_disabled():
    assert CrossAccountBedrockConfig().enabled is False


def test_cross_account_bedrock_is_enabled_in_prod_config():
    settings = load_settings("prod", include_env=False)

    assert settings.cross_account_bedrock.enabled is True
    assert settings.cross_account_bedrock.role_arn == "arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role"
    assert settings.cross_account_bedrock.external_id == "trd-bedrock-prod-632-from-873"


def test_cross_account_bedrock_env_overrides(monkeypatch):
    monkeypatch.setenv("CROSS_ACCOUNT_BEDROCK_ENABLED", "true")
    monkeypatch.setenv("CROSS_ACCOUNT_BEDROCK_ROLE_ARN", "arn:aws:iam::111122223333:role/test-bedrock")
    monkeypatch.setenv("CROSS_ACCOUNT_BEDROCK_EXTERNAL_ID", "external-test")
    monkeypatch.setenv("CROSS_ACCOUNT_BEDROCK_REGION", "eu-west-2")
    monkeypatch.setenv("CROSS_ACCOUNT_BEDROCK_SESSION_NAME", "session-test")

    settings = load_settings("prod", include_env=True)

    assert settings.cross_account_bedrock.enabled is True
    assert settings.cross_account_bedrock.role_arn == "arn:aws:iam::111122223333:role/test-bedrock"
    assert settings.cross_account_bedrock.external_id == "external-test"
    assert settings.cross_account_bedrock.region == "eu-west-2"
    assert settings.cross_account_bedrock.session_name == "session-test"


def test_bedrock_session_returns_none_when_disabled():
    session = build_bedrock_boto_session(CrossAccountBedrockConfig(enabled=False))

    assert session is None


def test_bedrock_session_assumes_role_when_enabled(monkeypatch):
    calls = []
    created_sessions = []

    class FakeStsClient:
        def assume_role(self, **kwargs):
            calls.append(kwargs)
            return {
                "Credentials": {
                    "AccessKeyId": "access",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                    "Expiration": datetime.now(timezone.utc),
                }
            }

    class FakeBoto3:
        @staticmethod
        def client(service_name):
            assert service_name == "sts"
            return FakeStsClient()

        class Session:
            def __init__(self, **kwargs):
                created_sessions.append(kwargs)
                self.region_name = kwargs["region_name"]

    monkeypatch.setattr("agent.bedrock_session.boto3", FakeBoto3)

    session = build_bedrock_boto_session(
        CrossAccountBedrockConfig(
            enabled=True,
            role_arn="arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role",
            external_id="trd-bedrock-prod-632-from-873",
            region="eu-west-2",
            session_name="unit-test",
        )
    )

    assert session.region_name == "eu-west-2"
    assert calls == [
        {
            "RoleArn": "arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role",
            "RoleSessionName": "unit-test",
            "ExternalId": "trd-bedrock-prod-632-from-873",
        }
    ]
    assert created_sessions == [
        {
            "aws_access_key_id": "access",
            "aws_secret_access_key": "secret",
            "aws_session_token": "token",
            "region_name": "eu-west-2",
        }
    ]


def test_bedrock_session_info_preserves_sts_expiration(monkeypatch):
    expiration = datetime.now(timezone.utc) + timedelta(minutes=30)

    class FakeStsClient:
        def assume_role(self, **kwargs):
            return {
                "Credentials": {
                    "AccessKeyId": "access",
                    "SecretAccessKey": "secret",
                    "SessionToken": "token",
                    "Expiration": expiration,
                }
            }

    class FakeBoto3:
        @staticmethod
        def client(service_name):
            assert service_name == "sts"
            return FakeStsClient()

        class Session:
            def __init__(self, **kwargs):
                self.region_name = kwargs["region_name"]

    monkeypatch.setattr("agent.bedrock_session.boto3", FakeBoto3)

    session_info = build_bedrock_session_info(
        CrossAccountBedrockConfig(
            enabled=True,
            role_arn="arn:aws:iam::632943041262:role/trd-bedrock-invoke-from-873-role",
            external_id="trd-bedrock-prod-632-from-873",
            region="eu-west-2",
            session_name="unit-test",
        )
    )

    assert session_info is not None
    assert session_info.boto_session.region_name == "eu-west-2"
    assert session_info.expiration == expiration


def test_get_model_keeps_single_account_behavior_when_cross_account_disabled(monkeypatch):
    import agent.main as main_module

    calls = []

    class FakeBedrockModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_strands_models = types.ModuleType("strands.models")
    fake_strands_models.BedrockModel = FakeBedrockModel
    monkeypatch.setitem(sys.modules, "strands.models", fake_strands_models)
    monkeypatch.setattr(main_module, "models", {})

    fake_session_module = types.ModuleType("agent.bedrock_session")
    fake_session_module.build_bedrock_session_info = lambda: None
    monkeypatch.setitem(sys.modules, "agent.bedrock_session", fake_session_module)

    model = main_module.get_model("reasoning")

    assert model is not None
    assert calls[0]["model_id"] == main_module.REASONING_MODEL_ID
    assert calls[0]["region_name"] == main_module.AWS_REGION
    assert "boto_session" not in calls[0]


def test_get_model_uses_assumed_session_when_cross_account_enabled(monkeypatch):
    import agent.main as main_module

    calls = []
    assumed_session = object()
    expiration = datetime.now(timezone.utc) + timedelta(hours=1)

    class FakeBedrockModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_strands_models = types.ModuleType("strands.models")
    fake_strands_models.BedrockModel = FakeBedrockModel
    monkeypatch.setitem(sys.modules, "strands.models", fake_strands_models)
    monkeypatch.setattr(main_module, "models", {})

    fake_session_module = types.ModuleType("agent.bedrock_session")
    fake_session_module.build_bedrock_session_info = lambda: types.SimpleNamespace(
        boto_session=assumed_session,
        expiration=expiration,
    )
    monkeypatch.setitem(sys.modules, "agent.bedrock_session", fake_session_module)

    model = main_module.get_model("reasoning")

    assert model is not None
    assert calls[0]["model_id"] == main_module.REASONING_MODEL_ID
    assert calls[0]["boto_session"] is assumed_session
    assert "region_name" not in calls[0]


def test_get_model_refreshes_assumed_session_before_expiry(monkeypatch):
    import agent.main as main_module

    calls = []
    sessions = [object(), object()]

    class FakeBedrockModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_strands_models = types.ModuleType("strands.models")
    fake_strands_models.BedrockModel = FakeBedrockModel
    monkeypatch.setitem(sys.modules, "strands.models", fake_strands_models)
    monkeypatch.setattr(main_module, "models", {})
    monkeypatch.setattr(main_module, "model_expirations", {})

    expirations = [
        datetime.now(timezone.utc) + timedelta(seconds=30),
        datetime.now(timezone.utc) + timedelta(hours=1),
    ]

    def build_session_info():
        return types.SimpleNamespace(
            boto_session=sessions[len(calls)],
            expiration=expirations[len(calls)],
        )

    fake_session_module = types.ModuleType("agent.bedrock_session")
    fake_session_module.build_bedrock_session_info = build_session_info
    monkeypatch.setitem(sys.modules, "agent.bedrock_session", fake_session_module)

    first_model = main_module.get_model("reasoning")
    second_model = main_module.get_model("reasoning")

    assert first_model is not second_model
    assert calls[0]["boto_session"] is sessions[0]
    assert calls[1]["boto_session"] is sessions[1]


def test_ecs_task_definition_exposes_cross_account_bedrock_env_vars():
    stack_source = open("cicd/cdk/stacks/agent_runtime_stack.py", encoding="utf-8").read()

    for env_name in [
        "CROSS_ACCOUNT_BEDROCK_ENABLED",
        "CROSS_ACCOUNT_BEDROCK_ROLE_ARN",
        "CROSS_ACCOUNT_BEDROCK_EXTERNAL_ID",
        "CROSS_ACCOUNT_BEDROCK_REGION",
        "CROSS_ACCOUNT_BEDROCK_SESSION_NAME",
    ]:
        assert env_name in stack_source


def test_enabled_cross_account_bedrock_requires_role_and_external_id():
    with pytest.raises(ValueError, match="ROLE_ARN"):
        build_bedrock_boto_session(CrossAccountBedrockConfig(enabled=True, external_id="x"))

    with pytest.raises(ValueError, match="EXTERNAL_ID"):
        build_bedrock_boto_session(CrossAccountBedrockConfig(enabled=True, role_arn="arn"))
