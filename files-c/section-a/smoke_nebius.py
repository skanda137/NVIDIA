"""
Run once with Nebius credentials, paste the whole output back. It answers the
questions the code currently only assumes. It changes nothing in the repo.

    contree auth            # out of band, once
    python smoke_nebius.py

Checks (each prints PASS / FAIL / INFO plus the raw evidence):
  1 tooling  : is the `contree` CLI on PATH; is contree_sdk importable, and what
               are the signatures of the objects we would build on instead
  2 roundtrip: write_file then read_file through NebiusSandboxClient
  3 session  : does a file created by one `run` exist in the next `run`
  4 python   : python3 / pip / git present in the default image
  5 network  : can the sandbox reach github.com and pypi.org (git clone, pip install)
  6 latency  : wall time of a trivial command, 3 runs
"""

import importlib
import inspect
import shutil
import time

from sandbox_client import NebiusSandboxClient


def report(name, status, evidence=""):
    print(f"[{status}] {name}" + (f"\n        {evidence}" if evidence else ""))


def check_tooling():
    cli = shutil.which("contree")
    report("contree CLI on PATH", "PASS" if cli else "FAIL", cli or "not found; NebiusSandboxClient cannot work as written")
    try:
        sdk = importlib.import_module("contree_sdk")
    except ImportError as exc:
        report("contree_sdk importable", "INFO", str(exc))
        return cli is not None
    names = [n for n in dir(sdk) if not n.startswith("_")]
    report("contree_sdk importable", "INFO", f"public names: {names}")
    for n in names:
        obj = getattr(sdk, n)
        if inspect.isclass(obj):
            try:
                report(f"signature {n}", "INFO", str(inspect.signature(obj)))
            except (TypeError, ValueError):
                pass
            run = getattr(obj, "run", None)
            if callable(run):
                report(f"signature {n}.run", "INFO", str(inspect.signature(run)))
    return cli is not None


def main():
    if not check_tooling():
        print("\nNo CLI: checks 2-6 skipped. Report the SDK signatures above; the client has to move to contree_sdk.")
        return
    sb = NebiusSandboxClient()

    sb.write_file("/tmp/smoke_rt.txt", "hello")
    try:
        got = sb.read_file("/tmp/smoke_rt.txt")
        report("write_file/read_file roundtrip", "PASS" if got.strip() == "hello" else "FAIL", repr(got))
    except FileNotFoundError as exc:
        report("write_file/read_file roundtrip", "FAIL", str(exc))

    sb.run("touch /tmp/smoke_session_marker")
    r = sb.run("ls /tmp/smoke_session_marker")
    report("session persists across run() calls", "PASS" if r.ok else "FAIL", (r.stdout + r.stderr).strip())

    r = sb.run("python3 --version; python3 -m pip --version; git --version; coverage --version | head -1")
    report("python3 / pip / git / coverage in image", "INFO", (r.stdout + r.stderr).strip())

    for label, cmd in [("github.com", "git ls-remote https://github.com/git/git HEAD"),
                       ("pypi.org", "python3 -m pip download -q --no-deps -d /tmp/pipdl coverage")]:
        r = sb.run(cmd, timeout=120)
        report(f"network: {label}", "PASS" if r.ok else "FAIL", (r.stdout + r.stderr).strip()[-300:])

    times = []
    for _ in range(3):
        t0 = time.time()
        sb.run("true")
        times.append(round(time.time() - t0, 2))
    report("latency of `true`, seconds (3 runs)", "INFO", str(times))


if __name__ == "__main__":
    main()
