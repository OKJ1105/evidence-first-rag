"""Groups A through E of Section 4.9, one function per check.

Each check returns a `CheckResult` rather than raising, because Section 4.9
wants every check's outcome recorded in the artifact -- including the ones
that failed, and including the ones after the first failure. A runner that
stopped at the first failure would produce an artifact that says less the
worse things are.

The group letters and the sources are Section 4.9's own. They are repeated in
each docstring because Section 4.9 is explicit that "a check exists because a
frozen obligation requires it, not because a runner conventionally has one",
and a check whose source is not written down drifts into being conventional.
"""

import dataclasses
import inspect

from ..registry import REGISTERED as REGISTERED_TEMPLATES
from ..runtime.render import compose, values_of
from ..status import Status
from .normalize import failure_class, first_divergence

# Section 4.9 `B2`. These six say the request did not become a fact, so none of
# them may have reached a factual SQL success.
NEGATIVE_STATUSES = frozenset(
    {
        Status.UNSUPPORTED.value,
        Status.INVALID_REQUEST.value,
        Status.NEEDS_ENTITY_DISCOVERY.value,
        Status.AMBIGUOUS.value,
        Status.COVERAGE_GAP.value,
        Status.NOT_FOUND.value,
    }
)

# `TPL_SNAPSHOT_CANDIDATES_V1` is not one: Section 4.4 registers it so that an
# `ambiguous` outcome can list candidate scopes, and it "returns no message,
# signal, or mapping facts". Rows from it are not a factual success.
FACTUAL_TEMPLATES = frozenset(
    {"TPL_MESSAGE_FACTS_V1", "TPL_SIGNAL_FACTS_V1", "TPL_SIGNAL_MAPPING_V1"}
)

# The committed SQL of the four registered templates, snapshotted when this
# module is imported. `B1` compares against this set and never resolves a
# template by name at check time: `get(name)` reads a mutable dictionary, so a
# forged entry would validate itself, and a forged template may take a
# registered name freely (Issue #28).
REGISTERED_SQL = frozenset(template.sql for template in REGISTERED_TEMPLATES)

# The parameter names `tests/test_registry_surface.py` treats as a caller
# handing over SQL, a table, or a column. Same list, because `B1`'s second
# half is the same claim that test pins.
CALLER_SUPPLIED_SQL = frozenset(
    {
        "sql", "query", "statement", "text", "where", "order_by", "ordering_clause",
        "table", "table_name", "tables", "schema_name", "relation",
        "column", "column_name", "columns", "select", "projection", "expression",
    }
)


@dataclasses.dataclass(frozen=True, kw_only=True)
class CheckResult:
    """One check, its outcome, and enough detail to act on a failure."""

    identifier: str
    group: str
    passed: bool
    detail: str
    failure_class: str | None = None

    def as_json(self) -> dict:
        return {
            "identifier": self.identifier,
            "group": self.group,
            "passed": self.passed,
            "detail": self.detail,
            "failure_class": self.failure_class,
        }


def a1(case, actual: dict, expected: dict | None) -> CheckResult:
    """`A1` The normalized result equals its registered expected result in full.

    Framework Section 5.7 requires registered inputs and normalized expected
    outputs. Section 4.9: "`A1` is one equality, not a set of independent field
    checks. On failure the runner reports the first diverging path and uses it
    only to assign a failure class."
    """
    if expected is None:
        return CheckResult(
            identifier="A1",
            group="A",
            passed=False,
            detail=f"{case.identifier} has no registered expected result",
            failure_class="contract",
        )
    path = first_divergence(actual, expected, ())
    if path is None:
        return CheckResult(
            identifier="A1", group="A", passed=True, detail="equal in full"
        )
    return CheckResult(
        identifier="A1",
        group="A",
        passed=False,
        detail=f"first divergence at {_path(path)}",
        failure_class=failure_class(path),
    )


