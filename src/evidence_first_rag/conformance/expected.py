"""The registered expected result for each fixture, and where it comes from.

Framework Section 5.7 requires registered inputs and **normalized expected
outputs**; `cases.py` holds the inputs and `expected/` holds the outputs, one
committed JSON file per identifier. Section 4.9's `A1` compares them field by
field.

**How these files were authored, because it decides what `A1` proves.** They
are written from `fixtures/` -- the registered inputs -- and from the contract
Sections that fix each field, not copied out of a run. An expectation
generated from the runtime would make `A1` the statement that the runtime
equals itself, which is true of any runtime. `tests/test_conformance_expected.py`
holds that line where it can be held mechanically: every `SAMPLE_*` identifier
in an expectation must appear in `fixtures/`, so an expectation cannot name
data the registered inputs do not contain.

What that check cannot cover is the prose in a `limitations` detail, which is
transcribed from the runtime's own wording. That is the intended coupling: the
detail is a pure function of the scopes involved, and a registered expectation
is meant to fail when the text a user reads changes.
"""

import functools
import json
import pathlib

DIRECTORY = pathlib.Path(__file__).resolve().parent / "expected"


@functools.cache
def registered(identifier: str) -> dict | None:
    """The expected result for `identifier`, or None when none is registered.

    None rather than a raise: Section 4.9 makes a missing expectation an `A1`
    failure recorded in the artifact, not a crash that stops the run and
    leaves every later fixture unjudged.
    """
    path = DIRECTORY / f"{identifier}.json"
    if not path.is_file():
        return None
    return json.loads(path.read_text())


def identifiers() -> tuple[str, ...]:
    return tuple(sorted(path.stem for path in DIRECTORY.glob("FX-*.json")))
