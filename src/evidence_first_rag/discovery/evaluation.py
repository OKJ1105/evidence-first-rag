"""entity-discovery-v0.1 Sections 4.10 and 8.3: the shape of a labeled
discovery evaluation case, the authoring rules a program can check, and the
registration itself.

Two halves, in that order. The first is Section 4.10's: the `EvaluationCase`
type, the eight classes, and `authoring_failures`, which is the assertion
Section 4.10 says "each becomes ... in the slice that registers the set".
The second is Section 8.3's registration -- `REGISTERED_AT`, the
`registry_digest` the set was authored against, the per-class `THRESHOLDS`,
and `REGISTERED_SET`, the forty cases. It landed at `0.3.0` as a minor
version of the contract taken as a recorded human decision, which Charter
Section 9 requires before the run it judges.

The rules come first on purpose: they are what the cases below are checked
against, and `authoring_failures(REGISTERED_SET)` is empty.

Rules 5 (authored without running a method) and 7 (English) are properties
of the authoring session, not of the data; `authoring_failures` does not
claim to check them.
"""

import dataclasses
import enum
import re
from collections.abc import Mapping

from ..references import MessageReference, SignalReference, SnapshotScope
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

# The argument rule 1 does not govern, because it is not a name a case could
# invent: `entity_kind` is one of the two values Section 4.1 enumerates, and
# a Q-OUT case registers one outside them on purpose.
NOT_AN_IDENTIFIER = frozenset({"entity_kind"})

# The classes whose registered term *is* an identifier, so rule 1 governs it
# too. Section 4.10's table fixes Q-EXACT's term as "a term equal to an
# approved entity's lookup key, byte for byte", Q-ALIAS's as a registered
# alias byte for byte, Q-COLLIDE's as "a fully scoped request for a key",
# and Q-NOMATCH's as a name that matches nothing -- which rule 1's "or
# reserved there as absent" clause is what covers. The other three register
# a description (Q-SEMANTIC), a request discovery does not represent
# (Q-OUT), or a term under a scope that never resolves (Q-SCOPE, where the
# term need not be a key), so none of them is a name rule 1 governs.
TERM_IS_AN_IDENTIFIER = frozenset({"Q-EXACT", "Q-ALIAS", "Q-COLLIDE", "Q-NOMATCH"})

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

    Returns one line per violation. An empty list means the set satisfies
    rule 1's first half -- every name a case registers is `SAMPLE_*` -- and
    rules 2 (as far as the type enforces it), 3, 4 and 6.

    What it does not establish: rule 1's second half, that each of those
    names "is either loaded by the `mvp-v0.1` Section 4.11 fixture files or
    reserved there as absent". That is a claim about the fixtures a run
    executes against, not about the cases, and nothing here reads them; the
    registration slice records it, and the `registry_digest` the runner
    writes is how a later change to those files is detected.
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
        # absent. No case invents a name." `entity_kind` is exempt, whose
        # two values Section 4.1 enumerates. The `term` is exempt only where
        # its class registers a description or a request that never reaches
        # a key; in the four classes whose term is itself an identifier it
        # is governed like any other name. Everything else -- the four scope
        # dimensions and `parent_message_key` -- names a row.
        for name, value in case.arguments.items():
            if name in NOT_AN_IDENTIFIER:
                continue
            if name == "term" and case.query_class not in TERM_IS_AN_IDENTIFIER:
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


# --- Section 8.3: the registration -----------------------------------------
#
# Registered as a minor version of the contract, on the repository owner's
# recorded decision (#152). Charter Section 9 requires a numeric adoption
# threshold to be registered before the run it judges: `REGISTERED_AT` is that
# instant, and no run over this set had happened when it was written.

REGISTERED_AT = "2026-09-13T04:20:00Z"
REGISTRATION_CONTRACT_VERSION = "0.3.0"

# Section 8.3 item 2: the registry state the set was authored against. Section
# 4.10 rule 8 makes this how a registry change that alters a registered case's
# outcome is detected rather than remembered.
REGISTERED_AGAINST_DIGEST = "1b81429adae7a373bf434b6a7e1e912991808c94376df849fdfd5c230c608ddb"


