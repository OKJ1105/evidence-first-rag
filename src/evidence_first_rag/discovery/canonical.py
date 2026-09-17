"""Section 4.2: canonical JSON, and the digest computed over it.

The contract states the rules inline "so that the digest does not depend on
any library's defaults", and this module is written against those rules
rather than against `json.dumps`. The two differ in ways that change a
digest: `json.dumps` writes a newline as `\\n` where the contract requires
`\\u000a`, and with `ensure_ascii=True` it would escape every non-ASCII
character. Both produce valid JSON; neither produces the byte sequence two
implementations are required to agree on.

The rules, from Section 4.2:

- UTF-8 output; a character JSON does not require escaping is written as
  itself, never as a `\\u` escape.
- The escape set is exactly RFC 8259's minimum: `"` as `\\"`, `\\` as `\\\\`,
  and U+0000-U+001F as `\\u` plus four lower-case hexadecimal digits. `/` is
  written as `/`.
- Object keys are sorted by their UTF-8 bytes. No whitespace outside strings.
- An absent value is `null`. An integer is its shortest decimal form; no
  other number appears in any digest input.
- A timestamp is a string in RFC 3339 form, UTC, second precision, `Z`.
  Arrays keep their order.

A value outside that vocabulary -- a float, a bool, a datetime that was not
formatted by the caller -- is refused rather than guessed at. The contract
says no other number appears in a digest input; a serializer that quietly
accepted one would produce a digest some other conforming implementation
could not.
"""

import hashlib


class CanonicalError(ValueError):
    """A value the Section 4.2 vocabulary does not contain."""


def canonical_json(value) -> bytes:
    """The Section 4.2 canonical serialization of `value`, as UTF-8 bytes."""
    parts: list[str] = []
    _write(value, parts)
    return "".join(parts).encode("utf-8")


def json_text(value) -> str:
    """The Section 4.2 rules over the one value a digest input may not hold.

    Same escape set, same key order, same absence of whitespace as
    `canonical_json` -- and a boolean is written rather than refused.
    `api-v0.1` Section 4.4 cites these rules for a wire document, and three of
    every document's values are booleans: `read_only_safeguards` carries
    `read_only_transaction` and `connection_opened`, and no result lacks them.

    Kept here rather than written a second time in `api/`, because the rules
    this module's docstring lists are the thing two implementations have to
    agree on, and an escape set defined in two places is an escape set that
    will one day differ in one of them. `canonical_json` still refuses a
    boolean: a digest input may not hold one, and that is a different
    obligation from what a response body may carry.
    """
    parts: list[str] = []
    _write(value, parts, booleans=True)
    return "".join(parts)


def sha256_hex(data: bytes) -> str:
    """Lower-case hexadecimal SHA-256, the form every digest in the contract
    takes."""
    return hashlib.sha256(data).hexdigest()


def _write(value, parts: list[str], *, booleans: bool = False) -> None:
    # bool is checked before int: True is an int in Python, and the contract's
    # digest inputs carry no boolean, so one reaching here is a caller error
    # unless the caller is `json_text`, which serializes a wire document.
    if value is None:
        parts.append("null")
    elif isinstance(value, bool):
        if not booleans:
            raise CanonicalError("a boolean is not a Section 4.2 digest input")
        parts.append("true" if value else "false")
    elif isinstance(value, int):
        # Shortest decimal form. Python's int repr has no fraction and no
        # exponent, and carries a leading `-` exactly when the value is
        # negative, which is the same shortest form JSON gives it.
        #
        # A negative integer is refused for a digest input and written for a
        # wire document, for the reason the boolean split above gives. No
        # Section 4.2 digest input is negative -- ranks, counts, tiers and
        # widths are all non-negative -- so one reaching `canonical_json` is a
        # caller error. A **result row** is a different matter: the schema
        # gives `frame_identifier`, `bit_offset` and `transmit_period_ms` a
        # plain `integer` with no non-negativity CHECK, so a loaded row may
        # carry one, and `api-v0.1` Section 4.2 has to put it on the wire. A
        # serializer that refused would turn a correct `success` into an
        # HTTP 500 `runtime_fault` -- a true answer reported as a fault, which
        # Charter Section 3.4 is written against.
        if value < 0 and not booleans:
            raise CanonicalError("a negative integer is not a Section 4.2 digest input")
        parts.append(str(value))
    elif isinstance(value, str):
        _write_string(value, parts)
    elif isinstance(value, (list, tuple)):
        parts.append("[")
        for index, item in enumerate(value):
            if index:
                parts.append(",")
            _write(item, parts, booleans=booleans)
        parts.append("]")
    elif isinstance(value, dict):
        parts.append("{")
        # Sorted by UTF-8 bytes. Sorting the str keys by code point gives the
        # same order, because UTF-8 preserves code-point order, but encoding
        # first is what the contract says and costs nothing.
        for index, key in enumerate(sorted(value, key=_utf8)):
            if not isinstance(key, str):
                raise CanonicalError(f"object key {key!r} is not a string")
            if index:
                parts.append(",")
            _write_string(key, parts)
            parts.append(":")
            _write(value[key], parts, booleans=booleans)
        parts.append("}")
    else:
        raise CanonicalError(
            f"{type(value).__name__} is not a Section 4.2 digest input"
        )


def _utf8(key) -> bytes:
    if not isinstance(key, str):
        raise CanonicalError(f"object key {key!r} is not a string")
    return key.encode("utf-8")


def _write_string(text: str, parts: list[str]) -> None:
    parts.append('"')
    for character in text:
        code = ord(character)
        if character == '"':
            parts.append('\\"')
        elif character == "\\":
            parts.append("\\\\")
        elif code < 0x20:
            parts.append(f"\\u{code:04x}")
        else:
            parts.append(character)
    parts.append('"')
