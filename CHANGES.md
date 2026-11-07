# CHANGES.md

Three lines per assignment: what it added, what it removed, what it constrained.
Removals are logged like additions.

## Assignment 1
- **Added:** a bounded tool loop; four ways to triage an issue (a direct call, a workflow, an agent, and a hybrid of the two); a grounded success check that reads the tracker; a results script
- **Removed:** nothing
- **Constrained:** every agent run to three bounds checked in code (steps, tokens, wall clock); success to what the tracker holds for the run's ID

## Assignment 2
- **Added:** a plan written as data before the issue is read; a validator with four checks; an executor that runs only the plan's steps; one checkpoint that may revise the plan; a second pass before the comment; detectors and a diff over traces; a progress file and a compaction
- **Removed:** the model's choice of the next tool, in the planned way
- **Constrained:** every tool call to a step of a validated plan; revisions to steps not yet done; the comment to drafts that pass the second pass

## Assignment 3
- **Added:** five rewritten tool definitions with examples, among them open_pr; a boundary check before every call; errors that name the fix; harness-derived idempotency keys, a check before every write attempt and a read-back after a timeout; the call record; a fail-closed hook
- **Removed:** free-text tool descriptions and free-form filters; protocol detail in anything the model sees
- **Constrained:** every write to be safe to retry, and to a person when its outcome cannot be read back; the comment to the last write, after the PR

## Assignment 4
- **Added:** a checkpoint after each file read and before each write, saved sync; a resume from the last checkpoint that replays a write with its saved arguments and key; a memory store of dated records with their source and origin, read before the first search; a write policy with one record per issue, superseded when it disagrees
- **Removed:** the conversation from every checkpoint; the issue's own text from what memory shows a prompt
- **Constrained:** a crashed run to resume, never restart; what is remembered to what a person stated or RepoMind derived, each with its source

## Assignment 5
- **Added:** an autonomy policy in three columns (policy/autonomy.yaml), enforced by a hook before every call that places each call by its action and circumstance from the harness's facts; a reviewer gate with a decisions log and a screen (policy/screen.py); a hold when nobody answers; the inbox drained before every model call, with a boundary parsed into a rule (policy/rules.jsonl); an escalation with a packet before a push whose own tests failed; a live notification; bin/stop, bin/rollback and bin/replay_policy; the disclosure line on every comment
- **Removed:** the hook that allowed every call; unasked comments into live human conversations, pull requests and pushes now wait for a person
- **Constrained:** merges and pushes to main or any shared branch to never, whoever answers; a gated call to a person's yes, never a timeout's; a run to stop at its next call when a person says so, and to touch no path a user ruled out, after any compaction; every comment to say an agent wrote it

