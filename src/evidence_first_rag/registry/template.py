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
The last of those is a property of what this module does *not* expose, which
is why `tests/test_registry_surface.py` enumerates the public surface: adding
such an entry point later has to fail a test rather than pass review.

Sections cited are from docs/contracts/mvp-v0.1.md at version 0.3.0.
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

# The positional and format placeholder styles, which would make the binding
# order-dependent and take the parameter names out of the SQL.
_POSITIONAL = re.compile(r"%s|%\d*\$?[a-z]", re.IGNORECASE)


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

    def __post_init__(self) -> None:
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
        without_named = _PLACEHOLDER.sub("", self.sql)
        if _POSITIONAL.search(without_named):
            raise TemplateError(
                f"{self.name}: SQL uses a positional placeholder; Section 4.4"
                f" binds every variable as a named parameter"
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

        # Section 4.4's limits table assigns a row limit per template, and the
        # limit belongs in the registered text so that a caller cannot raise it.
        if f"LIMIT {self.row_limit}" not in self.sql.upper():
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


def _text(field: str, value: object) -> None:
    if not isinstance(value, str) or value == "":
        raise TemplateError(f"{field} must be a non-empty string")
