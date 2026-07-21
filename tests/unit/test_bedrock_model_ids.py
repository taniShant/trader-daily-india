import json
from pathlib import Path

from agent.config import BedrockConfig


ROOT = Path(__file__).resolve().parents[2]
INVALID_BEDROCK_MODEL_IDS = {
    "anthropic.claude-3-haiku-20240307-v1:0",
    "anthropic.claude-haiku-4-5-20251001-v1:0",
    "anthropic.claude-3-5-sonnet-20241022-v2:0",
    "us.anthropic.claude-3-5-sonnet-20241022-v2:0",
    "anthropic.claude-3-opus-20240229-v1:0",
}


def test_default_bedrock_model_ids_avoid_known_invalid_runtime_ids():
    defaults = BedrockConfig()

    assert defaults.model_id not in INVALID_BEDROCK_MODEL_IDS
    assert defaults.fast_model_id not in INVALID_BEDROCK_MODEL_IDS
    assert defaults.reasoning_model_id not in INVALID_BEDROCK_MODEL_IDS
    assert defaults.deep_research_model_id not in INVALID_BEDROCK_MODEL_IDS


def test_prod_bedrock_model_ids_avoid_known_invalid_runtime_ids():
    prod_config = json.loads((ROOT / "cicd" / "env" / "prod.json").read_text())
    bedrock_config = prod_config["bedrock"]

    for key in ["model_id", "fast_model_id", "reasoning_model_id", "deep_research_model_id"]:
        assert bedrock_config[key] not in INVALID_BEDROCK_MODEL_IDS


def test_trading_container_startup_defaults_avoid_known_invalid_runtime_ids():
    entrypoint = (ROOT / "containers" / "trading-bot" / "entrypoint.sh").read_text()

    for model_id in INVALID_BEDROCK_MODEL_IDS:
        assert model_id not in entrypoint
