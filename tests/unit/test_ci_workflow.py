from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_ci_workflow_runs_project_verify_gate():
    workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text()

    assert "name: CI" in workflow
    assert "pull_request:" in workflow
    assert "push:" in workflow
    assert "actions/setup-python@v5" in workflow
    assert "python-version: \"3.12\"" in workflow
    assert "npm install -g aws-cdk" in workflow
    assert "python -m pip install -r requirements.txt" in workflow
    assert "run: make verify" in workflow


def test_deploy_workflow_waits_for_successful_ci_on_main():
    workflow = (ROOT / ".github" / "workflows" / "deploy.yml").read_text()

    assert "workflow_run:" in workflow
    assert "workflows:" in workflow
    assert "- CI" in workflow
    assert "types:" in workflow
    assert "- completed" in workflow
    assert "github.event.workflow_run.conclusion == 'success'" in workflow
    assert "workflow_dispatch:" in workflow
