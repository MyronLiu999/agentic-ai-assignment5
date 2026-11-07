"""RepoMind's autonomy policy, enforced before every tool call (Assignment 5).

The registry (tools/__init__.py) runs Policy, one per run, as its hook: hook(name,
args) returns None to allow a call, and a reason to refuse it. The model never sees
the policy; it only learns that a call was not allowed. Everything here is decided
from the call's arguments and the facts the harness computes (harness/facts.py),
never from what the model says.

Before every call, in this order:

  1. The stop. A run that bin/stop stopped has every further call refused; the
     first refusal writes the stop's `effective` line (logs/stops.jsonl).
  2. The class. The action (Lecture 5's name, harness.roles.action_of) and its
     circumstance, from the facts: action_class(). The column is read from
     policy/autonomy.yaml: placement(). bin/replay_policy places the recorded day
     with these same two functions.
  3. The boundary. A rule a user stated to this run through the inbox
     (policy/rules.jsonl): a call whose facts' paths match a denied glob is refused.
  4. Prohibited: refused, whoever would answer.
  5. Disclosure (Part D): a comment whose body does not carry DISCLOSURE after its
     first two lines is refused, before anybody is asked.
  6. Requires approval: the reviewer is asked (harness.reviewer) and the run waits.
     Approve runs the call; deny refuses it ("declined"); no answer before the
     timeout refuses it ("no_answer") and the way holds the run: never a yes. A stop
     that arrives during the wait withdraws the request.
  7. Independent: allowed.

Every refusal is a line in logs/hook.jsonl; every answer the hook or an escalation
asked for is a line in logs/approvals.jsonl (checks/FORMATS.md, sections 13.4, 13.7).
The hook fails closed: anything it raises becomes a refusal with reason "error".
"""

from __future__ import annotations

import json
import os
import re
import threading
from pathlib import Path

import yaml

from harness import ROOT
from harness.clock import now
from harness.formats import BOUNDARY, COLUMNS, normalize_path

POLICY_DIR = Path(__file__).resolve().parent
AUTONOMY = POLICY_DIR / "autonomy.yaml"
RULES = POLICY_DIR / "rules.jsonl"
LOGS = ROOT / "logs"
HOOK_LOG = LOGS / "hook.jsonl"
APPROVALS = LOGS / "approvals.jsonl"
STOPS = LOGS / "stops.jsonl"

# Part D: the line every comment RepoMind posts carries, after its label and file lines.
# Plain ASCII on purpose: every log and fixture here is read with the platform's encoding.
DISCLOSURE = ("Written by RepoMind, an AI triage assistant, not by a person; "
              "a Ledgerline maintainer reviews its work.")

ACTIVE_MINUTES = 60          # a thread a person wrote in within this many minutes is a live conversation
TIMEOUT_ENV = "REPOMIND_APPROVAL_TIMEOUT_S"
DEFAULT_TIMEOUT_S = 1800.0   # half an hour for a person to answer; then the run holds
HALTING = ("no_answer", "stopped")   # refusals after which the way ends the run held or stopped

_lock = threading.RLock()     # reentrant: mark_effective holds it across a read and an append


# -- placement: the same code for a live call and a line of the recorded day ---------------------

def circumstance(action: str, facts: dict) -> str | None:
    """The circumstance that splits an action into classes, or None for an action with one class."""
    facts = facts or {}
    if action == "post_comment":
        minutes = facts.get("minutes_since_human_comment")
        if isinstance(minutes, (int, float)) and minutes <= ACTIVE_MINUTES:
            return "human_active"
        return "agent_opened" if facts.get("issue_opened_by_agent") else "human_quiet"
    if action == "push_commit":
        if facts.get("branch_protected"):
            return "protected_branch"
        return "agent_branch" if facts.get("target_created_by_agent") else "shared_branch"
    return None


def action_class(action: str, facts: dict) -> str:
    found = circumstance(action, facts)
    return f"{action}/{found}" if found else action


def load_policy(path: Path = AUTONOMY) -> dict[str, str]:
    """{action_class: column}, from policy/autonomy.yaml."""
    data = yaml.safe_load(Path(path).read_text()) or {}
    placed = {}
    for column in COLUMNS:
        for klass in data.get(column) or []:
            placed[str(klass)] = column
    return placed


