import subprocess
import sys
from pathlib import Path


def test_active_deploy_path_is_consistent():
    result = subprocess.run(
        [sys.executable, "scripts/verify_deploy_path.py"],
        cwd=Path(__file__).resolve().parents[2],
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr or result.stdout
