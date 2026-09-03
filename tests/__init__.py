"""Test package for the evidence_first_rag type surface.

Importing this package puts `src/` on the path so that the suite runs from a
clean checkout with no install step and no network — the same reason
scripts/checks/test_validate_fixtures.py imports its subject by path. The
agent loop's checks manifest spawns commands without a shell, so a
`PYTHONPATH=src` prefix is not available to it; doing the same thing here
keeps CI and the loop running the identical command.
"""

import pathlib
import sys

_SOURCE = str(pathlib.Path(__file__).resolve().parent.parent / "src")
if _SOURCE not in sys.path:
    sys.path.insert(0, _SOURCE)
