import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_core_has_no_web_imports():
    """Importing the core in a fresh interpreter must not load any web framework."""
    code = ("import sys, ups.core; "
            "bad=[m for m in ('fastapi','starlette','flask','django','uvicorn','ups.api') if m in sys.modules]; "
            "assert not bad, bad")
    subprocess.run([sys.executable, "-c", code], cwd=ROOT, check=True)
