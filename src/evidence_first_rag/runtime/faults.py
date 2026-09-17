"""Operational faults: the things that are not outcomes.

Section 5 fixes seven status families and Section 4.4 is explicit that two
conditions are outside them. A statement timeout "is an operational fault, not
an outcome: it fails the request rather than producing a status family". A
facts template returning two rows means "the loaded database violates its own
invariants, and the runtime reports a failure (conformance class `data`)
instead of silently returning one of several".

Both are raised, never returned. A `Result` cannot represent them: every
status in Section 5 is a claim about the request, and neither of these is. The
`conformance_class` on each is the tag Section 4.9 requires the runner to
attach, kept on the exception so that the runner reads it off the failure
rather than re-deriving it from a message.
"""


class Fault(Exception):
    """A request failed for a reason Section 5 has no status for.

    Section 4.9 names five failure classes: `data`, `retrieval`, `contract`,
    `runtime`, and `presentation`. The default here is `runtime`, which is the
    class Section 4.4 assigns to a statement timeout.
    """

    conformance_class = "runtime"


class DataFault(Fault):
    """The loaded database contradicts an invariant the contract guarantees.

    Section 4.9 classes a scope or row divergence `data`. Raised rather than
    reported as a status because no Section 5 family fits: the request was
    well formed and the scope resolved, and the fault is in what was loaded.
    """

    conformance_class = "data"


class ConnectionUnavailable(Exception):
    """No session could be opened, so no request was attempted.

    Deliberately **not** a `Fault`. A `Fault` is a request that ran and failed
    for a reason Section 5 has no status for, which `api-v0.1` Section 4.5
    answers with `runtime_fault` at HTTP 500. Being unable to reach the
    database at all is that contract's `database_unavailable` at HTTP 503, and
    the two are different rows of the same table -- so they have to be
    distinguishable by type, not by reading a message.

    Raised by the session provider rather than derived by a caller, because
    which driver exception means "could not connect" is knowledge that belongs
    to the module holding the driver. `api/` catches this and imports no
    driver, which is what keeps the surface's test suite runnable from a clean
    checkout.

    It carries no `conformance_class`: the request never ran, so there is
    nothing for Section 4.9 to class.
    """
