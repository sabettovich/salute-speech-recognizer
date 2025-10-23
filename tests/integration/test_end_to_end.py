import os
import subprocess
import sys
import pathlib
import pytest

pytestmark = pytest.mark.integration


@pytest.mark.integration
def test_end_to_end_grpc(tmp_path):
    # Require auth key
    if not os.getenv("SBER_SPEECH_AUTH_KEY") and not os.getenv("SBER_SPEECH_API_KEY"):
        pytest.skip("No SBER_SPEECH_AUTH_KEY set")

    proj = pathlib.Path(__file__).resolve().parents[2]
    audio = proj / "Source" / "audio.mp3"
    assert audio.exists(), f"Input audio not found: {audio}"

    out_md = proj / "Result" / "audio.md"
    # Run via existing script to avoid relying on console entry registration in tests
    cmd = [
        str(proj / "venv" / "bin" / "python"),
        str(proj / "ss_recognize.py"),
        "--input",
        str(audio),
        "--api",
        "grpc",
    ]
    env = os.environ.copy()
    proc = subprocess.run(cmd, cwd=str(proj), env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    assert proc.returncode == 0, f"recognize failed: rc={proc.returncode}\nstdout={proc.stdout}\nstderr={proc.stderr}"

    # Check outputs
    assert out_md.exists(), f"Markdown not generated: {out_md}"
    raw = proj / "Result" / "audio.grpc.raw.json"
    norm = proj / "Result" / "audio.grpc.norm.json"
    assert raw.exists(), "Raw JSON not generated"
    assert norm.exists(), "Norm JSON not generated"

    # Non-empty checks
    assert out_md.stat().st_size > 10
    assert raw.stat().st_size > 10
    assert norm.stat().st_size > 10
