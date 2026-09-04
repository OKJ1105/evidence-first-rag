"""The contract this package implements, named once.

Section 1 of docs/contracts/mvp-v0.1.md gives the identifier and the version;
Section 7 requires every evidence bundle to carry both. Section 6 fixes the
collation the bundle records. They are constants here so that one edit moves
them everywhere a result cites them, and so that a reader can see which
version of the contract this code claims to satisfy.
"""

# Section 1.
CONTRACT_IDENTIFIER = "mvp-v0.1"
CONTRACT_VERSION = "0.5.0"

# Section 6: the database is created with LC_COLLATE='C' and ordering is
# byte-wise. The evidence bundle records "C".
COLLATION = "C"
