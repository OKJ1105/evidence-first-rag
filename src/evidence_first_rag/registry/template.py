"""The registered template type and the safeguards that run at registration.

Section 4.4 lists the registry's safeguards and says they are "enforced at
registry construction time where possible and at execution time otherwise".
Everything here is the first kind: a template that would violate one cannot be
constructed, so an unsafe template has no representation to reach execution
with.

Charter Section 3.1 and AGENTS.md fix the boundary this module holds:
authoritative facts come only from registered fixed SQL templates, no
free-form SQL is generated or executed from user text or model output, and no
public arbitrary-SQL, arbitrary-table, or arbitrary-column interface exists.
The last of those is a property of what the package exposes, not of this
class alone: `Template`'s constructor accepts SQL text, so `Template` is
deliberately left out of `registry/__init__.py`'s exports. Only `registry.py`,
inside this package, builds one -- the four instances Section 4.4 registers.
Being left out of the exports is not, by itself, enough: this module is still
importable directly as `evidence_first_rag.registry.template`, so
`tests/test_registry_surface.py` also scans the source tree and fails if
anything outside this package imports `Template` or the `_SEAL` sentinel from
here, in addition to enumerating the package's public surface so that
exporting `Template` from `__init__.py` has to fail a test rather than pass
review. The one deliberate exception is `tests/test_registry.py`, which
imports this module directly to exercise the registration safeguards
themselves and says why at the import.

Sections cited are from docs/contracts/mvp-v0.1.md at version 0.5.0.
"""

import dataclasses
import enum
import re
import types
from collections.abc import Mapping

from ..evidence import LimitationKind

# Section 4.4: "Registration is refused for SQL containing INSERT, UPDATE,
# DELETE, MERGE, CREATE, DROP, ALTER, TRUNCATE, GRANT, REVOKE, COPY, CALL, or
# DO." Transcribed from the contract, in its order.
FORBIDDEN_KEYWORDS = (
    "INSERT",
    "UPDATE",
    "DELETE",
    "MERGE",
    "CREATE",
    "DROP",
    "ALTER",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "CALL",
    "DO",
)

# Matched on word boundaries rather than as substrings. A substring scan would
# refuse a template for containing "update" inside a column name, and the
# repair for that is usually to weaken the scan; a word-boundary scan is strict
# about the thing that matters and has no false positive to be weakened by.
_FORBIDDEN = re.compile(
    r"\b(?:" + "|".join(FORBIDDEN_KEYWORDS) + r")\b", re.IGNORECASE
)

# Section 4.4: "Every variable is bound as a named parameter. String
# interpolation into SQL is prohibited." psycopg's named form is `%(name)s`.
_PLACEHOLDER = re.compile(r"%\((?P<name>[a-z_][a-z0-9_]*)\)s")

# psycopg's positional placeholder forms. Only these two: `%s` and `%b`.
# Matched after the literal `%%` escapes and the named placeholders have been
# removed, so what is left is unambiguous.
_POSITIONAL = re.compile(r"%[sb]", re.IGNORECASE)

# A literal percent, written as `%%`. psycopg consumes the doubling, so SQL
# that wants one percent sign writes two.
_ESCAPED_PERCENT = re.compile(r"%%")


# Construction is sealed with this. `Template` is absent from the package's
# `__all__` and no module outside the registry imports it, but neither of
# those stops `type(TPL_MESSAGE_FACTS_V1)` -- an exported instance hands out
# its own class, and Python cannot make that unreachable. Requiring a value
# only this module can supply turns "we did not export the constructor" into
# "the constructor refuses you", which is the difference between a convention
# and the boundary Charter Section 3.1 states.
#
# This seal stops only the no-import path: a caller who never names this
# module at all, and reaches `Template` by calling `type()` on an exported
# instance. It does nothing against the other half -- a caller who imports
# this sentinel directly, `from evidence_first_rag.registry.template import
# _SEAL` -- because whoever holds the value satisfies the check it guards.
# That half is `tests/test_registry_surface.py`'s job: it scans the source
# tree and fails if anything outside this package imports `Template` or
# `_SEAL` from here. Neither guard is a runtime-proof barrier -- this is
# Python, and a committer editing this file directly can always change what
# it does -- but the seal plus the scan together are a boundary CI enforces,
# not a convention a caller happens to follow. Do not read `_SEAL` alone as
# more than half of that.
_SEAL = object()