def placement(action: str, facts: dict, policy: dict[str, str] | None = None) -> tuple[str, str]:
    """(action_class, column). A class the policy does not place is prohibited: fail closed."""
    policy = policy if policy is not None else load_policy()
    klass = action_class(action, facts)
    return klass, policy.get(klass) or policy.get(action) or "prohibited"


# -- the boundary: rules a user stated through the inbox -------------------------------------------

def glob_regex(glob: str) -> re.Pattern:
    """A path glob: ** matches any number of directories, * any characters within one."""
    out, i = "", 0
    while i < len(glob):
        if glob.startswith("**/", i):
            out, i = out + "(?:.*/)?", i + 3
        elif glob.startswith("**", i):
            out, i = out + ".*", i + 2
        elif glob[i] == "*":
            out, i = out + "[^/]*", i + 1
        elif glob[i] == "?":
            out, i = out + "[^/]", i + 1
        else:
            out, i = out + re.escape(glob[i]), i + 1
    return re.compile(f"^{out}$")


def crosses(path: str, glob: str) -> bool:
    p = normalize_path(str(path)) or ""
    g = normalize_path(str(glob)) or ""
    return bool(glob_regex(g).match(p)) or bool(glob_regex(g).match(p.rstrip("/") + "/"))


def add_rule(run_id: str, message: dict) -> dict | None:
    """Parse one inbox message. A boundary becomes a deny rule for this run, in
    policy/rules.jsonl, and is returned; anything else returns None."""
    match = BOUNDARY.match(str(message.get("text") or ""))
    if not match:
        return None
    rule = {"run_id": run_id, "effect": "deny", "path": match.group(1),
            "stated_at": message.get("delivered_at") or now(), "message": message.get("text")}
    _append(RULES, rule)
    return rule


def rules(run_id: str) -> list[dict]:
    return [r for r in _read(RULES) if r.get("run_id") == run_id and r.get("effect") == "deny"]


# -- the stop: logs/stops.jsonl ----------------------------------------------------------------------

def stop_events(run_id: str) -> list[dict]:
    return [e for e in _read(STOPS) if e.get("run_id") == run_id]


def is_stopped(run_id: str) -> bool:
    """A stop was requested for this run and no resume has lifted it since."""
    state = None
    for e in stop_events(run_id):
        if e.get("event") in ("requested", "lifted"):
            state = e["event"]
    return state == "requested"


def needs_effective(run_id: str) -> bool:
    """The latest request has no effective line yet."""
    waiting = False
    for e in stop_events(run_id):
        if e.get("event") == "requested":
            waiting = True
        elif e.get("event") == "effective":
            waiting = False
    return waiting


def request_stop(run_id: str) -> dict:
    line = {"run_id": run_id, "event": "requested", "at": now()}
    _append(STOPS, line)
    return line


def lift_stop(run_id: str) -> dict | None:
    """A resume lifts a stop: the `lifted` line, if the run is stopped."""
    if not is_stopped(run_id):
        return None
    line = {"run_id": run_id, "event": "lifted", "at": now()}
    _append(STOPS, line)
    return line


# -- the disclosure line (Part D) ----------------------------------------------------------------------

def discloses(body: str) -> bool:
    return any(line.strip() == DISCLOSURE for line in str(body or "").splitlines()[2:])


# -- the hook ------------------------------------------------------------------------------------------------

