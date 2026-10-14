# Feedback log (Nebius Token Factory / AI Cloud / NVIDIA)

Running log for the required "feedback" submission field. Add an entry the moment
something costs you time. Each entry: what we tried, what happened, what we expected,
what would have helped. Only record things we actually saw.

## Nebius Token Factory Sandboxes (from the Oct 14 audit, VERIFIED on a Windows + WSL machine)

1. **The `contree` CLI has no obvious install path.** `pip install contree` returns
   "No matching distribution found"; `contree` is not on PATH on Windows or WSL.
   `pip install contree-sdk` (0.3.6) works but ships no CLI binary.
   Expected: the Sandboxes tutorial's `contree auth` / `contree run` commands should be
   installable with one documented command.
   Helped: an install section on the Install & Authenticate page naming the package.

2. **CLI and SDK defaults differ.** The docs describe `contree run` as advancing a
   checkpoint unless `-D` is passed; the SDK's `run()` defaults to `disposable=True`.
   Code ported between the two silently loses filesystem state.
   Helped: one sentence on the SDK reference page stating the default and how it differs.

3. **Session persistence is keyed by profile + parent PID + TTY** (per the docs). That is
   clear in an interactive terminal and ambiguous for a script that spawns one subprocess
   per command. Helped: a documented explicit session handle for scripted use.

## To fill (do not write these until observed)
- Token Factory: which Nemotron model IDs are served; latency per tier; rate limits.
- Sandboxes: outbound network (git clone / pip install), cold-start and per-call latency
  (run `python smoke_nebius.py`), image choice, timeouts.
- NVIDIA models: tool-calling / <think> output quirks seen in test generation.
- Tavily (if used): result quality for library docs queries, credit cost per run.
