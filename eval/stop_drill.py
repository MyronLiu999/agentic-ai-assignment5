"""Part C's stop drill: start runs, press bin/stop in the middle of each, then resume.

    python eval/stop_drill.py --runs 10                      # on your model (settings.yaml), the dev issues
    python eval/stop_drill.py --runs 2 --backend harness.scripted:SlowTriage   # free, to try it out

For each run: start `run.py --way planned` on the next issue, wait for its live
notification (logs/notifications.jsonl), wait until its trace shows N tool calls
(N drawn from --after, so the stop lands at different points: before any write,
between writes), press bin/stop exactly as a person would, wait for the process to
end, then `run.py --resume <run_id>`. The stop is pressed from outside the run's
process; nothing here touches the run's own code. The latencies come from
logs/stops.jsonl afterwards (eval/lab05_report.py), never from this script.
"""

from __future__ import annotations

import argparse
import json
import os
import random
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

DEV = [4191, 4192]


def lines(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for x in path.read_text().splitlines():
        try:
            out.append(json.loads(x))
        except json.JSONDecodeError:
            continue
    return out


def tool_calls(run_id: str) -> int:
    return sum(1 for r in lines(ROOT / "runs" / f"{run_id}.jsonl") if r.get("type") == "tool_call")


def drill(issue: int, backend: str | None, after: int, env: dict, timeout_s: float) -> str | None:
    seen = {(n.get("run_id"), n.get("at")) for n in lines(ROOT / "logs" / "notifications.jsonl")}
    cmd = [sys.executable, "run.py", "--way", "planned", "--issues", str(issue), "--jobs", "1"]
    if backend:
        cmd += ["--backend", backend]
    proc = subprocess.Popen(cmd, cwd=ROOT, env=env)
    run_id, start = None, time.monotonic()
    while proc.poll() is None and time.monotonic() - start < timeout_s:
        if run_id is None:
            fresh = [n for n in lines(ROOT / "logs" / "notifications.jsonl")
                     if n.get("kind") == "live" and (n.get("run_id"), n.get("at")) not in seen]
            run_id = fresh[0]["run_id"] if fresh else None
        if run_id and tool_calls(run_id) >= after:
            subprocess.run([sys.executable, "bin/stop", run_id], cwd=ROOT, env=env, check=False)
            break
        time.sleep(0.05)
    proc.wait()
    if run_id is None:
        print(f"issue {issue}: the run never went live; nothing stopped")
        return None
    ends = [r.get("terminal_reason") for r in lines(ROOT / "runs" / f"{run_id}.jsonl") if r.get("type") == "end"]
    if ends[-1:] != ["stopped"]:
        print(f"{run_id}: ended {ends[-1:]} before the stop took effect (stop pressed after {after} tool calls)")
        return None
    print(f"{run_id}: stopped after {after} tool calls; resuming")
    subprocess.run([sys.executable, "run.py", "--resume", run_id], cwd=ROOT, env=env, check=False)
    return run_id


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--runs", type=int, default=10)
    p.add_argument("--issues", default=",".join(map(str, DEV)), help="issues to cycle through (default the dev pair)")
    p.add_argument("--backend", help="default: your model in settings.yaml")
    p.add_argument("--after", default="2-5", help="press stop once the trace has this many tool calls: N or LO-HI")
    p.add_argument("--seed", type=int, default=5)
    p.add_argument("--timeout", type=float, default=900, help="seconds to wait for one run")
    a = p.parse_args(argv)
    lo, _, hi = a.after.partition("-")
    rng = random.Random(a.seed)
    env = {**os.environ, "REVIEWER": os.environ.get("REVIEWER") or "scripted:approve-all"}
    issues = [int(x) for x in a.issues.split(",")]
    stopped = []
    for i in range(a.runs):
        after = rng.randint(int(lo), int(hi or lo))
        rid = drill(issues[i % len(issues)], a.backend, after, env, a.timeout)
        if rid:
            stopped.append(rid)
    print(f"\n{len(stopped)} runs stopped and resumed: {' '.join(stopped)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
