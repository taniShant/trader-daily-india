from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
ENTRYPOINT = ROOT / "containers" / "trading-bot" / "entrypoint.sh"
AGENT_RUNTIME_STACK = ROOT / "cicd" / "cdk" / "stacks" / "agent_runtime_stack.py"


def test_trading_entrypoint_does_not_require_icici_credentials_in_aws_paper_mode():
    source = ENTRYPOINT.read_text()

    assert "Paper mode enabled - ICICI credentials are not required in AWS" in source
    assert "Trading bot will not start without ICICI credentials" not in source
    assert "ICICI credentials must remain on the Oracle static-IP proxy" in source


def test_trading_entrypoint_live_mode_requires_oracle_proxy_secret():
    source = ENTRYPOINT.read_text()

    assert 'if [ -z "$ORACLE_EXECUTION_PROXY_BASE_URL" ]; then' in source
    assert 'if [ -z "$ORACLE_PROXY_SHARED_SECRET" ]; then' in source
    assert "In paper mode no execution secret is required; in live mode AWS needs Oracle proxy signing credentials." in source


def test_agent_runtime_stack_passes_oracle_proxy_secret_to_trading_task():
    source = AGENT_RUNTIME_STACK.read_text()

    assert 'oracle_proxy_shared_secret = oracle_config.get("execution_proxy_shared_secret", "")' in source
    assert '"ORACLE_PROXY_SHARED_SECRET": oracle_proxy_shared_secret' in source
