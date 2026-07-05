import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "oracle" / "scripts" / "deploy_execution_proxy.sh"


def test_oracle_deploy_script_dry_run_is_safe_and_uses_static_ip():
    result = subprocess.run(
        ["bash", str(SCRIPT), "--dry-run"],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
    assert "host: 80.225.242.6" in result.stdout
    assert "dry run: true" in result.stdout
    assert "[dry-run] ssh" in result.stdout
    assert "[dry-run] rsync" in result.stdout
    assert "docker build -t oracle-execution-proxy:latest" in result.stdout
    assert "docker run -d --restart unless-stopped" in result.stdout
    assert "curl -fsS http://127.0.0.1:8080/health" in result.stdout


def test_oracle_deploy_script_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