class NotABar(enum.Enum):
    """Why a (class, quantity) pair carries no threshold.

    Neither value is a waiver, and the two are different: one says the
    quantity does not exist for the class, the other that it exists and no
    bar on it would say anything.
    """

    #: The Section 4.11 denominator is empty by the class's registered
    #: outcome -- `recall_at_k` over a class that names no target,
    #: `correct_abstention` over a class registered `resolved`. The runner
    #: reports `null`, and a number here is a defect.
    NO_DENOMINATOR = "no denominator"

    #: The denominator exists and the quantity is reported, but the set
    #: itself fixes a ceiling that makes a bar vacuous -- `recall_at_1` over
    #: `Q-MULTI`, where every case registers at least two references that
    #: Section 4.11 requires all of, so no method can score above zero.
    REPORTED = "reported without a bar"


NO_DENOMINATOR = NotABar.NO_DENOMINATOR
REPORTED = NotABar.REPORTED

#: The quantities a threshold is an upper bound on. Every other field is a
#: floor. Stated here so that no reader has to infer a direction from a name.
CEILINGS = frozenset({"false_resolution", "over_abstention"})


@dataclasses.dataclass(frozen=True, kw_only=True)
class ClassThresholds:
    """One class's registered bars, by the Section 4.11 definitions.

    `latency` and `operational_complexity` are not fields: Section 8.3
    registers no bar on either in any class. Latency is reported for
    comparison, and Charter Section 8's pre-registered budget is a vector
    variant's, registered with that variant.
    """

    false_resolution: float | NotABar
    correct_abstention: float | NotABar
    over_abstention: float | NotABar
    recall_at_1: float | NotABar
    recall_at_5: float | NotABar
    recall_at_10: float | NotABar
    task_completion: float | NotABar
    mrr: float | NotABar

    def __post_init__(self) -> None:
        for field in dataclasses.fields(self):
            value = getattr(self, field.name)
            if isinstance(value, NotABar):
                continue
            if not isinstance(value, float) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{field.name} is a fraction between 0 and 1, or a NotABar")

    def as_json(self) -> dict:
        return {
            field.name: (
                getattr(self, field.name).value
                if isinstance(getattr(self, field.name), NotABar)
                else getattr(self, field.name)
            )
            for field in dataclasses.fields(self)
        }


def _resolving(**overrides) -> ClassThresholds:
    """The three classes registered `resolved`.

    Section 4.11 fixes the observed list for such a case as the single
    resolved reference at rank 1, so the three recall values coincide and
    each is 1 minus `over_abstention` once false resolutions are excluded.
    `correct_abstention` has no denominator here: no case in these classes is
    registered as anything but `resolved`.
    """
    return ClassThresholds(
        false_resolution=0.0,
        correct_abstention=NO_DENOMINATOR,
        over_abstention=0.0,
        recall_at_1=1.0, recall_at_5=1.0, recall_at_10=1.0,
        task_completion=1.0,
        mrr=REPORTED,
        **overrides,
    )


def _refusing() -> ClassThresholds:
    """The three classes that register a refusal and name no target."""
    return ClassThresholds(
        false_resolution=0.0,
        correct_abstention=1.0,
        over_abstention=NO_DENOMINATOR,
        recall_at_1=NO_DENOMINATOR, recall_at_5=NO_DENOMINATOR, recall_at_10=NO_DENOMINATOR,
        task_completion=NO_DENOMINATOR,
        mrr=NO_DENOMINATOR,
    )


THRESHOLDS: dict[str, ClassThresholds] = {
    "Q-EXACT": _resolving(),
    "Q-ALIAS": _resolving(),
    "Q-COLLIDE": _resolving(),
    # Both candidate classes register `candidates`, so `over_abstention` has
    # no denominator and `correct_abstention` is the mirror of the false
    # resolution bar. Their recall bars are derived from the cases: see
    # `semantic_recall_bars()` and `multi_recall_ceilings()` below, which the
    # accompanying test recomputes rather than copies.
    "Q-SEMANTIC": ClassThresholds(
        false_resolution=0.0,
        correct_abstention=1.0,
        over_abstention=NO_DENOMINATOR,
        recall_at_1=0.8, recall_at_5=1.0, recall_at_10=1.0,
        task_completion=1.0,
        mrr=REPORTED,
    ),
    "Q-MULTI": ClassThresholds(
        false_resolution=0.0,
        correct_abstention=1.0,
        over_abstention=NO_DENOMINATOR,
        recall_at_1=REPORTED, recall_at_5=0.8, recall_at_10=1.0,
        task_completion=1.0,
        mrr=REPORTED,
    ),
    "Q-SCOPE": _refusing(),
    "Q-NOMATCH": _refusing(),
    "Q-OUT": _refusing(),
}


