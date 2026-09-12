"""entity-discovery-v0.1 Section 4.10: the shape of a labeled discovery
evaluation case, and the authoring rules a program can check.

This module authors no case and registers no number. Section 8.3 is reserved
for the registration, which is a minor version of the contract taken as a
recorded human decision, and Charter Section 9 requires it before the run it
judges. What lives here is the type a registration will be written in and
the assertions Section 4.10 says "each becomes ... in the slice that
registers the set" -- shipped now so that the registration slice inherits
them rather than writing them beside the numbers they govern.

Rules 5 (authored without running a method) and 7 (English) are properties
of the authoring session, not of the data; `authoring_failures` does not
claim to check them.
"""

import dataclasses
import re
from collections.abc import Mapping

from ..references import MessageReference, SignalReference
from ..routes import Route
from .normalize import normalize

# Section 4.10's eight classes, one per Charter Section 8 bullet, with the
# outcome family each registers.
CLASSES = (
    "Q-EXACT",
    "Q-ALIAS",
    "Q-SEMANTIC",
    "Q-SCOPE",
    "Q-COLLIDE",
    "Q-MULTI",
    "Q-NOMATCH",
    "Q-OUT",
)
EXPECTED_OUTCOME = {
    "Q-EXACT": ("resolved",),
    "Q-ALIAS": ("resolved",),
    "Q-SEMANTIC": ("candidates",),
    "Q-SCOPE": ("ambiguous",),
    "Q-COLLIDE": ("resolved",),
    "Q-MULTI": ("candidates",),
    "Q-NOMATCH": ("not_found",),
    "Q-OUT": ("unsupported", "coverage_gap"),
}

# The classes whose registration names a target reference (Section 4.11,
# recall_at_k and mrr are computed over these).
NAMES_A_TARGET = frozenset({"Q-EXACT", "Q-ALIAS", "Q-SEMANTIC", "Q-COLLIDE", "Q-MULTI"})

# Section 4.10 rule 4.
MINIMUM_PER_CLASS = 5

SAMPLE = re.compile(r"\ASAMPLE_[A-Za-z0-9_.\-]+\Z")

# The arguments rule 1 does not govern, because neither is a name a case
# could invent: the term is free text, and `entity_kind` is one of the two
# values Section 4.1 enumerates.
NOT_AN_IDENTIFIER = frozenset({"term", "entity_kind"})

# The classes whose registered request is refused before any term is
# normalized -- an `entity_kind` outside the two, or a scope that never
# resolves -- so a term with no token is not a defect in them.
TERM_MAY_HAVE_NO_TOKEN = frozenset({"Q-OUT", "Q-SCOPE"})


