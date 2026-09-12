"""Section 4.5: the discovery normalization.

    For a text `t`, `normalize(t)` is: map each ASCII upper-case letter to
    its lower-case form; replace every character that is not `a-z` or `0-9`
    with a single space; split on spaces; drop empty tokens.

Defined on bytes, on purpose. `str.lower()` folds by Unicode rules and would
turn a non-ASCII letter into another letter; the contract maps every
non-ASCII byte to a separator instead, "the same reason `mvp-v0.1` Section 6
chose the `C` collation". So the text is encoded to UTF-8 first and every
byte is judged alone, which is identical on every platform.

This applies to candidate generation only. Section 4.5 is explicit that a
fact lookup never normalizes: the reference discovery hands to a fact route
is a byte-exact key from the registry, never the output of this function.
"""

# The bytes that survive normalization unchanged: a-z and 0-9. Everything else
# becomes a separator. Written as a translation table so the rule is one
# lookup per byte and has no locale to consult.
_TABLE = bytes(
    ord("a") + (byte - ord("A")) if ord("A") <= byte <= ord("Z")
    else byte if ord("a") <= byte <= ord("z") or ord("0") <= byte <= ord("9")
    else ord(" ")
    for byte in range(256)
)


def normalize(text: str) -> list[str]:
    """Section 4.5: the ordered token list of `text`.

    The result is a list of non-empty ASCII strings drawn from `a-z0-9`, in
    the order they occur. It may be empty: Section 4.3 makes a term with no
    token `invalid_request`, and Section 4.2 rule 5 refuses an alias with no
    token at load, so the callers decide what emptiness means; this function
    only reports it.
    """
    if not isinstance(text, str):
        raise TypeError(f"normalize() takes a str, not {type(text).__name__}")
    return text.encode("utf-8").translate(_TABLE).decode("ascii").split()
