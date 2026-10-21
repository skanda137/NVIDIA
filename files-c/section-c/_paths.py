"""Put section-a (Section 1: models, verifier, sandbox_client) and section-b
(Section 2: generator) on sys.path, so each stays the single source of truth.
Import this before any Section 1 or Section 2 module. section-b/_paths.py is
an identical copy, so whichever one is imported first has the same effect."""
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
for _section in ("section-a", "section-b"):
    _dir = os.path.normpath(os.path.join(_HERE, "..", _section))
    if _dir not in sys.path:
        sys.path.insert(0, _dir)
