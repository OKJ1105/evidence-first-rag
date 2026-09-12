"""The pure half of contract `entity-discovery-v0.1`.

What the provisioning path and the discovery runtime both need and neither
may define twice: the Section 4.5 normalization and the Section 4.2 canonical
JSON. Both are byte-defined, use no locale and no library default, and are
shared here so that the tokens the loader stores and the tokens the runtime
binds come from one function, and the digest provisioning writes and the
digest a selection re-derives come from one serializer.

Standard library only. Nothing here opens a connection or imports a driver;
`db/` imports this package, never the other way round.

Every function cites the Section of docs/contracts/entity-discovery-v0.1.md
it implements.
"""

from .canonical import CanonicalError, canonical_json, sha256_hex
from .normalize import normalize

__all__ = ["CanonicalError", "canonical_json", "normalize", "sha256_hex"]
