"""Contract Sections 4.6 and 4.7: the Thin LLM Adapter and its control group.

The Milestone 2 half of the contract. An adapter proposes a route and
arguments from free text; deterministic revalidation refuses anything the
contract does not permit; a curated exact-match baseline gives the comparison
a floor; a harness runs both over one frozen request set and reports two
numbers.

Charter Section 3.1 is the boundary this package defends: a model may choose
only an approved route and extract explicitly stated arguments, and **model
output is untrusted input to deterministic contract validation**. Everything
here follows from treating a proposal as hostile until `revalidation.py` has
finished with it.

Nothing exported here imports the SDK. `client.py` -- the only module that
calls a model -- is imported explicitly by whoever has a credential, and the
SDK is an optional extra (`pip install evidence-first-rag[adapter]`) so that a
runtime that answers questions never needs a model library present at all.

The curated request set and the adoption thresholds are the two decisions
Contract Section 9 requires to be registered before the run that judges them;
`evaluation.py` mirrors Section 8.3's registration of both, and
`comparison.judge` refuses to produce a verdict without them.
"""

from .baseline import Baseline, CuratedEntry, normalize
from .comparison import (
    EvaluationCase,
    Judgement,
    Metrics,
    Outcome,
    Report,
    Thresholds,
    compare,
    judge,
    measure,
)
from .evaluation import CURATED, EVALUATION_SET, THRESHOLDS
from .revalidation import Proposal, answer, refused, revalidate

__all__ = [
    "Baseline",
    "CURATED",
    "CuratedEntry",
    "EVALUATION_SET",
    "EvaluationCase",
    "Judgement",
    "Metrics",
    "Outcome",
    "Proposal",
    "Report",
    "THRESHOLDS",
    "Thresholds",
    "answer",
    "compare",
    "judge",
    "measure",
    "normalize",
    "refused",
    "revalidate",
]
