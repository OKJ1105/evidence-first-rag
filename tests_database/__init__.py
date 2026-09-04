"""Tests that need a live PostgreSQL server.

Kept out of `tests/` deliberately. The agent loop runs the manifest in
`.github/agent-checks.json` with no database, so a suite that required one
would fail there for a reason that has nothing to do with the branch. These
run in CI against the service container, which is where Issue #12 puts the
acceptance evidence: "It passes locally" is not acceptance evidence for a
determinism claim.

Importing this package puts `src/` on the path, for the same reason
`tests/__init__.py` does.
"""

import pathlib
import sys

_SOURCE = str(pathlib.Path(__file__).resolve().parent.parent / "src")
if _SOURCE not in sys.path:
    sys.path.insert(0, _SOURCE)