class LimitMeaning(enum.Enum):
    """Section 4.4's "Meaning of hitting it" column, which is not the same for
    every template.

    The candidate and mapping limits cap a result that may legitimately be
    longer, and hitting one is reported in `limitations`. The facts limit of 2
    is a detector: Section 4.1's uniqueness constraints guarantee at most one
    row, so a second means the loaded database violates its own invariants.
    Section 4.4 is explicit that the runtime then "reports a failure
    (conformance class `data`) instead of silently returning one of several",
    which is a fault rather than a limitation on a result.
    """

    TRUNCATES = "truncates"
    DETECTS_OVERFLOW = "detects_overflow"


class TemplateError(Exception):
    """A template could not be registered. Raised at construction."""


class UnregisteredTemplate(Exception):
    """Section 4.4: "Execution is refused for any template name not in the
    registry." """


class ParameterError(Exception):
    """Section 4.4: a parameter outside the allowlist, or a required parameter
    that is missing."""


@dataclasses.dataclass(frozen=True, kw_only=True)
class Template:
    """One registered fixed SQL template.

    Section 4.4 fixes what a template records: "template name, version, the
    full SQL text, its allowed parameter names, its result column list in
    order, its ordering clause, and its declared limitations." The row limit
    is here too, because Section 4.4's limits table assigns one per template.
    """

    # An InitVar, so it is not a field: it stays out of repr, eq and the
    # frozen instance, and only gates construction.
    seal: dataclasses.InitVar[object] = None

    name: str
    version: str
    sql: str
    required_parameters: tuple[str, ...] = ()
    optional_parameters: tuple[str, ...] = ()
    result_columns: tuple[str, ...]
    ordering: tuple[str, ...]
    row_limit: int
    limit_meaning: LimitMeaning
    declared_limitations: tuple[LimitationKind, ...] = ()

    def __post_init__(self, seal: object) -> None:
        if seal is not _SEAL:
            raise TemplateError(
                "a Template is registered in registry.py, not constructed by a"
                " caller; Section 4.4 puts the SQL text beyond a caller's reach"
            )
        _text("name", self.name)
        _text("version", self.version)
        _text("sql", self.sql)
        if self.row_limit < 1:
            raise TemplateError(f"{self.name}: row_limit must be at least 1")
        if not self.result_columns:
            raise TemplateError(f"{self.name}: a template declares its result columns")
        if not self.ordering:
            raise TemplateError(
                f"{self.name}: Section 4.4 puts the ordering in the template,"
                f" so a template without one has no ordering the caller may supply"
            )
        for kind in self.declared_limitations:
            if not isinstance(kind, LimitationKind):
                raise TemplateError(
                    f"{self.name}: declared_limitations holds LimitationKind values"
                )

        if not isinstance(self.limit_meaning, LimitMeaning):
            raise TemplateError(f"{self.name}: limit_meaning must be a LimitMeaning")
        # The two meanings imply different limitations. A truncating limit is
        # reported on the result; an overflow detector is a fault, and
        # declaring it as a limitation would present a broken database as a
        # qualified answer.
        truncation_declared = LimitationKind.TRUNCATED_BY_LIMIT in self.declared_limitations
        if self.limit_meaning is LimitMeaning.TRUNCATES and not truncation_declared:
            raise TemplateError(
                f"{self.name}: a truncating limit declares TRUNCATED_BY_LIMIT"
            )
        if self.limit_meaning is LimitMeaning.DETECTS_OVERFLOW and truncation_declared:
            raise TemplateError(
                f"{self.name}: an overflow detector is a fault, not a truncation"
                f" (Section 4.4)"
            )

        overlap = set(self.required_parameters) & set(self.optional_parameters)
        if overlap:
            raise TemplateError(
                f"{self.name}: {sorted(overlap)} is both required and optional"
            )

        self._check_sql()

    # Section 4.4's registration safeguards. Each one is a separate method so
    # that a failure names the rule it broke rather than "invalid template".

    def _check_sql(self) -> None:
        stripped = self.sql.lstrip()
        # Section 4.4: "Every registered SQL text must begin with SELECT."
        if not stripped.upper().startswith("SELECT"):
            raise TemplateError(
                f"{self.name}: SQL must begin with SELECT (Section 4.4)"
            )

        found = sorted({match.group(0).upper() for match in _FORBIDDEN.finditer(self.sql)})
        if found:
            raise TemplateError(
                f"{self.name}: SQL contains the prohibited keyword(s) {found}"
                f" (Section 4.4)"
            )

        # Section 4.4: string interpolation into SQL is prohibited, so every
        # variable has to appear as a named placeholder. A template carrying a
        # positional one binds by position, and the parameter allowlist below
        # would then be checking names the SQL does not use.
        #
        # Stripped in this order -- literal `%%` escapes, then named
        # placeholders -- so that what remains is unambiguously a placeholder.
        # Review finding N3: the earlier pattern matched any `%` followed by a
        # letter, so `LIKE '%%foo'` was refused as positional binding even
        # though it is a correctly escaped literal percent. That is the same
        # false-positive trap the keyword scan avoids by matching on word
        # boundaries, and the usual repair for it is to weaken the check.
        remainder = _PLACEHOLDER.sub("", _ESCAPED_PERCENT.sub("", self.sql))
        if _POSITIONAL.search(remainder):
            raise TemplateError(
                f"{self.name}: SQL uses a positional placeholder; Section 4.4"
                f" binds every variable as a named parameter"
            )
        if "%" in remainder:
            # Not a placeholder, but psycopg would try to read it as one and
            # fail at execution. Refusing it here says what is wrong; letting
            # it register would move the failure to a runtime nobody is
            # watching.
            raise TemplateError(
                f"{self.name}: SQL contains an unescaped '%'; a literal percent"
                f" is written '%%' so that psycopg does not read it as a"
                f" placeholder"
            )

        # Every placeholder in the SQL must be declared, and every declared
        # parameter must appear. The first direction stops a template from
        # binding something the allowlist does not govern; the second stops the
        # allowlist from advertising a parameter that changes nothing.
        placeholders = {match.group("name") for match in _PLACEHOLDER.finditer(self.sql)}
        declared = set(self.allowed_parameters)
        undeclared = sorted(placeholders - declared)
        if undeclared:
            raise TemplateError(
                f"{self.name}: SQL binds {undeclared}, which the template does not allow"
            )
        unused = sorted(declared - placeholders)
        if unused:
            raise TemplateError(
                f"{self.name}: {unused} is allowed but never bound in the SQL"
            )

        # Section 6: "Null ordering is `NULLS LAST`, written explicitly in
        # every registered template's ordering clause rather than left to the
        # database default."
        if "ORDER BY" not in self.sql.upper():
            raise TemplateError(f"{self.name}: SQL carries no ORDER BY (Section 4.4)")
        order_clause = self.sql.upper().split("ORDER BY", 1)[1]
        expressions = order_clause.split("LIMIT", 1)[0].split(",")
        for expression in expressions:
            if "NULLS LAST" not in expression:
                raise TemplateError(
                    f"{self.name}: ordering term '{expression.strip()}' has no"
                    f" explicit NULLS LAST (Section 6)"
                )

        # Review finding N2, and the same class of defect as the row limit
        # above: metadata that can silently disagree with the SQL it describes.
        # `ordering` is what the runtime and the conformance runner reason
        # about, so a template whose declared ordering does not match its
        # ORDER BY would have them reasoning about a query that does not
        # exist. Checked positionally, because Section 6 makes the order of
        # the terms the thing that matters.
        declared = list(self.ordering)
        if len(expressions) != len(declared):
            raise TemplateError(
                f"{self.name}: declares {len(declared)} ordering term(s) but the"
                f" SQL has {len(expressions)}"
            )
        for position, (column, expression) in enumerate(zip(declared, expressions)):
            ordered_column = _ordered_column(expression)
            if ordered_column != column.upper():
                # `ordering` takes a bare column name; a declared value that
                # carries ASC/DESC or NULLS ordering decoration renders
                # identically to the SQL side once both are printed raw, so
                # this compares and prints the normalized values that were
                # actually checked against each other, not the raw inputs.
                raise TemplateError(
                    f"{self.name}: ordering term {position} is declared as"
                    f" {column.upper()!r}, but the SQL orders by column"
                    f" {ordered_column!r} (from '{expression.strip()}');"
                    f" `ordering` takes the bare column name, without"
                    f" ASC/DESC or NULLS ordering decoration"
                )

        # The same for the result columns. Section 4.4 records "its result
        # column list in order", and a declared column the SELECT does not
        # produce would be a column name nothing returns.
        select_clause = self.sql.upper().split("FROM", 1)[0]
        for column in self.result_columns:
            if not re.search(rf"\b{re.escape(column.upper())}\b", select_clause):
                raise TemplateError(
                    f"{self.name}: result column {column!r} does not appear in"
                    f" the SELECT list"
                )

        # Section 4.4's limits table assigns a row limit per template, and the
        # limit belongs in the registered text so that a caller cannot raise
        # it. Matched as the trailing `LIMIT <n>` clause, not as a substring:
        # "LIMIT 2" is a substring of "LIMIT 200", so a substring scan would
        # let a declared row_limit disagree with the SQL's actual limit.
        limit_match = re.search(r"LIMIT\s+(\d+)\s*$", self.sql.strip(), re.IGNORECASE)
        if limit_match is None or int(limit_match.group(1)) != self.row_limit:
            raise TemplateError(
                f"{self.name}: SQL does not carry its declared LIMIT"
                f" {self.row_limit} (Section 4.4)"
            )

    @property
    def allowed_parameters(self) -> tuple[str, ...]:
        """Section 4.4's allowlist: required first, then optional."""
        return self.required_parameters + self.optional_parameters

    def rows_are_overflow(self, row_count: int) -> bool:
        """Whether `row_count` rows from this template mean a broken database.

        Only true for a template whose limit detects overflow. Section 4.4:
        the facts limit "is deliberately 2, not 1: a second row means the
        loaded database violates its own invariants". The runtime turns a True
        here into a conformance class `data` failure; deciding that is the
        runtime's, but recognising it belongs to the template that set the
        limit.
        """
        if not isinstance(row_count, int) or isinstance(row_count, bool):
            raise ValueError("row_count must be an int")
        if row_count < 0:
            raise ValueError("row_count must not be negative")
        return self.limit_meaning is LimitMeaning.DETECTS_OVERFLOW and row_count > 1

    def truncated(self, row_count: int) -> bool:
        """Whether `row_count` rows mean the result was cut off by the limit."""
        if not isinstance(row_count, int) or isinstance(row_count, bool):
            raise ValueError("row_count must be an int")
        if row_count < 0:
            raise ValueError("row_count must not be negative")
        return self.limit_meaning is LimitMeaning.TRUNCATES and row_count >= self.row_limit

    def bind(self, arguments: Mapping[str, object]) -> Mapping[str, object]:
        """Return the parameters to bind, or raise ParameterError.

        Section 4.4: "A parameter not in the template's allowlist is refused. A
        required parameter that is missing is refused." Optional parameters the
        caller omitted are bound as None, because the registered SQL tests them
        for null rather than being rewritten around them — Section 4.4 puts the
        SQL text beyond the caller's reach, so an absent optional argument
        changes what the query matches, never what the query is.
        """
        if not isinstance(arguments, Mapping):
            raise ParameterError(f"{self.name}: arguments must be a mapping")

        unknown = sorted(set(arguments) - set(self.allowed_parameters))
        if unknown:
            raise ParameterError(
                f"{self.name}: parameter(s) {unknown} are not in the allowlist"
                f" {list(self.allowed_parameters)} (Section 4.4)"
            )
        missing = sorted(set(self.required_parameters) - set(arguments))
        if missing:
            raise ParameterError(
                f"{self.name}: required parameter(s) {missing} are missing (Section 4.4)"
            )
        for name in self.required_parameters:
            if arguments[name] is None:
                raise ParameterError(
                    f"{self.name}: required parameter {name!r} is null; Section 4.2"
                    f" forbids the runtime from supplying a missing scope dimension"
                )

        bound = {name: arguments.get(name) for name in self.allowed_parameters}
        return types.MappingProxyType(bound)


# The decoration an ordering term may carry after its column, per Section 6.
_ORDER_DECORATION = re.compile(
    r"\s+(?:ASC|DESC)?\s*(?:NULLS\s+(?:FIRST|LAST))?\s*$", re.IGNORECASE
)


def _ordered_column(expression: str) -> str:
    """The bare column an ORDER BY term sorts on, upper-cased.

    Compared by equality rather than containment, and this is not fussiness:
    a substring test passes for a column named `a` because "NULLS LAST"
    contains an A. That is the same defect the row-limit check had before
    review finding B2, found here by probing this check with a one-letter
    column name rather than trusting it.
    """
    bare = _ORDER_DECORATION.sub("", expression.strip())
    return bare.rsplit(".", 1)[-1].strip().upper()


def _text(field: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise TemplateError(f"{field} must be a non-empty string")
