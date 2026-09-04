"""Section 4.9's conformance runner and Section 4.10's read-only invariance.

The evaluation half of contract `mvp-v0.1`: run every registered fixture
against the runtime with the read-only identity, judge each against its
registered expected result, assert the boundary and determinism properties,
and write one JSON artifact carrying the verdict and the failure classes.

Nothing here invokes a language model. Charter Section 3.3 forbids a model
from judging conformance of its own output, so every check is an equality, a
set difference, or a SQLSTATE comparison, and `tests/test_conformance_surface.py`
asserts the absence rather than trusting this sentence.

`runner.main` is the entry point; importing this package pulls in no driver.
"""

from .artifact import Artifact, FixtureOutcome, Verdict, comparable
from .cases import REGISTERED, Case
from .checks import CheckResult
from .normalize import failure_class, first_divergence, normalize

__all__ = [
    "Artifact",
    "Case",
    "CheckResult",
    "FixtureOutcome",
    "REGISTERED",
    "Verdict",
    "comparable",
    "failure_class",
    "first_divergence",
    "normalize",
]
