from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_oracle_deploy_script_targets_static_ip_and_both_services():
    script = (ROOT / "oracle" / "scripts" / "deploy_oracle_services.sh").read_text()

    assert "ORACLE_HOST=\"${ORACLE_HOST:-80.225.242.6}\"" in script
    assert "rsync -az --delete" in script
    assert "docker compose" in script
    assert "ORACLE_PROXY_SHARED_SECRET" in script
    assert "curl -fsS http://127.0.0.1:${ORACLE_PROXY_PORT}/health" in script
    assert "curl -fsS http://127.0.0.1:${ORACLE_COLLECTOR_PORT}/health" in script


def test_oracle_compose_defines_proxy_and_collector_ports():
    compose = (ROOT / "oracle" / "docker-compose.yml").read_text()

    assert "execution-proxy:" in compose
    assert "collector:" in compose
    assert "${ORACLE_PROXY_PORT:-8080}:8080" in compose
    assert "${ORACLE_COLLECTOR_PORT:-8090}:8090" in compose
    assert "execution-proxy/Dockerfile" in compose
    assert "collector/Dockerfile" in compose


def test_oracle_github_workflow_is_manual_and_supports_dry_run():
    workflow = (ROOT / ".github" / "workflows" / "oracle-deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "dry_run:" in workflow
    assert "ORACLE_HOST: ${{ secrets.ORACLE_HOST || '80.225.242.6' }}" in workflow
    assert "ORACLE_SSH_PRIVATE_KEY" in workflow
    assert "ORACLE_PROXY_SHARED_SECRET" in workflow
    assert "oracle/scripts/deploy_oracle_services.sh --dry-run" in workflow
    assert "oracle/scripts/deploy_oracle_services.sh" in workflow