def b1(statements, port_executions, opened_fixtures) -> CheckResult:
    """`B1` No SQL originated outside the registry, and no arbitrary-SQL path
    was reachable.

    Charter Section 9 lists this as a Milestone 1 gate condition. What makes
    the check sound is *what it refuses to trust*, so that is worth stating.

    **It does not trust a `Template`.** Issue #28 established that the
    registry's seal is bypassable with no import at all -- `type(exported)`
    yields the class, and a forged instance carrying arbitrary SQL binds and
    executes like any other. So a template's `name`, its type, and its seal
    are worthless as provenance. The only anchor is the set of SQL texts
    committed in `registry.py`, which a human reads in review, and the
    comparison below is against those texts byte for byte.

    **It does not trust the session port.** `statements` comes from the
    psycopg cursor (`recording.recording_cursor`), so a statement issued by
    code that never used the port is still seen. Observing at the port would
    make `B1` a statement about the runtime's intent; #28's lesson is that a
    "nothing else can reach this" claim is exactly the thing to verify rather
    than assume.

    **It refuses to pass vacuously.** A run in which nothing executed would
    satisfy "no statement came from outside the registry" trivially. So a
    fixture whose evidence bundle records an opened connection must be matched
    by observed statements, and a mismatch fails.

    **It excludes nothing.** psycopg opens the Section 4.3 read-only
    transaction through the connection rather than a cursor, so no
    transaction-control statement reaches this recorder and no allowlist is
    needed. An earlier draft carried one; it was removed once a real run
    showed the recorder sees 19 statements for 19 template executions and
    nothing else. If a driver change ever puts a `BEGIN` here, `B1` fails
    loudly and somebody looks, which is the right direction for that surprise.
    The runner's own instrumentation runs on separate connections and is not
    recorded here; see `probes.py`.
    """
    registered = REGISTERED_SQL
    queries = list(statements)
    foreign = sorted({s for s in queries if s not in registered})
    if foreign:
        return CheckResult(
            identifier="B1",
            group="B",
            passed=False,
            detail=f"{len(foreign)} statement(s) reached the database without"
            f" matching a registered template text: {[s[:120] for s in foreign]}",
            failure_class="runtime",
        )
    if opened_fixtures and not queries:
        return CheckResult(
            identifier="B1",
            group="B",
            passed=False,
            detail=f"{opened_fixtures} fixture(s) record an opened connection but no"
            f" statement was observed; the recorder saw nothing and this check"
            f" would otherwise pass vacuously",
            failure_class="runtime",
        )
    if len(queries) < len(port_executions):
        return CheckResult(
            identifier="B1",
            group="B",
            passed=False,
            detail=f"the port ran {len(port_executions)} template(s) but the driver"
            f" observed {len(queries)} statement(s); the recorder is not seeing"
            f" every execution",
            failure_class="runtime",
        )
    reachable = sorted(_arbitrary_sql_entry_points())
    if reachable:
        return CheckResult(
            identifier="B1",
            group="B",
            passed=False,
            detail=f"arbitrary-SQL entry point(s) reachable: {reachable}",
            failure_class="runtime",
        )
    return CheckResult(
        identifier="B1",
        group="B",
        passed=True,
        detail=f"{len(queries)} statement(s) reached the database, each byte-identical"
        f" to one of the {len(registered)} committed template texts;"
        f" no arbitrary-SQL entry point reachable",
    )


def b2(outcomes) -> CheckResult:
    """`B2` No negative outcome reached a factual SQL success.

    `outcomes` is one entry per fixture: `(identifier, status, executions)`.
    A negative status that came back with rows from a facts or mapping
    template would mean the runtime found facts and reported that it had not.
    """
    offenders = []
    for identifier, status, executions in outcomes:
        if status not in NEGATIVE_STATUSES:
            continue
        for execution in executions:
            if execution.template_name in FACTUAL_TEMPLATES and execution.row_count:
                offenders.append(f"{identifier} ({status}, {execution.template_name})")
    if offenders:
        return CheckResult(
            identifier="B2",
            group="B",
            passed=False,
            detail=f"negative outcome(s) reached a factual success: {offenders}",
            failure_class="runtime",
        )
    return CheckResult(
        identifier="B2",
        group="B",
        passed=True,
        detail="every negative outcome returned no factual row",
    )


