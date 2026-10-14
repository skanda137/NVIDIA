"""
Sandbox execution layer.

Everything in coverage_diff.py and verifier.py talks to a `SandboxClient`
interface, never to subprocess or to the `contree` CLI directly. Two
implementations:

- LocalSandboxClient: runs commands with plain local subprocess. No Nebius
  account needed. Use this for all local development and for the demo below.
- NebiusSandboxClient: wraps the Nebius Token Factory `contree` CLI. Swap
  this in once you have API credentials; verifier.py and coverage_diff.py
  do not change at all.

CONFIDENCE NOTE (read before trusting NebiusSandboxClient blindly):
The commands below are built only from patterns I directly saw in the
Nebius Token Factory Sandboxes docs (Overview, Tutorial, Your First
Sandbox, Install & Authenticate pages, fetched live). Specifically grounded:
  - `contree auth -y` non-interactive auth
  - `contree run <command>` executes and prints stdout/stderr
  - `contree run -D <command>` runs disposable (no new checkpoint)
  - Sessions are auto-keyed by profile + parent PID + TTY, so sequential
    `contree run` calls from the same Python process should share one
    evolving filesystem session without you passing a session id explicitly
NOT independently confirmed (the docs I pulled didn't show full syntax):
  - the exact flag for attaching/uploading a local file mid-run (the tutorial
    index mentions a `--file` flag exists but I never saw its argument order)
  - exact `contree cp` argument order for pulling a file back out
To avoid depending on either of those two uncertain pieces, this
implementation never uploads files and never shells out to `contree cp`.
It gets code into the sandbox via `git clone`/`git checkout` and heredocs
inside the command string, and gets files out via `contree run cat <path>`
(stdout capture), both of which ARE directly confirmed in the docs
("contree run cat /etc/os-release" is the literal example given). Before
you rely on this against the real API, run `contree run --help` once and
confirm nothing above has changed — it's a beta product, weeks old.
"""

from __future__ import annotations

import os
import shlex
import signal
import subprocess
from dataclasses import dataclass
from typing import Protocol


DEFAULT_TIMEOUT = 120      # seconds; generated tests can loop forever
TIMEOUT_RETURNCODE = 124   # same code GNU `timeout` uses


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class SandboxClient(Protocol):
    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        """Run a shell command in the sandbox's current session (persists
        filesystem state for the next call, like a real shell)."""
        ...

    def run_disposable(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        """Run a shell command without advancing/mutating session state."""
        ...

    def write_file(self, path: str, content: str) -> CommandResult:
        """Write `content` to `path` inside the sandbox via a heredoc,
        sidestepping any need for a separate file-upload call."""
        ...

    def read_file(self, path: str) -> str:
        """Read a file's contents back out of the sandbox via stdout capture."""
        ...


class LocalSandboxClient:
    """Runs everything in a local temp-rooted subprocess. No network, no
    Nebius account, no 'sandbox' isolation at all -- this is purely so
    Sections 1-3 can be developed and demoed before anyone has credentials,
    and so this exact code could be shown running today. Do not use this
    for anything that touches untrusted/LLM-generated code outside a
    throwaway environment; it has none of the isolation the real thing has.
    """

    def __init__(self, cwd: str):
        # verifier.py's commands are POSIX shell (env-var prefixes, rm -f, [ -f ]).
        # Under cmd.exe they fail, and every candidate would be silently rejected.
        if os.name != "posix":
            raise RuntimeError("LocalSandboxClient needs a POSIX shell; on Windows run it inside WSL")
        self.cwd = cwd

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        # Popen + own process group so a timeout kills the whole tree: with
        # shell=True, killing only the shell leaves the child running and
        # communicate() then blocks on its open pipes.
        proc = subprocess.Popen(
            command, shell=True, cwd=self.cwd,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True,
            start_new_session=(os.name == "posix"),
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
            out, err = proc.communicate()
            return CommandResult(out or "", (err or "") + f"\n[timed out after {timeout}s]", TIMEOUT_RETURNCODE)
        return CommandResult(out, err, proc.returncode)

    def run_disposable(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        return self.run(command, timeout)

    def write_file(self, path: str, content: str) -> CommandResult:
        with open(os.path.join(self.cwd, path), "w") as f:  # join keeps an absolute `path` as is
            f.write(content)
        return CommandResult("", "", 0)

    def read_file(self, path: str) -> str:
        with open(os.path.join(self.cwd, path)) as f:
            return f.read()


class NebiusSandboxClient:
    """Wraps the `contree` CLI. See the module docstring for which parts of
    this are confirmed against the docs vs. best-guess. Requires `contree
    auth` to have already been run once (out of band, not from this class --
    don't put long-lived tokens through code you might commit)."""

    def __init__(self, image: str = "ubuntu-22.04", profile: str = "default"):
        self.image = image
        self.profile = profile
        self._booted = False

    def _contree(self, args: str, disposable: bool = False, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        flag = "-D " if disposable else ""
        full_cmd = f"contree --profile={self.profile} run {flag}{args}"
        try:
            proc = subprocess.run(
                full_cmd, shell=True, capture_output=True, text=True, timeout=timeout,
            )
        except subprocess.TimeoutExpired:
            return CommandResult("", f"[contree call timed out after {timeout}s]", TIMEOUT_RETURNCODE)
        return CommandResult(proc.stdout, proc.stderr, proc.returncode)

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        # Quoted so the remote shell sees one argument, not contree's own flags.
        return self._contree(f"-- bash -c {shlex.quote(command)}", timeout=timeout)

    def run_disposable(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        return self._contree(f"-- bash -c {shlex.quote(command)}", disposable=True, timeout=timeout)

    def write_file(self, path: str, content: str) -> CommandResult:
        # Heredoc trick: no upload API needed, just a shell command.
        marker = "SBX_EOF_7f3a"
        heredoc_cmd = f"mkdir -p $(dirname {shlex.quote(path)}) && cat > {shlex.quote(path)} << '{marker}'\n{content}\n{marker}"
        return self.run(heredoc_cmd)

    def read_file(self, path: str) -> str:
        result = self.run(f"cat {shlex.quote(path)}")
        if not result.ok:
            raise FileNotFoundError(f"{path} in sandbox: {result.stderr}")
        return result.stdout
