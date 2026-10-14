"""Put section-a (Section 1: models, verifier, sandbox_client) on sys.path, so
it stays the single source of truth. Import this before any Section 1 module."""
import os
import sys

_SECTION_A = os.path.normpath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "section-a"))
if _SECTION_A not in sys.path:
    sys.path.insert(0, _SECTION_A)
