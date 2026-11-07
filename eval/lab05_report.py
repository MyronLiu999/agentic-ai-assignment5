"""Fill reports/LAB_05.json's measured fields from what the runs left behind.

    python eval/lab05_report.py            # print what it would write
    python eval/lab05_report.py --write    # and write it

It recomputes, the way checks/check_05.py does and from the same files:
  - replay and batching: bin/replay_policy on the recorded day, with and without --batched;
  - diagnostics: logs/approvals.jsonl, the human approval decisions on your model's runs;
  - stop: logs/stops.jsonl, every stop that took effect on your model's runs;
  - rollback: the latest line of logs/rollbacks.jsonl that bin/rollback wrote.
Everything else (the ranking, the moments, stop.partial_condition, the disclosure
line) is yours, and left as it is. It never asks a model anything.
"""

from __future__ import annotations

import argparse
import json
import statistics
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from checks.check_05 import ROLLUP, irreversible_wide, jsonl, load_runs, stop_events  # noqa: E402
from harness.clock import seconds_between  # noqa: E402

REPORT = ROOT / "reports" / "LAB_05.json"


def replay(batched: bool) -> dict:
    args = [sys.executable, str(ROOT / "bin" / "replay_policy"), ROLLUP, "--json"] + (["--batched"] if batched else [])
    return json.loads(subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout.splitlines()[-1])


def diagnostics(report: dict, real: set[str]) -> dict:
    lines = [a for a in jsonl(ROOT / "logs" / "approvals.jsonl")
             if a.get("reviewer") == "human" and (a.get("kind") or "approval") == "approval" and a.get("run_id") in real]
    decided = [a for a in lines if a.get("decision") in ("approve", "deny")]
    classes = sorted(irreversible_wide(report))
    out = {"decisions": len(decided), "approval_rate_all": None, "approval_rate_irreversible_wide": None,
           "irreversible_wide_classes": classes, "median_seconds_by_class": {}}
    if not decided:
        return out
    out["approval_rate_all"] = round(sum(a["decision"] == "approve" for a in decided) / len(decided), 2)
    wide = [a for a in decided if a.get("action_class") in classes]
    if wide:
        out["approval_rate_irreversible_wide"] = round(sum(a["decision"] == "approve" for a in wide) / len(wide), 2)
    seconds: dict[str, list[float]] = {}
    for a in decided:
        if isinstance(a.get("seconds"), (int, float)):
            seconds.setdefault(a.get("action_class"), []).append(float(a["seconds"]))
    out["median_seconds_by_class"] = {k: round(statistics.median(v), 1) for k, v in sorted(seconds.items())}
    out["decisions_by_class"] = {k: len(v) for k, v in sorted(seconds.items())}
    return out


def stops(report: dict, runs) -> dict:
    found = stop_events({"stop": {}}, runs)            # every stop that took effect on your model's runs
    ids = sorted(found, key=lambda rid: found[rid]["requested"])
    latencies = [seconds_between(found[r]["requested"], found[r]["effective"]) for r in ids]
    old = report.get("stop") if isinstance(report.get("stop"), dict) else {}
    return {"run_ids": ids, "latencies_s": latencies,
            "p50_s": round(statistics.median(latencies), 3) if latencies else None,
            "max_s": max(latencies) if latencies else None,
            "partial_condition": old.get("partial_condition")}


def rollback(report: dict) -> dict:
    done = jsonl(ROOT / "logs" / "rollbacks.jsonl")
    if not done:
        return report.get("rollback") or {"run_id": None, "compensated": [], "none": []}
    run_id = done[-1]["run_id"]                        # the run rolled back last; bin/rollback may run on it twice
    mine = [d for d in done if d["run_id"] == run_id]
    compensated = [c for d in mine for c in d["compensated"]]
    return {"run_id": run_id, "compensated": compensated, "none": mine[-1]["none"]}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--write", action="store_true", help="write reports/LAB_05.json")
    a = p.parse_args(argv)
    report = json.loads(REPORT.read_text())
    runs, _ = load_runs()
    real = {r.run_id for r in runs}
    plain, batched = replay(False), replay(True)
    report["replay"] = plain
    report["batching"] = {"covers": batched.get("covers", []), "prompts_per_day_before": plain["prompts_per_day"],
                          "prompts_per_day_after": batched["prompts_per_day"]}
    report["diagnostics"] = diagnostics(report, real)
    report["stop"] = stops(report, runs)
    report["rollback"] = rollback(report)
    text = json.dumps(report, indent=2) + "\n"
    if a.write:
        REPORT.write_text(text)
        print(f"wrote {REPORT.relative_to(ROOT)}: {len(real)} runs on your model, "
              f"{report['diagnostics']['decisions']} human decisions, {len(report['stop']['run_ids'])} stops")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
