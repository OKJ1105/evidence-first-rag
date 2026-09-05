"""Section 4.7's deterministic baseline. A control group, and nothing else.

"A deterministic exact-match resolver over a curated request set. A request
whose normalized text exactly matches a registered curated entry yields that
entry's `{route, arguments}`; anything else yields `unsupported`."

Section 4.7 is unusually explicit about what this is *not*: "It exists only as
the control group for the Milestone 2 adapter comparison required by Charter
Section 9. It is not a product path, it is not exposed by any public
interface, and it is not a fallback when the adapter fails."

Those three prohibitions are structural here. Nothing in `revalidation.py`
imports this module, so there is no code path in which a failed adapter call
reaches the baseline; `tests/test_adapter_surface.py` asserts that absence, and
it is the one that would decay quietly, because a fallback is exactly what a
well-meaning later change would add.

**The curated table is not in this file.** Contract Section 9 lists it as an
open decision owned by the contract and registered "before the Milestone 2
comparison", so authoring one here would be this session registering an
evaluation input it also benefits from. `Baseline` takes the table as data; an
empty table resolves nothing, which is the correct behaviour of a baseline
whose entries have not been registered yet, not a placeholder.
"""

import dataclasses
import types
from collections.abc import Mapping

from ..routes import UNSUPPORTED_ROUTE
from .revalidation import Proposal


@dataclasses.dataclass(frozen=True, kw_only=True)
class CuratedEntry:
    """One registered request and the call it stands for."""

    text: str
    route: str
    arguments: Mapping[str, str] = dataclasses.field(default_factory=dict)

    def __post_init__(self) -> None:
        if not isinstance(self.text, str) or self.text.strip() == "":
            raise ValueError("a curated entry needs request text")
        if not isinstance(self.route, str) or self.route == "":
            raise ValueError("a curated entry needs a route")
        object.__setattr__(self, "arguments", types.MappingProxyType(dict(self.arguments)))


def normalize(request_text: str) -> str:
    """The normalization Section 4.7's "normalized text" leaves unfixed.

    Whitespace only: leading and trailing space removed, internal runs
    collapsed to one. **No case folding**, because Section 6 fixes byte-exact
    comparison with no case folding for every other comparison in this
    contract, and a baseline that folded case would be more permissive than
    the runtime it is a control for -- which would flatter it on exactly the
    axis the comparison measures.

    Section 4.7 does not define this, so it is a choice; it is written here
    rather than inline so that a reviewer can disagree with it in one place.
    """
    return " ".join(str(request_text).split())


class Baseline:
    """Exact match over the curated table. Never guesses, never falls back."""

    def __init__(self, entries=()):
        table = {}
        for entry in entries:
            key = normalize(entry.text)
            if key in table:
                raise ValueError(
                    f"two curated entries normalize to the same text: {key!r};"
                    f" an exact-match table cannot hold both"
                )
            table[key] = entry
        self._table = types.MappingProxyType(table)

    def __len__(self) -> int:
        return len(self._table)

    def resolve(self, request_text: str) -> Proposal:
        """The curated entry for `request_text`, or `unsupported`.

        There is no near match, no ranking, and no threshold. Section 4.7
        makes anything but an exact hit `unsupported`, and that severity is
        the point: the baseline's job is to be the honest floor the adapter is
        measured against, not to score well.
        """
        entry = self._table.get(normalize(request_text))
        if entry is None:
            return Proposal(route=UNSUPPORTED_ROUTE, arguments={})
        return Proposal(route=entry.route, arguments=dict(entry.arguments))
