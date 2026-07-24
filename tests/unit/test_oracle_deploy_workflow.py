from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_oracle_deploy_script_targets_static_ip_and_both_services():
    script = (ROOT / "oracle" / "scripts" / "deploy_oracle_services.sh").read_text()

    assert "ORACLE_HOST=\"${ORACLE_HOST:-80.225.242.6}\"" in script
    assert "ORACLE_COLLECTOR_MODE=\"${ORACLE_COLLECTOR_MODE:-live}\"" in script
    assert "rsync -az --delete" in script
    assert "command -v docker-compose" in script
    assert "docker-compose down --remove-orphans || true" in script
    assert "docker-compose up -d --build --remove-orphans" in script
    assert "docker compose down --remove-orphans || true" in script
    assert "docker compose" in script
    assert "ORACLE_PROXY_SHARED_SECRET" in script
    assert "curl -fsS http://127.0.0.1:${ORACLE_PROXY_PORT}/health" in script
    assert "curl -fsS http://127.0.0.1:${ORACLE_COLLECTOR_PORT}/health" in script


def test_oracle_deploy_from_prod_config_loads_icici_values_without_printing_them():
    script = (ROOT / "oracle" / "scripts" / "deploy_from_prod_config.sh").read_text()

    assert "CONFIG_PATH=\"${CONFIG_PATH:-cicd/env/prod.json}\"" in script
    assert "ORACLE_USER=\"${ORACLE_USER:-ubuntu}\"" in script
    assert "ORACLE_SSH_KEY=\"${ORACLE_SSH_KEY:-$HOME/.ssh/oracle-key.key}\"" in script
    assert "read_config oracle.execution_proxy_shared_secret" in script
    assert "read_config icici.api_key" in script
    assert "read_config icici.secret_key" in script
    assert "read_config icici.session_token" in script
    assert "oracle/scripts/deploy_oracle_services.sh" in script


def test_oracle_compose_defines_proxy_and_collector_ports():
    compose = (ROOT / "oracle" / "docker-compose.yml").read_text()

    assert "execution-proxy:" in compose
    assert "collector:" in compose
    assert "${ORACLE_PROXY_PORT:-8080}:8080" in compose
    assert "${ORACLE_COLLECTOR_PORT:-8090}:8090" in compose
    assert "execution-proxy/Dockerfile" in compose
    assert "collector/Dockerfile" in compose


def test_oracle_dockerfiles_match_oracle_build_context():
    proxy_dockerfile = (ROOT / "oracle" / "execution-proxy" / "Dockerfile").read_text()
    collector_dockerfile = (ROOT / "oracle" / "collector" / "Dockerfile").read_text()

    assert "COPY execution-proxy/requirements.txt ./requirements.txt" in proxy_dockerfile
    assert "COPY execution-proxy/app.py ./app.py" in proxy_dockerfile
    assert "COPY execution-proxy/auth.py ./auth.py" in proxy_dockerfile
    assert "COPY execution-proxy/breeze_client.py ./breeze_client.py" in proxy_dockerfile
    assert "COPY execution-proxy/idempotency.py ./idempotency.py" in proxy_dockerfile
    assert "COPY oracle/execution-proxy" not in proxy_dockerfile

    assert "COPY collector/requirements.txt ." in collector_dockerfile
    assert "COPY collector/app.py ." in collector_dockerfile
    assert "COPY oracle/collector" not in collector_dockerfile


def test_oracle_github_workflow_is_manual_and_supports_dry_run():
    workflow = (ROOT / ".github" / "workflows" / "oracle-deploy.yml").read_text()

    assert "workflow_dispatch:" in workflow
    assert "dry_run:" in workflow
    assert "ORACLE_HOST: ${{ secrets.ORACLE_HOST || '80.225.242.6' }}" in workflow
    assert "ORACLE_SSH_PRIVATE_KEY" in workflow
    assert "ORACLE_PROXY_SHARED_SECRET" in workflow
    assert "oracle/scripts/deploy_oracle_services.sh --dry-run" in workflow
    assert "oracle/scripts/deploy_oracle_services.sh" in workflow
