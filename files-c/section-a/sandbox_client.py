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

import shlex
import subprocess
from dataclasses import dataclass
from typing import Protocol


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class SandboxClient(Protocol):
    def run(self, command: str) -> CommandResult:
        """Run a shell command in the sandbox's current session (persists
        filesystem state for the next call, like a real shell)."""
        ...

    def run_disposable(self, command: str) -> CommandResult:
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
        self.cwd = cwd

    def run(self, command: str) -> CommandResult:
        proc = subprocess.run(
            command, shell=True, cwd=self.cwd,
            capture_output=True, text=True,
        )
        return CommandResult(proc.stdout, proc.stderr, proc.returncode)

    def run_disposable(self, command: str) -> CommandResult:
        return self.run(command)

    def write_file(self, path: str, content: str) -> CommandResult:
        full_path = f"{self.cwd}/{path}"
        with open(full_path, "w") as f:
            f.write(content)
        return CommandResult("", "", 0)

    def read_file(self, path: str) -> str:
        with open(f"{self.cwd}/{path}") as f:
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

    def _contree(self, args: str, disposable: bool = False) -> CommandResult:
        flag = "-D " if disposable else ""
        full_cmd = f"contree --profile={self.profile} run {flag}{args}"
        proc = subprocess.run(
            full_cmd, shell=True, capture_output=True, text=True,
        )
        return CommandResult(proc.stdout, proc.stderr, proc.returncode)

    def run(self, command: str) -> CommandResult:
        # Quoted so the remote shell sees one argument, not contree's own flags.
        return self._contree(f"-- bash -c {shlex.quote(command)}")

    def run_disposable(self, command: str) -> CommandResult:
        return self._contree(f"-- bash -c {shlex.quote(command)}", disposable=True)

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
