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


def sha256_hex(data: bytes) -> str:
    """Lower-case hexadecimal SHA-256, the form every digest in the contract
    takes."""
    return hashlib.sha256(data).hexdigest()


def _write(value, parts: list[str]) -> None:
    # bool is checked before int: True is an int in Python, and the contract's
    # digest inputs carry no boolean, so one reaching here is a caller error.
    if value is None:
        parts.append("null")
    elif isinstance(value, bool):
        raise CanonicalError("a boolean is not a Section 4.2 digest input")
    elif isinstance(value, int):
        # Shortest decimal form. Python's int repr has no sign for a
        # non-negative value, no fraction, and no exponent.
        if value < 0:
            raise CanonicalError("a negative integer is not a Section 4.2 digest input")
        parts.append(str(value))
    elif isinstance(value, str):
        _write_string(value, parts)
    elif isinstance(value, (list, tuple)):
        parts.append("[")
        for index, item in enumerate(value):
            if index:
                parts.append(",")
            _write(item, parts)
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
            _write(value[key], parts)
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
