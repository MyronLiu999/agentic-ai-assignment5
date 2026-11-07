# ARCHITECTURE.md · RepoMind on the seven layers

For each layer: what does this job, and where is it enforced. Cite code as a file
path and line number joined by a colon, inside backticks; a checker opens every
reference (`checks/FORMATS.md`, section 8). A layer held only by a sentence in a
prompt (any file under `prompts/`) is **EMPTY**, and so is a layer nothing does
yet. Status is one of: present, partial (say what is missing), or **EMPTY**. Each
assignment brings this file up to date.

What each layer is for (Lecture 1, slides 42 to 44):

- **Model**: reasoning, choosing tools, generating text.
- **Harness**: runs the loop, builds each prompt, trims old history.
- **Tools**: where the system acts on the world.
- **Memory & State**: what survives a step, a session, a restart.
- **Control & Policy**: what the system may do, and when it must ask.
- **Observability**: a step-by-step record of what it did.
- **Evaluation**: measuring quality, before and after release.

The table below is RepoMind as Assignment 5 leaves it.

| Layer | What does this job | Where it is enforced | Status |
|---|---|---|---|
| Model | The configured model, called only through the metered client | `harness/client.py:150` | present |
| Harness | The loop, with three bounds checked in code; a plan validated before it runs, and an executor that runs only the plan's steps; before every model call the inbox is drained and a stopped run is not asked anything more | `agent/loop.py:38`, `ways/planned.py:343`, `ways/planned.py:440`, `ways/planned.py:185` | present |
| Tools | Ten namespaced tools behind one registry: every call checked at the boundary before it runs; every write keyed by the harness, checked before each attempt and read back after a timeout; every attempt in the call record | `tools/__init__.py:169`, `tools/__init__.py:259`, `tools/__init__.py:268`, `tools/__init__.py:285`, `tools/__init__.py:324` | present |
| Memory & State | A checkpoint after each file read and before and after each write, sync, and a resume from the last one, also for a run that ended held or stopped; a store of dated records with their origin, read before the first search and written once at the end of a run; a user's boundary kept as a rule outside the history, which no compaction can drop | `ways/planned.py:402`, `ways/planned.py:415`, `ways/planned.py:279`, `ways/planned.py:299`, `state/checkpointer.py:55`, `state/store.py:96`, `policy/hook.py:132` | present |
| Control & Policy | The autonomy policy in three columns (policy/autonomy.yaml), enforced in the registry's hook before every call: each call placed by its action and circumstance, from facts the harness computes; prohibited classes refused whoever answers; gated classes wait for the reviewer, and no answer holds the run; a user's boundary refuses any call on a matching path; a comment without the disclosure line is refused; bin/stop refuses every further call; an escalation with a packet before a push whose own tests failed; bin/rollback offsets labels, PRs and closes through the remote's endpoints | `tools/__init__.py:145`, `policy/hook.py:100`, `policy/hook.py:230`, `policy/hook.py:235`, `policy/hook.py:241`, `policy/hook.py:244`, `policy/hook.py:252`, `policy/hook.py:231`, `ways/planned.py:506`, `ways/planned.py:539`, `bin/stop:36`, `bin/rollback:60` | present |
| Observability | One trace line per model call and per tool call, and the plan as data before it runs; a live notification when a run starts, and one when it holds, stops or escalates; every refusal in logs/hook.jsonl, every decision in logs/approvals.jsonl, every stop in logs/stops.jsonl | `agent/loop.py:50`, `ways/planned.py:225`, `ways/planned.py:210`, `ways/planned.py:524`, `policy/hook.py:273`, `policy/hook.py:302` | present |
| Evaluation | The grounded check reads the tracker, never the agent; the recorded day replayed through the hook's own placement code; the report's measured fields recomputed from the logs | `eval/check_triage.py:7`, `bin/replay_policy:36`, `eval/lab05_report.py:38` | partial: offline only |

**Empty layers: 0 of 7**, and one is partial (Evaluation: nothing measures quality in production).