def semantic_recall_bars(cases) -> dict[int, float]:
    """The `Q-SEMANTIC` recall bars the registered rank bounds entail.

    Section 4.10 rule 3 makes each case register the rank its target must
    meet; the class bar is the fraction of cases whose bound is at or below
    `k`. Written as a function so the registered numbers above can be
    recomputed from the set rather than trusted.
    """
    bounds = [case.rank_bound for case in cases if case.query_class == "Q-SEMANTIC"]
    return {k: sum(1 for bound in bounds if bound <= k) / len(bounds) for k in (1, 5, 10)}


def multi_recall_ceilings(cases) -> dict[int, float]:
    """The highest `recall_at_k` any method can reach on `Q-MULTI`.

    Section 4.11 counts a `Q-MULTI` case only when **every** registered
    reference appears at rank at or below `k`, so a case registering `n`
    references cannot count for `k` < `n` whatever a method does.
    """
    sizes = [len(case.expected_references) for case in cases if case.query_class == "Q-MULTI"]
    return {k: sum(1 for size in sizes if size <= k) / len(sizes) for k in (1, 5, 10)}


# --- The registered cases ---------------------------------------------------
#
# Section 4.10 rule 5: every case below was authored by reading the fixture
# rows and Section 4.5's tier table, and **not** by running any retrieval
# method over it. A case edited to agree with a method's output would make the
# set measure whether that method equals itself.

_ALPHA = "SAMPLE_PROJECT_ALPHA"

_PT_BASE = SnapshotScope(project_code=_ALPHA, revision_label="SAMPLE_REV_A",
                         network_name="SAMPLE_NET_POWERTRAIN", snapshot_label="SAMPLE_SNAP_BASE")
_PT_REVISED = dataclasses.replace(_PT_BASE, snapshot_label="SAMPLE_SNAP_REVISED")
_CH_A = dataclasses.replace(_PT_BASE, network_name="SAMPLE_NET_CHASSIS")
_CH_B = dataclasses.replace(_CH_A, revision_label="SAMPLE_REV_B")

_ENGINE_STATUS = "SAMPLE_MSG_ENGINE_STATUS"
_TRANSMISSION_STATE = "SAMPLE_MSG_TRANSMISSION_STATE"
_WHEEL_SPEED = "SAMPLE_MSG_WHEEL_SPEED"
_DIAGNOSTIC_EVENT = "SAMPLE_MSG_DIAGNOSTIC_EVENT"
_BRAKE_STATUS = "SAMPLE_MSG_BRAKE_STATUS"


def _message(scope, key):
    return MessageReference(scope=scope, message_key=key)


def _signal(scope, parent, key):
    return SignalReference(message=_message(scope, parent), signal_key=key)


def _request(scope, **rest):
    return {
        "project_code": scope.project_code,
        "revision_label": scope.revision_label,
        "network_name": scope.network_name,
        "snapshot_label": scope.snapshot_label,
    } | rest


