import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_main_model_tasks_are_configured_from_settings():
    import agent.main as main_module

    assert main_module.MODEL_IDS_BY_TASK["fast"] == main_module.FAST_MODEL_ID
    assert main_module.MODEL_IDS_BY_TASK["reasoning"] == main_module.REASONING_MODEL_ID
    assert main_module.MODEL_IDS_BY_TASK["deep_research"] == main_module.DEEP_RESEARCH_MODEL_ID
    assert main_module.MODEL_IDS_BY_TASK["default"] == main_module.MODEL_ID


def test_get_model_lazily_constructs_bedrock_model_by_task(monkeypatch):
    import agent.main as main_module

    calls = []

    class FakeBedrockModel:
        def __init__(self, **kwargs):
            calls.append(kwargs)

    fake_strands_models = types.ModuleType("strands.models")
    fake_strands_models.BedrockModel = FakeBedrockModel
    monkeypatch.setitem(sys.modules, "strands.models", fake_strands_models)
    monkeypatch.setattr(main_module, "models", {})

    reasoning_model = main_module.get_model("reasoning")
    cached_reasoning_model = main_module.get_model("reasoning")
    deep_model = main_module.get_model("deep_research")

    assert reasoning_model is cached_reasoning_model
    assert deep_model is not reasoning_model
    assert calls == [
        {
            "model_id": main_module.REASONING_MODEL_ID,
            "region_name": main_module.AWS_REGION,
            "temperature": 0.2,
            "max_tokens": 4096,
        },
        {
            "model_id": main_module.DEEP_RESEARCH_MODEL_ID,
            "region_name": main_module.AWS_REGION,
            "temperature": 0.2,
            "max_tokens": 4096,
        },
    ]


def test_runtime_source_uses_reasoning_model_for_orchestrator_and_specialists():
    import inspect
    import agent.main as main_module

    source = inspect.getsource(main_module)

    assert 'get_model("reasoning")' in source
    assert "DEEP_RESEARCH_MODEL_ID" in source
    assert "FAST_MODEL_ID" in source


def test_ecs_runtime_wires_model_task_environment_variables():
    stack_source = (ROOT / "cicd" / "stacks" / "agent_runtime_stack.py").read_text()
    entrypoint_source = (ROOT / "containers" / "trading-bot" / "entrypoint.sh").read_text()

    for env_name in [
        "BEDROCK_FAST_MODEL_ID",
        "BEDROCK_REASONING_MODEL_ID",
        "BEDROCK_DEEP_RESEARCH_MODEL_ID",
    ]:
        assert env_name in stack_source
        assert env_name in entrypoint_source

    assert "anthropic.claude-*" in stack_source