class Policy:
    """The registry's hook for one run. `last` is what happened to the latest call:
    None when it was allowed, else {"reason", "action", "action_class", "column"};
    the way reads it to hold or stop the run."""

    __name__ = "autonomy_policy"

    def __init__(self, ctx):
        self.ctx = ctx
        self.policy = load_policy()
        self.last: dict | None = None

    @property
    def run_id(self) -> str:
        return self.ctx.run_id

    # The registry calls this before every call.
    def __call__(self, name: str, args: dict):
        self.last = None
        action = None
        try:
            from harness.roles import action_of
            action = action_of(name)
            if action is None:
                return None          # not one of the ten: the registry's protocol check handles it
            return self.decide(action, args or {})
        except Exception as exc:  # fail closed
            return self.refuse(action or name, action or name, None, "error", args,
                               f"the policy could not decide ({type(exc).__name__}: {exc}), so the call is refused")

    def facts(self, action: str, args: dict) -> dict:
        return self.ctx.tracker.facts(self.run_id, action, args, getattr(self.ctx, "issue", None))

    def decide(self, action: str, args: dict):
        if is_stopped(self.run_id):
            return self.stopped(action, action, args)
        facts = self.facts(action, args)
        klass, column = placement(action, facts, self.policy)
        for rule in rules(self.run_id):
            hit = next((p for p in facts.get("paths") or [] if crosses(p, rule["path"])), None)
            if hit is not None:
                return self.refuse(action, klass, None, "boundary", args,
                                   f"{hit} is outside what this run may touch (a user's boundary: deny "
                                   f"{rule['path']})")
        if column == "prohibited":
            return self.refuse(action, klass, column, "prohibited", args,
                               f"{klass} is never done by RepoMind; a person does it")
        if action == "post_comment" and not discloses(args.get(_arg("comment", "body"))):
            return self.refuse(action, klass, None, "disclosure", args,
                               "every comment must say, after its label and file lines, that RepoMind wrote it")
        if column == "requires_approval":
            return self.ask(action, klass, column, args, facts)
        return None

    # -- asking a person --------------------------------------------------------------------------------------
    def ask(self, action: str, klass: str, column: str, args: dict, facts: dict):
        from harness.reviewer import Reviewer
        reviewer = Reviewer.from_env()
        request = {"run_id": self.run_id, "action": action, "action_class": klass, "args": args, "facts": facts,
                   "kind": "approval", "column": column, "issue": facts.get("issue")}
        answer = reviewer.ask(request, timeout_s=timeout_s(), until=lambda: is_stopped(self.run_id))
        log_decision(self.run_id, action, klass, facts, "approval", answer, reviewer)
        if answer is not None and answer.get("decision") == "approve":
            return None
        if answer is not None:
            return self.refuse(action, klass, column, "declined", args, "the reviewer declined this call")
        if is_stopped(self.run_id):          # the stop withdrew the wait
            return self.stopped(action, klass, args)
        return self.refuse(action, klass, column, "no_answer", args,
                           "nobody answered before the timeout; the run holds until a person answers")

    # -- refusals ------------------------------------------------------------------------------------------
    def stopped(self, action: str, klass: str, args: dict):
        mark_effective(self.run_id, action)
        return self.refuse(action, klass, None, "stopped", args, "this run was stopped by a person (bin/stop)")

    def refuse(self, action, klass, column, reason: str, args, text: str) -> str:
        self.last = {"reason": reason, "action": action, "action_class": klass, "column": column}
        _append(HOOK_LOG, {"at": now(), "run_id": self.run_id, "action": action, "action_class": klass,
                           "column": column, "reason": reason, "args": args})
        return f"{text} [{reason}]"

    # -- for the way ------------------------------------------------------------------------------------
    def check_stop(self, action: str | None) -> bool:
        """Before a model call: True when the run is stopped, after recording the hook's
        refusal of the call that model call was for (the stop takes effect there)."""
        if not is_stopped(self.run_id):
            return False
        self.stopped(action or "read_issue", action or "read_issue", {})
        return True


def mark_effective(run_id: str, action: str) -> None:
    with _lock:
        if needs_effective(run_id):
            _append(STOPS, {"run_id": run_id, "event": "effective", "at": now(), "action": action})


def timeout_s() -> float:
    try:
        return float(os.environ.get(TIMEOUT_ENV) or DEFAULT_TIMEOUT_S)
    except ValueError:
        return DEFAULT_TIMEOUT_S


def log_decision(run_id: str, action: str, klass: str, facts: dict, kind: str, answer: dict | None,
                 reviewer) -> dict:
    """One line of logs/approvals.jsonl (checks/FORMATS.md, section 13.4)."""
    line = {"at": now(), "run_id": run_id, "action": action, "action_class": klass, "facts": facts, "kind": kind,
            "decision": answer["decision"] if answer else "none",
            "seconds": answer.get("seconds") if answer else None,
            "reviewer": answer.get("reviewer") if answer else reviewer.kind,
            "mode": answer.get("mode") if answer else reviewer.mode}
    _append(APPROVALS, line)
    return line


# -- files ------------------------------------------------------------------------------------------------

def _arg(role: str, name: str) -> str:
    from harness.roles import arg
    return arg(role, name)


def _append(path: Path, line: dict) -> None:
    with _lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a") as fh:
            fh.write(json.dumps(line, default=str) + "\n")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        if line.strip():
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out
