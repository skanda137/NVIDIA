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

4. **We never ran a Nebius sandbox, and replaced it with local bubblewrap.** Because of
   item 1 we had no working `contree` CLI. `contree-sdk` 0.3.6 was installed but never
   tried. Generated tests now run in `bwrap` on WSL2: read-only root, no network, host
   secrets hidden (`files-c/section-a/sandbox_client.py`). Helped: a working one-command
   install, or a Python quickstart that runs one command in a sandbox.

## Token Factory inference (VERIFIED, 2026-10-21 to 2026-10-24, from our runs)

5. **Model IDs use inconsistent casing across the Nemotron 3 tiers**, and the exact casing
   is required: `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/nemotron-3-super-120b-a12b`,
   `nvidia/Nemotron-3-Ultra-550b-a55b`. We picked them from the model list with a script
   (`scripts/check_token_factory.py`). Helped: one consistent naming scheme, or
   case-insensitive IDs.

6. **Nemotron 3 reasons by default, and the system-prompt toggle is ignored.** The switch
   that worked on all three tiers was `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`
   (checked live 2026-10-21: 0 reasoning tokens). Before that, reasoning ate the
   `max_tokens` budget. Helped: this parameter on the model card and in the
   OpenAI-compatible API docs.

7. **No errors in about 325 sequential calls.** Runs A, B and C made 117, 114 and 90
   calls; the real repos and a replay made 4 more. We saw no timeouts, 429s or 5xx (0
   "no response" attempts in any eval CSV). Mean wall time per generated gap, including
   our sandbox runs, was 5.8 s, 7.8 s and 6.1 s. One Nano call with a 2620-token prompt
   took 3.0 s (`docs/evidence/real_repos_2026-10-24_droptests.md`). We did not log
   per-tier latency in the eval runs.

## NVIDIA Nemotron models in test generation (VERIFIED, eval runs on seeded repos)

8. **Nano often leaves out imports.** In run B, 32 attempts failed with `NameError`. 30
   were Nano and 2 Super; 17 were `pytest.raises` without `import pytest`, and the rest
   mostly a missing import of the function under test. We now catch undefined names
   statically and ask once for a repair; run C had 0 `NameError` attempts
   (`docs/evidence/eval_2026-10-24_runB.jsonl`, `_runC.jsonl`).

9. **Most rescues come from Super; Ultra adds little on these gaps.** Count of gaps whose
   first verified attempt was each tier, runs A, B and C: Nano 18, 14, 37; Super 26, 28,
   15; Ultra 2, 5, 2. Our own prompt bug depressed Nano's numbers in A and B: target line
   numbers were not shown in the context. With the fix, in run C, Nano closed 37 of 54
   generated gaps on attempt 1 (in-sample: the fix was found on these repos).

## Not used
- Tavily: cut on 2026-10-24. Run C exhausted no gaps. Runs A and B exhausted 2
  third-party gaps between them, both `weather.forecast_range` in run A. Both failed on
  a mock call-argument check the test itself wrote (`unittest/mock.py` AssertionError),
  not on a wrong library API, so docs lookups would not have fixed them.