REGISTERED_SET: tuple[EvaluationCase, ...] = (
    # Q-EXACT: the term is an approved lookup key that reaches exactly one
    # entity at tiers 1-2 in its scope and kind, so Section 4.7 resolves.
    # EV-EXACT-3's parent message is deliberately not an approved entity --
    # SAMPLE_MSG_DIAGNOSTIC_EVENT is one of DX-015's two -- because the
    # registry allowlists entities and not trees.
    EvaluationCase(
        identifier="EV-EXACT-1", query_class="Q-EXACT",
        arguments=_request(_PT_BASE, entity_kind="message", term=_TRANSMISSION_STATE),
        expected_outcome="resolved",
        expected_references=(_message(_PT_BASE, _TRANSMISSION_STATE),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-EXACT-2", query_class="Q-EXACT",
        arguments=_request(_PT_BASE, entity_kind="message", term=_BRAKE_STATUS),
        expected_outcome="resolved",
        expected_references=(_message(_PT_BASE, _BRAKE_STATUS),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-EXACT-3", query_class="Q-EXACT",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_FAULT_CODE"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _DIAGNOSTIC_EVENT, "SAMPLE_SIG_FAULT_CODE"),),
        target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-EXACT-4", query_class="Q-EXACT",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_BRAKE_PRESSURE"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _BRAKE_STATUS, "SAMPLE_SIG_BRAKE_PRESSURE"),),
        target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-EXACT-5", query_class="Q-EXACT",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_CLUTCH_STATE"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_CLUTCH_STATE"),),
        target_route=Route.SIGNAL_FACTS),

    # Q-ALIAS: the term equals a registered alias byte for byte, so the match
    # is tier 2. EV-ALIAS-2 is the spelling_variant; EV-ALIAS-3 is scoped to
    # the superseded chassis snapshot, where its alias is asserted, so the run
    # records the Section 7 supersession limitation on a positive outcome;
    # EV-ALIAS-5 resolves an entity whose own key cannot, which is what an
    # approved alias is for.
    EvaluationCase(
        identifier="EV-ALIAS-1", query_class="Q-ALIAS",
        arguments=_request(_PT_BASE, entity_kind="message", term="SAMPLE_ALIAS_GEARBOX_STATE"),
        expected_outcome="resolved",
        expected_references=(_message(_PT_BASE, _TRANSMISSION_STATE),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-ALIAS-2", query_class="Q-ALIAS",
        arguments=_request(_PT_BASE, entity_kind="message", term="SAMPLE_MSG_TRANSMISION_STATE"),
        expected_outcome="resolved",
        expected_references=(_message(_PT_BASE, _TRANSMISSION_STATE),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-ALIAS-3", query_class="Q-ALIAS",
        arguments=_request(_CH_A, entity_kind="message", term="SAMPLE_ALIAS_WHEEL_SPEEDS"),
        expected_outcome="resolved",
        expected_references=(_message(_CH_A, _WHEEL_SPEED),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-ALIAS-4", query_class="Q-ALIAS",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_ALIAS_ENGINE_ROTATION_SPEED"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_ENGINE_SPEED"),),
        target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-ALIAS-5", query_class="Q-ALIAS",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_ALIAS_COOLANT_TEMPERATURE"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_TEMPERATURE"),),
        target_route=Route.SIGNAL_FACTS),

    # Q-COLLIDE: a key approved in two snapshots, each request fully scoped to
    # one, the other snapshot's occurrence absent from the result.
    EvaluationCase(
        identifier="EV-COLLIDE-1", query_class="Q-COLLIDE",
        arguments=_request(_PT_BASE, entity_kind="message", term=_ENGINE_STATUS),
        expected_outcome="resolved",
        expected_references=(_message(_PT_BASE, _ENGINE_STATUS),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-COLLIDE-2", query_class="Q-COLLIDE",
        arguments=_request(_CH_B, entity_kind="message", term=_WHEEL_SPEED),
        expected_outcome="resolved",
        expected_references=(_message(_CH_B, _WHEEL_SPEED),),
        target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-COLLIDE-3", query_class="Q-COLLIDE",
        arguments=_request(_CH_B, entity_kind="signal", term="SAMPLE_SIG_WHEEL_SPEED_FL"),
        expected_outcome="resolved",
        expected_references=(_signal(_CH_B, _WHEEL_SPEED, "SAMPLE_SIG_WHEEL_SPEED_FL"),),
        target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-COLLIDE-4", query_class="Q-COLLIDE",
        arguments=_request(_PT_REVISED, entity_kind="signal", term="SAMPLE_SIG_ENGINE_SPEED"),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_REVISED, _ENGINE_STATUS, "SAMPLE_SIG_ENGINE_SPEED"),),
        target_route=Route.SIGNAL_FACTS),
    # The one case whose outcome turns on `parent_message_key`: the key is in
    # two snapshots (Q-COLLIDE) *and* under two parents in this one (DX-005),
    # so a method that ignores the parameter returns `candidates` here and
    # scores a miss rather than passing unnoticed.
    EvaluationCase(
        identifier="EV-COLLIDE-5", query_class="Q-COLLIDE",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_TEMPERATURE",
                           parent_message_key=_ENGINE_STATUS),
        expected_outcome="resolved",
        expected_references=(_signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_TEMPERATURE"),),
        target_route=Route.SIGNAL_FACTS),

    # Q-SEMANTIC: a description equal to no match text, reaching its target by
    # Section 4.5 tier-4 token containment. EV-SEMANTIC-4's bound is 2 because
    # the term reaches two entities and Section 4.6 orders the other first; a
    # bound of 1 would register a bar the contract's own ordering forbids.
    EvaluationCase(
        identifier="EV-SEMANTIC-1", query_class="Q-SEMANTIC",
        arguments=_request(_PT_BASE, entity_kind="signal", term="engine speed"),
        expected_outcome="candidates",
        expected_references=(_signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_ENGINE_SPEED"),),
        rank_bound=1, target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-SEMANTIC-2", query_class="Q-SEMANTIC",
        arguments=_request(_PT_BASE, entity_kind="signal", term="brake pressure"),
        expected_outcome="candidates",
        expected_references=(_signal(_PT_BASE, _BRAKE_STATUS, "SAMPLE_SIG_BRAKE_PRESSURE"),),
        rank_bound=1, target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-SEMANTIC-3", query_class="Q-SEMANTIC",
        arguments=_request(_PT_BASE, entity_kind="signal", term="clutch state"),
        expected_outcome="candidates",
        expected_references=(_signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_CLUTCH_STATE"),),
        rank_bound=1, target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-SEMANTIC-4", query_class="Q-SEMANTIC",
        arguments=_request(_PT_BASE, entity_kind="signal", term="gear position"),
        expected_outcome="candidates",
        expected_references=(_signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_GEAR_POSITION"),),
        rank_bound=2, target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-SEMANTIC-5", query_class="Q-SEMANTIC",
        arguments=_request(_PT_BASE, entity_kind="signal", term="coolant temperature"),
        expected_outcome="candidates",
        expected_references=(_signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_TEMPERATURE"),),
        rank_bound=1, target_route=Route.SIGNAL_FACTS),

    # Q-MULTI: two or more approved entities in the resolved scope, and never
    # a resolution. EV-MULTI-1 is the tier-1-against-tier-2 collision
    # (DX-004); EV-MULTI-2 is the two-parent collision (DX-005) reached
    # lexically; the rest widen from two entities to seven, so a method is
    # scored on abstaining as the list grows. All are within k = 10.
    EvaluationCase(
        identifier="EV-MULTI-1", query_class="Q-MULTI",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_GEAR_POSITION"),
        expected_outcome="candidates",
        expected_references=(
            _signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_GEAR_POSITION"),
            _signal(_PT_BASE, _DIAGNOSTIC_EVENT, "SAMPLE_SIG_FAULT_CODE"),
        ), target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-MULTI-2", query_class="Q-MULTI",
        arguments=_request(_PT_BASE, entity_kind="signal", term="temperature"),
        expected_outcome="candidates",
        expected_references=(
            _signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_TEMPERATURE"),
            _signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_TEMPERATURE"),
        ), target_route=Route.SIGNAL_FACTS),
    EvaluationCase(
        identifier="EV-MULTI-3", query_class="Q-MULTI",
        arguments=_request(_PT_BASE, entity_kind="message", term="status"),
        expected_outcome="candidates",
        expected_references=(
            _message(_PT_BASE, _BRAKE_STATUS), _message(_PT_BASE, _ENGINE_STATUS),
        ), target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-MULTI-4", query_class="Q-MULTI",
        arguments=_request(_PT_BASE, entity_kind="message", term="sample msg"),
        expected_outcome="candidates",
        expected_references=(
            _message(_PT_BASE, _BRAKE_STATUS), _message(_PT_BASE, _ENGINE_STATUS),
            _message(_PT_BASE, _TRANSMISSION_STATE),
        ), target_route=Route.MESSAGE_FACTS),
    EvaluationCase(
        identifier="EV-MULTI-5", query_class="Q-MULTI",
        arguments=_request(_PT_BASE, entity_kind="signal", term="sample sig"),
        expected_outcome="candidates",
        expected_references=(
            _signal(_PT_BASE, _BRAKE_STATUS, "SAMPLE_SIG_BRAKE_PRESSURE"),
            _signal(_PT_BASE, _DIAGNOSTIC_EVENT, "SAMPLE_SIG_FAULT_CODE"),
            _signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_ENGINE_SPEED"),
            _signal(_PT_BASE, _ENGINE_STATUS, "SAMPLE_SIG_TEMPERATURE"),
            _signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_CLUTCH_STATE"),
            _signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_GEAR_POSITION"),
            _signal(_PT_BASE, _TRANSMISSION_STATE, "SAMPLE_SIG_TEMPERATURE"),
        ), target_route=Route.SIGNAL_FACTS),

    # Q-SCOPE: one scope dimension absent, so mvp-v0.1 Section 4.2 answers
    # `ambiguous` and no discovery template executes. EV-SCOPE-3 omits
    # snapshot_label where the remaining scope holds exactly one snapshot --
    # FX-113's rule that one candidate is still ambiguous. EV-SCOPE-4 omits
    # revision_label, so the class is not a test of one dimension.
    EvaluationCase(
        identifier="EV-SCOPE-1", query_class="Q-SCOPE",
        arguments={"project_code": _ALPHA, "revision_label": "SAMPLE_REV_A",
                   "network_name": "SAMPLE_NET_POWERTRAIN",
                   "entity_kind": "message", "term": "engine status"},
        expected_outcome="ambiguous"),
    EvaluationCase(
        identifier="EV-SCOPE-2", query_class="Q-SCOPE",
        arguments={"project_code": _ALPHA, "revision_label": "SAMPLE_REV_A",
                   "network_name": "SAMPLE_NET_POWERTRAIN",
                   "entity_kind": "message", "term": "transmission state"},
        expected_outcome="ambiguous"),
    EvaluationCase(
        identifier="EV-SCOPE-3", query_class="Q-SCOPE",
        arguments={"project_code": _ALPHA, "revision_label": "SAMPLE_REV_B",
                   "network_name": "SAMPLE_NET_CHASSIS",
                   "entity_kind": "message", "term": "wheel speed"},
        expected_outcome="ambiguous"),
    EvaluationCase(
        identifier="EV-SCOPE-4", query_class="Q-SCOPE",
        arguments={"project_code": _ALPHA, "network_name": "SAMPLE_NET_POWERTRAIN",
                   "snapshot_label": "SAMPLE_SNAP_BASE",
                   "entity_kind": "signal", "term": "fault code"},
        expected_outcome="ambiguous"),
    EvaluationCase(
        identifier="EV-SCOPE-5", query_class="Q-SCOPE",
        arguments={"project_code": _ALPHA, "revision_label": "SAMPLE_REV_A",
                   "network_name": "SAMPLE_NET_POWERTRAIN",
                   "entity_kind": "signal", "term": "temperature reading"},
        expected_outcome="ambiguous"),

    # Q-NOMATCH: a name reserved as absent in fixtures/README.md. Each carries
    # a token that occurs in no match_tokens, so the term misses tier 4 as
    # well as tiers 1-3.
    EvaluationCase(
        identifier="EV-NOMATCH-1", query_class="Q-NOMATCH",
        arguments=_request(_PT_BASE, entity_kind="message", term="SAMPLE_MSG_ABSENT"),
        expected_outcome="not_found"),
    EvaluationCase(
        identifier="EV-NOMATCH-2", query_class="Q-NOMATCH",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_ABSENT"),
        expected_outcome="not_found"),
    EvaluationCase(
        identifier="EV-NOMATCH-3", query_class="Q-NOMATCH",
        arguments=_request(_PT_BASE, entity_kind="message", term="SAMPLE_MSG_UNREGISTERED"),
        expected_outcome="not_found"),
    EvaluationCase(
        identifier="EV-NOMATCH-4", query_class="Q-NOMATCH",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_UNREGISTERED"),
        expected_outcome="not_found"),
    EvaluationCase(
        identifier="EV-NOMATCH-5", query_class="Q-NOMATCH",
        arguments=_request(_PT_BASE, entity_kind="signal", term="SAMPLE_SIG_MISSING"),
        expected_outcome="not_found"),

    # Q-OUT: three entity_kind values outside the two Section 4.1 enumerates,
    # refused before any connection; and two complete scopes naming no
    # snapshot. EV-OUT-5's parts all exist -- SAMPLE_REV_B and
    # SAMPLE_NET_POWERTRAIN both do -- but not together, so a method checking
    # each dimension separately answers it wrongly.
    EvaluationCase(
        identifier="EV-OUT-1", query_class="Q-OUT",
        arguments=_request(_PT_BASE, entity_kind="mapping", term="signal mapping"),
        expected_outcome="unsupported"),
    EvaluationCase(
        identifier="EV-OUT-2", query_class="Q-OUT",
        arguments=_request(_PT_BASE, entity_kind="snapshot", term="snapshot listing"),
        expected_outcome="unsupported"),
    EvaluationCase(
        identifier="EV-OUT-3", query_class="Q-OUT",
        arguments=_request(_PT_BASE, entity_kind="network", term="network members"),
        expected_outcome="unsupported"),
    EvaluationCase(
        identifier="EV-OUT-4", query_class="Q-OUT",
        arguments=_request(_PT_BASE, network_name="SAMPLE_NET_BODY",
                           entity_kind="message", term="body controller"),
        expected_outcome="coverage_gap"),
    EvaluationCase(
        identifier="EV-OUT-5", query_class="Q-OUT",
        arguments=_request(_PT_BASE, revision_label="SAMPLE_REV_B",
                           entity_kind="message", term="powertrain revision b"),
        expected_outcome="coverage_gap"),
)
