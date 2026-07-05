from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_makefile_exposes_phase9_local_runner_targets():
    makefile = (ROOT / "Makefile").read_text()

    for target in [
        "test:",
        "test-unit:",
        "test-integration:",
        "test-dashboard:",
        "smoke:",
        "synth:",
        "deploy-path:",
        "verify:",
    ]:
        assert target in makefile


def test_verify_target_runs_smoke_deploy_path_tests_and_synth():
    makefile = (ROOT / "Makefile").read_text()

    assert "verify: smoke deploy-path test synth" in makefile
    assert "bash scripts/verify_cdk_synth.sh" in makefile
    assert "$(PYTHON) scripts/verify_deploy_path.py" in makefile
