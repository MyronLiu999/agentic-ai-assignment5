"""Run a command with .env loaded, from any shell (PowerShell included).

    .venv\\Scripts\\python eval\\with_env.py run.py --way planned --set day
    .venv\\Scripts\\python eval\\with_env.py -m harness.ping

Reads KEY=VALUE lines from .env (blank lines and # comments skipped), adds them to
the environment without printing them, and runs the rest of the command line with
this same Python. A non-empty value in .env wins over the shell's.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load(path: Path) -> dict[str, str]:
    out = {}
    if not path.exists():
        return out
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip("'\"")
    return out


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    # .env wins: a stale variable already in the environment (this machine had a
    # one-character OPENAI_API_KEY set) must not shadow the key pasted into .env.
    env = {**os.environ, **{k: v for k, v in load(ROOT / ".env").items() if v}}
    if not env.get("OPENAI_API_KEY"):
        print("warning: OPENAI_API_KEY is empty: paste your key into .env", file=sys.stderr)
    return subprocess.call([sys.executable, *sys.argv[1:]], cwd=ROOT, env=env)


if __name__ == "__main__":
    sys.exit(main())
