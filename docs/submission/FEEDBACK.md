# Feedback on Nebius and NVIDIA tools

This is from building a test-generation agent over two weeks. Each item is something we
saw ourselves; the raw log with dates is `FEEDBACK_NOTES.md`.

## What worked well

- **Token Factory was reliable.** We made about 460 sequential calls across three
  seeded evaluation runs, a held-out run and real-repo runs, with no timeouts, 429s or
  5xx errors. Because it is OpenAI-compatible, switching our client to it took one base-URL
  change.
- **Three Nemotron 3 sizes behind one API made a cost ladder easy.** We start every gap on
  Nano and escalate to Super, then Ultra, only on failure. After we fixed our own prompt,
  Nano wrote a correct test on the first attempt for 69% of generated gaps. Super did
  most of the rescues (see the eval numbers below).

## What cost us time

1. **Nebius Sandboxes: we could not install the CLI.** `pip install contree` returns "No
   matching distribution found", and `contree-sdk` 0.3.6 installs but ships no CLI. We
   gave up and isolated tests with local `bubblewrap`. *What would have helped:* one
   install command on the Install & Authenticate page, or a Python quickstart that runs
   one command in a sandbox.
2. **The Sandboxes CLI and SDK have different defaults.** The CLI's `run` keeps
   filesystem state unless you pass `-D`; the SDK's `run()` defaults to
   `disposable=True`. Code ported from one to the other silently loses state. *Would
   help:* one sentence on the SDK reference page.
3. **Sandbox sessions are keyed by profile, parent PID and TTY.** That is ambiguous for
   a script that starts one subprocess per command. *Would help:* an explicit session
   handle for scripted use.
4. **Nemotron 3 reasons by default, and the system-prompt toggle is ignored.** Reasoning
   used up our `max_tokens` before the answer started. The setting that worked on all
   three tiers was
   `extra_body={"chat_template_kwargs": {"enable_thinking": False}}`. *Would help:*
   documenting this on the model card and in the API docs.
5. **The three model IDs use different casing, and casing matters.** The IDs are
   `nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B`, `nvidia/nemotron-3-super-120b-a12b` and
   `nvidia/Nemotron-3-Ultra-550b-a55b`. We wrote a script that picks them from `/models`.
   *Would help:* one naming scheme, or case-insensitive matching.

## What we learned about Nemotron for test generation

- **Nano often leaves out imports.** In one run, 32 failed attempts were `NameError`, and
  30 of those came from Nano. A static check for undefined names plus one repair request
  brought that to 0.
- **Super does most of the rescuing.** Across our three seeded runs, the tier that closed
  each gap was: Nano 18, 14 and 37; Super 26, 28 and 15; Ultra 2, 5 and 2.
- **Line numbers matter.** Nano's first-attempt rate went from 25-31% to 69% after we
  showed numbered source lines instead of only naming the target line range. That was our
  prompt bug, not the model's, and it may be worth a note in prompting guides for code
  tasks.
- **On new code, Nano closed 52% of gaps on its first attempt, and all three tiers
  closed 88%.** 7 of the 8 failures were the model guessing names defined outside the
  code it was shown. With the error in the prompt, the next tier guessed a different
  name: after "no attribute 'date'", Ultra tried `dt`. None of them said the definition
  was missing.