def b3(recorded) -> CheckResult:
    """`B3` The runtime identity could not write data or change the schema.

    Section 4.10 requires all four refusals and requires them to originate
    from PostgreSQL privileges. A statement that was refused for another
    reason is recorded as a failure here rather than counted as a refusal:
    the grant is what is under test.
    """
    unrefused = sorted(n for n, r in recorded.items() if not r["refused"])
    if unrefused:
        return CheckResult(
            identifier="B3",
            group="B",
            passed=False,
            detail=f"the runtime identity was allowed to: {unrefused}",
            failure_class="runtime",
        )
    wrong_origin = sorted(n for n, r in recorded.items() if not r["from_privileges"])
    if wrong_origin:
        return CheckResult(
            identifier="B3",
            group="B",
            passed=False,
            detail=f"refused, but not by privileges (Section 4.10): {wrong_origin}",
            failure_class="runtime",
        )
    return CheckResult(
        identifier="B3",
        group="B",
        passed=True,
        detail="all four writes refused with SQLSTATE 42501",
    )


def b4(before: dict, after: dict) -> CheckResult:
    """`B4` Every Section 4.1 table was unchanged from the run's start to its end."""
    if before == after:
        return CheckResult(
            identifier="B4", group="B", passed=True, detail="state digests equal"
        )
    return CheckResult(
        identifier="B4",
        group="B",
        passed=False,
        detail=f"state digest changed during the run: {before} -> {after}",
        failure_class="runtime",
    )


def c1(failures: list[str]) -> CheckResult:
    """`C1` Every Section 4.1 constraint and every Section 4.2 rule holds.

    Charter Section 9 requires an automated data-level check of the Section
    3.6 identity and scope invariants. The check itself is
    `db/invariants.py`, which the provisioning slice wrote and which runs as
    the provisioning identity because probing enforcement needs INSERT; this
    records its result in the artifact, which is what Section 4.9 adds.
    """
    if failures:
        return CheckResult(
            identifier="C1",
            group="C",
            passed=False,
            detail=f"{len(failures)} data-level invariant failure(s): {failures}",
            failure_class="data",
        )
    return CheckResult(
        identifier="C1", group="C", passed=True, detail="all data-level invariants hold"
    )


def d1(first: dict, second: dict) -> CheckResult:
    """`D1` Two runs over the same fixtures and database produce identical artifacts.

    Both arguments are already reduced by `artifact.comparable`, which removes
    the run identifier and the wall-clock timestamp Section 4.9 names as
    irreproducible. Anything else that differs is the defect this check is for.
    """
    path = first_divergence(second, first, ())
    if path is None:
        return CheckResult(
            identifier="D1", group="D", passed=True, detail="two runs compared equal"
        )
    return CheckResult(
        identifier="D1",
        group="D",
        passed=False,
        detail=f"two runs diverged at {_path(path)}",
        failure_class="runtime",
    )


def e1(case, result) -> CheckResult:
    """`E1` Every value in the rendered answer is present in the normalized result.

    Charter Section 3.1 requires user-facing text to be a rendering of
    validated data that neither contradicts nor extends the evidence bundle.
    `values_of` is that comparison's right-hand side, defined once in
    `runtime/render.py` so this check and the runtime's own tests cannot drift
    into comparing against different sets.
    """
    answer = compose(result)
    unexplained = sorted(set(answer.values()) - values_of(result))
    if unexplained:
        return CheckResult(
            identifier="E1",
            group="E",
            passed=False,
            detail=f"{case.identifier}: rendered value(s) absent from the result:"
            f" {unexplained}",
            failure_class="presentation",
        )
    return CheckResult(
        identifier="E1",
        group="E",
        passed=True,
        detail=f"{len(answer.values())} rendered value(s), all present in the result",
    )


def _arbitrary_sql_entry_points() -> list[str]:
    """Public registry callables that accept SQL, a table, or a column."""
    from .. import registry

    found = []
    for name in sorted(registry.__all__):
        value = getattr(registry, name)
        owner = value if inspect.isclass(value) else type(value)
        targets = [(f"{name}()", value)] if inspect.isfunction(value) else []
        if owner.__module__.split(".")[0] == "evidence_first_rag":
            targets += [
                (f"{name}.{method}()", function)
                for method, function in inspect.getmembers(owner, inspect.isfunction)
                if not method.startswith("__")
            ]
        for label, target in targets:
            if set(inspect.signature(target).parameters) & CALLER_SUPPLIED_SQL:
                found.append(label)
    return found


def _path(path: tuple) -> str:
    return "".join(f"[{p}]" if isinstance(p, int) else f".{p}" for p in path).lstrip(".")
