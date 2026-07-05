import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "verify_cdk_synth.sh"


def test_cdk_synth_script_syntax_is_valid():
    result = subprocess.run(
        ["bash", "-n", str(SCRIPT)],
        cwd=ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr


def test_cdk_synth_script_uses_project_venv_and_local_cache():
    text = SCRIPT.read_text()

    assert ".venv/bin/python" in text
    assert "XDG_CACHE_HOME" in text
    assert ".cdk-cache" in text
    assert ".tmp-home" in text
    assert "cdk synth" in text
