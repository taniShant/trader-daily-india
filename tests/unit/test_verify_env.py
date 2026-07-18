import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_env.py"


def test_verify_env_dry_run_reads_prod_config_without_network():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--env", "prod", "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "[OK] Config account:" in result.stdout
    assert "svc-trd-PlatformStack" in result.stdout
    assert "svc-trd-AgentRuntimeStack" in result.stdout
    assert "trading-bot-prod" in result.stdout
    assert "dashboard-prod" in result.stdout
    assert "80.225.242.6:8080/health" in result.stdout
    assert "environment verification passed" in result.stdout


def test_verify_env_checks_real_runtime_surfaces():
    source = SCRIPT.read_text()

    assert "describe_stacks" in source
    assert "describe_table" in source
    assert "describe_services" in source
    assert "describe_repositories" in source
    assert "execution_proxy_health_url" in source
    assert "collector_health_url" in source
    assert "/api/health" in source
    assert "allow-degraded" in source
