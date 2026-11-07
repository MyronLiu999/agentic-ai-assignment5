"""bin/review's screen: render(request) -> str (checks/FORMATS.md, section 13.4).

One screen, read in well under forty seconds, that makes the four reviewer shortcuts
harder: it leads with what the call does and why this one asks (not the tool's
name), shows the exact text that would become public, shows the conversation it
lands in, and ends with the one question being asked. Nothing on it comes from the
model's own account of itself: the facts are the harness's, the thread is the
tracker's, the text is the call's arguments.
"""

from __future__ import annotations

import textwrap

WIDTH = 70
WHY = {
    "post_comment/human_active": "a person wrote on this thread in the last hour: the comment lands in a live "
                                 "conversation, and nothing can take it back",
    "open_pr": "a pull request puts a proposed change in front of the team; it can be closed, but people see it",
    "push_commit/agent_branch": "a commit lands on RepoMind's own branch; nothing undoes a push",
}
QUESTION = {
    "post_comment/human_active": "Should this exact comment be posted, now, in this conversation?",
    "open_pr": "Should RepoMind open this draft pull request?",
    "push_commit/agent_branch": "Should this commit be pushed to RepoMind's branch?",
}


def render(request: dict) -> str:
    if request.get("kind") == "escalation":
        return escalation(request)
    facts = request.get("facts") or {}
    args = request.get("args") or {}
    klass = request.get("action_class") or request.get("action")
    issue = facts.get("issue")
    lines = [f"RepoMind wants to: {doing(request.get('action'), args, facts)}",
             f"Why it asks you:   {WHY.get(klass, 'your policy places ' + str(klass) + ' in requires_approval')}",
             ""]
    lines += context(issue, facts)
    lines += ["", "WHAT WOULD BE PUBLISHED" if request.get("action") == "post_comment" else "WHAT WOULD BE WRITTEN"]
    lines += content(request.get("action"), args)
    lines += ["", f"Class {klass}  |  run {request.get('run_id')}", "",
              QUESTION.get(klass, "Should this call run?")]
    return "\n".join(lines)


def doing(action: str, args: dict, facts: dict) -> str:
    issue = facts.get("issue")
    if action == "post_comment":
        return f"post a public comment on issue #{issue}"
    if action == "open_pr":
        return f"open a draft pull request from {facts.get('branch')} into {facts.get('base')} for issue #{issue}"
    if action == "push_commit":
        return f"push a commit to {facts.get('branch')} ({len(facts.get('paths') or [])} file(s))"
    return f"{action} on issue #{issue}"


def context(issue, facts: dict) -> list[str]:
    """The issue, and its latest discussion, from the tracker: what the comment answers."""
    if issue is None:
        return []
    out = []
    try:
        from harness.tracker import Tracker
        found = Tracker(flaky=False, readback_fail=False).issue(int(issue))
        opened = "RepoMind" if facts.get("issue_opened_by_agent") else found.get("author", "a person")
        out.append(f"Issue #{issue}: {found.get('title', '')}  (opened by {opened})")
        minutes = facts.get("minutes_since_human_comment")
        if minutes is not None:
            out.append(f"A person last wrote here {minutes:g} minutes ago.")
        for entry in (found.get("discussion") or [])[-2:]:
            who = entry.get("author") or "someone"
            text = " ".join(str(entry.get("body") or entry.get("text") or "").split())
            out.append(f"  {who}: " + textwrap.shorten(text, WIDTH, placeholder=" ..."))
        if not found.get("discussion"):
            body = " ".join(str(found.get("body") or "").split())
            out.append("  " + textwrap.shorten(body, WIDTH * 2, placeholder=" ..."))
    except Exception as exc:  # the screen still shows the call
        out.append(f"Issue #{issue} (could not be read: {type(exc).__name__})")
    return out


def content(action: str, args: dict) -> list[str]:
    def box(text: str) -> list[str]:
        lines = []
        for raw in str(text or "").splitlines() or [""]:
            lines += ["  | " + part for part in (textwrap.wrap(raw, WIDTH) or [""])]
        return lines
    if action == "post_comment":
        return box(args.get("body"))
    if action == "open_pr":
        return [f"  title: {args.get('title')}"] + box(args.get("body"))
    if action == "push_commit":
        return [f"  message: {args.get('message')}", f"  files:   {', '.join(map(str, args.get('files') or []))}"]
    return box(str(args))


def escalation(request: dict) -> str:
    packet = request.get("packet") or {}
    return "\n".join([
        "RepoMind STOPPED TO ASK before going on.",
        "",
        f"It was about to:  {packet.get('attempted')}",
        f"It stopped because: {packet.get('why_stopped')}",
        f"Signal: {packet.get('signal')}  |  run {request.get('run_id')}",
        "",
        f"Decide: {packet.get('needs_from_human')}",
        "  a = go ahead as planned | d = do not; the run hands the issue to a person",
    ])
