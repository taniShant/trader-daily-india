from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def deploy_workflow() -> str:
    return (ROOT / ".github" / "workflows" / "deploy.yml").read_text()


def test_deploy_workflow_supports_manual_dry_run():
    workflow = deploy_workflow()

    assert "dry_run:" in workflow
    assert "Build and synth only; do not push images or deploy" in workflow
    assert "DRY_RUN=${{ github.event.inputs.dry_run }}" in workflow
    assert "if: env.DRY_RUN != 'true'" in workflow


def test_deploy_workflow_uses_github_oidc_role_without_access_keys():
    workflow = deploy_workflow()

    assert "Configure AWS credentials with GitHub OIDC" in workflow
    assert "aws-actions/configure-aws-credentials@v5" in workflow
    assert "role-to-assume: arn:aws:iam::${{ steps.config.outputs.account_id }}:role/${{ steps.config.outputs.deploy_role_name }}" in workflow
    assert "aws-access-key-id" not in workflow
    assert "aws-secret-access-key" not in workflow


def test_deploy_workflow_builds_and_pushes_trading_and_dashboard_images():
    workflow = deploy_workflow()

    assert "containers/trading-bot/Dockerfile" in workflow
    assert "containers/dashboard/Dockerfile" in workflow
    assert "trading-bot-latest" in workflow
    assert "dashboard-latest" in workflow
    assert "trading-bot-${{ steps.config.outputs.image_tag }}" in workflow
    assert "dashboard-${{ steps.config.outputs.image_tag }}" in workflow
    assert "docker push \"${ECR_URI}:trading-bot-latest\"" in workflow
    assert "docker push \"${ECR_URI}:dashboard-latest\"" in workflow


def test_deploy_workflow_refreshes_ecs_services_after_cdk_deploy():
    workflow = deploy_workflow()

    assert "cluster_name=trading-cluster-${CDK_DEPLOY_ENV}" in workflow
    assert "trading_service=trading-bot-${CDK_DEPLOY_ENV}" in workflow
    assert "dashboard_service=dashboard-${CDK_DEPLOY_ENV}" in workflow
    assert "aws ecs update-service" in workflow
    assert "--force-new-deployment" in workflow
    assert "aws ecs wait services-stable" in workflow