@dataclasses.dataclass(frozen=True, kw_only=True)
class EvaluationCase:
    """One registered case (Section 4.10 rule 2).

    `expected_references` names the canonical reference(s) the outcome must
    carry: exactly one for a `resolved` class, one or more for `Q-MULTI`,
    one for `Q-SEMANTIC`, none otherwise. `rank_bound` is the rank the
    `Q-SEMANTIC` target must meet (rule 3). `target_route` is the mvp-v0.1
    route `task_completion` dispatches the reference to; None for a class
    that names no target.
    """

    identifier: str
    query_class: str
    arguments: Mapping[str, str]
    expected_outcome: str
    expected_references: tuple[MessageReference | SignalReference, ...] = ()
    rank_bound: int | None = None
    target_route: Route | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.identifier, str) or not self.identifier:
            raise ValueError("identifier must be a non-empty string")
        if self.query_class not in CLASSES:
            raise ValueError(f"query_class must be one of {CLASSES}")
        if not isinstance(self.arguments, Mapping):
            raise ValueError("arguments must be a mapping")
        object.__setattr__(self, "arguments", dict(self.arguments))
        if self.expected_outcome not in EXPECTED_OUTCOME[self.query_class]:
            raise ValueError(
                f"{self.query_class} registers {EXPECTED_OUTCOME[self.query_class]}, not"
                f" {self.expected_outcome!r} (Section 4.10)"
            )
        object.__setattr__(self, "expected_references", tuple(self.expected_references))
        for reference in self.expected_references:
            if not isinstance(reference, (MessageReference, SignalReference)):
                raise ValueError("expected_references holds canonical references")
        names_target = self.query_class in NAMES_A_TARGET
        if names_target and not self.expected_references:
            raise ValueError(f"{self.query_class} registers a target reference (rule 2)")
        if not names_target and self.expected_references:
            raise ValueError(f"{self.query_class} names no target")
        if self.query_class != "Q-MULTI" and len(self.expected_references) > 1:
            raise ValueError("only Q-MULTI registers more than one reference")
        if self.query_class == "Q-SEMANTIC":
            if not isinstance(self.rank_bound, int) or isinstance(self.rank_bound, bool) or not 1 <= self.rank_bound <= 10:
                raise ValueError("a Q-SEMANTIC case registers the rank bound its target must meet (rule 3)")
        elif self.rank_bound is not None:
            raise ValueError("only Q-SEMANTIC registers a rank bound")
        if self.target_route is not None and not isinstance(self.target_route, Route):
            raise ValueError("target_route is an mvp-v0.1 Route or None")
        if self.target_route is not None and not names_target:
            raise ValueError("a case with no target names no target route")

    @property
    def term(self) -> str:
        return str(self.arguments.get("term", ""))


def authoring_failures(cases) -> list[str]:
    """Every Section 4.10 authoring rule a program can check, over `cases`.

    Returns one line per violation; an empty list means the set satisfies
    rules 1, 2 (as far as the type enforces it), 3, 4 and 6.
    """
    failures: list[str] = []
    cases = tuple(cases)
    seen_identifiers: dict[str, str] = {}
    seen_texts: dict[tuple[str, ...], str] = {}
    per_class = {name: 0 for name in CLASSES}

    for case in cases:
        if case.identifier in seen_identifiers:
            failures.append(f"{case.identifier}: identifier registered twice")
        seen_identifiers[case.identifier] = case.query_class
        per_class[case.query_class] += 1

        # Rule 1: "Every identifier is `SAMPLE_*` and is either loaded by
        # the `mvp-v0.1` Section 4.11 fixture files or reserved there as
        # absent. No case invents a name." Two arguments are not identifiers
        # a case could invent and are exempt: `term`, which is the user's
        # free text and for a Q-SEMANTIC case is a description rather than a
        # name; and `entity_kind`, whose two values Section 4.1 enumerates.
        # Everything else -- the four scope dimensions and
        # `parent_message_key` -- names a row.
        for name, value in case.arguments.items():
            if name in NOT_AN_IDENTIFIER:
                continue
            if not isinstance(value, str) or not SAMPLE.match(value):
                failures.append(f"{case.identifier}: argument {name}={value!r} is not a SAMPLE_* identifier (rule 1)")

        # Rule 6: no two case texts equal after normalization.
        tokens = tuple(normalize(case.term))
        if not tokens and case.query_class not in TERM_MAY_HAVE_NO_TOKEN:
            failures.append(f"{case.identifier}: the term normalizes to no token")
        if tokens:
            if tokens in seen_texts:
                failures.append(
                    f"{case.identifier}: term normalizes to the same tokens as {seen_texts[tokens]} (rule 6)"
                )
            else:
                seen_texts[tokens] = case.identifier

    # Rule 4: at least five per class.
    for name, count in per_class.items():
        if count < MINIMUM_PER_CLASS:
            failures.append(f"{name}: {count} case(s) registered; rule 4 requires at least {MINIMUM_PER_CLASS}")
    return failures


# Section 8.3 is reserved: no set is registered. The runner refuses to run
# over nothing, and the registration slice replaces this with the cases the
# owner records.
REGISTERED_SET: tuple[EvaluationCase, ...] = ()
