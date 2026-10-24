"""
Sandbox execution layer.

Everything in coverage_diff.py and verifier.py talks to a `SandboxClient`
interface, never to subprocess directly. One implementation:

- LocalSandboxClient: runs every command inside bubblewrap (`bwrap`) on the
  local Linux/WSL2 machine. The LLM-generated tests and the PR's own code run
  here, so they get a read-only root, a private /tmp, no network by default,
  and no view of the host's home directory or Windows drives (where .env lives).

Mount layout of one run() call, in bwrap order (later mounts win):
  --ro-bind / /              whole host, read-only
  --tmpfs /mnt/<drive>       Windows drives (repo root, .env) hidden
  --tmpfs $HOME              ~/.config, ~/.ssh, ~/.git-credentials ... hidden
  --ro-bind <python roots>   the running interpreter's venv/base, if under $HOME
  --tmpfs /tmp               private, discarded after the call
  --ro-bind <ro_paths>       e.g. a local repo to `git clone` from
  --bind <cwd>               the workdir: read-write, persists across calls
Only the workdir persists, so repo_path and every write_file/read_file path
must live under it.
"""

from __future__ import annotations

import glob
import os
import shutil
import signal
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable, Protocol


DEFAULT_TIMEOUT = 120      # seconds; generated tests can loop forever
TIMEOUT_RETURNCODE = 124   # same code GNU `timeout` uses
DEPS_DIR = ".sandbox-site"  # under cwd: pip installs here (PIP_TARGET), the venv stays read-only


def scrubbed_env() -> dict[str, str]:
    """os.environ minus anything secret-looking, for every child process: generated
    tests run here and must not be able to read API keys."""
    return {k: v for k, v in os.environ.items()
            if not any(s in k.upper() for s in ("KEY", "TOKEN", "SECRET"))
            and not k.upper().startswith(("NEBIUS", "TOKEN_FACTORY"))}


@dataclass
class CommandResult:
    stdout: str
    stderr: str
    returncode: int

    @property
    def ok(self) -> bool:
        return self.returncode == 0


class SandboxClient(Protocol):
    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT, network: bool = False) -> CommandResult:
        """Run a shell command in the sandbox (filesystem state under the
        workdir persists for the next call, like a real shell). Offline unless
        `network=True`, which only checkout and dependency install pass."""
        ...

    def run_disposable(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        """Run a shell command without advancing/mutating session state."""
        ...

    def write_file(self, path: str, content: str) -> CommandResult:
        """Write `content` to `path` inside the sandbox."""
        ...

    def read_file(self, path: str) -> str:
        """Read a file's contents back out of the sandbox."""
        ...


def _under(path: str, root: str) -> bool:
    return os.path.commonpath([path, root]) == root


def _hidden_root(path: str) -> str | None:
    """The sandbox mount that hides `path` (a fresh /tmp, or an emptied Windows drive), or None."""
    path = os.path.abspath(path)
    for root in ["/tmp", *sorted(glob.glob("/mnt/?"))]:
        if _under(path, root):
            return root
    return None


class LocalSandboxClient:
    """bwrap-isolated subprocess rooted at `cwd` (see the module docstring for
    the mount layout). `ro_paths` are extra host paths made visible read-only,
    e.g. a local repo checkout_repo() clones from. Linux/WSL2 only, needs
    `bwrap` on PATH."""

    def __init__(self, cwd: str, ro_paths: Iterable[str] = ()):
        # verifier.py's commands are POSIX shell (env-var prefixes, rm -f, [ -f ]).
        if os.name != "posix":
            raise RuntimeError("LocalSandboxClient needs Linux; on Windows run it inside WSL")
        if shutil.which("bwrap") is None:
            raise RuntimeError("LocalSandboxClient needs bubblewrap: `sudo apt install bubblewrap`")
        # verifier.py runs sys.executable inside the sandbox. Under /tmp or /mnt/<drive> it
        # is masked there, and every command would fail with "python: not found".
        exe_dir = os.path.dirname(os.path.abspath(sys.executable))
        hidden = _hidden_root(exe_dir)
        if hidden:
            raise RuntimeError(
                f"the Python running this pipeline ({sys.executable}) is under {hidden}, which the "
                f"sandbox hides, so every test run would fail with 'python: not found'. "
                f"Create the venv under $HOME instead: python3 -m venv ~/.venvs/vtga")
        self.cwd = os.path.realpath(cwd)
        if self.cwd == "/tmp":
            raise ValueError("cwd must be a directory under /tmp, not /tmp itself")
        self.ro_paths = [os.path.realpath(p) for p in ro_paths]

    def _bwrap_argv(self, command: str, network: bool) -> list[str]:
        home = os.path.realpath(os.path.expanduser("~"))
        argv = ["bwrap", "--ro-bind", "/", "/", "--dev", "/dev", "--proc", "/proc"]
        for drive in sorted(glob.glob("/mnt/?")):  # WSL drvfs mounts; /mnt/wsl (resolv.conf) stays
            argv += ["--tmpfs", drive]
        argv += ["--tmpfs", home]
        for root in {os.path.realpath(sys.prefix), os.path.realpath(sys.base_prefix)}:
            if _under(root, home):
                argv += ["--ro-bind", root, root]
        argv += ["--tmpfs", "/tmp"]
        for p in self.ro_paths:
            argv += ["--ro-bind", p, p]
        argv += ["--bind", self.cwd, self.cwd]
        if not network:
            argv.append("--unshare-net")
        argv += ["--unshare-pid", "--unshare-ipc", "--die-with-parent", "--chdir", self.cwd,
                 "--", "/bin/sh", "-c", command]
        return argv

    def _env(self) -> dict[str, str]:
        env = scrubbed_env()
        deps = os.path.join(self.cwd, DEPS_DIR)
        env["PIP_TARGET"] = deps
        env["PYTHONPATH"] = deps + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
        return env

    def run(self, command: str, timeout: int = DEFAULT_TIMEOUT, network: bool = False) -> CommandResult:
        # Own process group so a timeout kills bwrap and, via --die-with-parent
        # and the pid namespace, everything inside it.
        proc = subprocess.Popen(
            self._bwrap_argv(command, network), env=self._env(),
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, start_new_session=True,
        )
        try:
            out, err = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            os.killpg(proc.pid, signal.SIGKILL)
            out, err = proc.communicate()
            return CommandResult(out or "", (err or "") + f"\n[timed out after {timeout}s]", TIMEOUT_RETURNCODE)
        return CommandResult(out, err, proc.returncode)

    def run_disposable(self, command: str, timeout: int = DEFAULT_TIMEOUT) -> CommandResult:
        return self.run(command, timeout)

    def _host_path(self, path: str) -> str:
        full = os.path.realpath(os.path.join(self.cwd, path))  # join keeps an absolute `path` as is
        if not _under(full, self.cwd):
            raise ValueError(f"{path} is outside the sandbox workdir {self.cwd}")
        return full

    def write_file(self, path: str, content: str) -> CommandResult:
        with open(self._host_path(path), "w") as f:
            f.write(content)
        return CommandResult("", "", 0)

    def read_file(self, path: str) -> str:
        with open(self._host_path(path)) as f:
            return f.read()
