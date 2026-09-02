"""Construction-time checks shared by the types in this package.

These are deliberately not runtime guards. Section 4.2 forbids the runtime
from supplying a missing scope dimension, and Section 5 forbids a result that
omits its evidence; a check somebody has to remember to call is a rule that
somebody eventually forgets. Every type in this package validates in
__post_init__ instead, so a violating value has no representation.
"""


def required_text(field: str, value: object) -> str:
    """Return `value` when it is a non-empty string, else raise ValueError.

    Empty means the empty string. A value that is only whitespace is passed
    through: Section 6 fixes byte-exact comparison with no trimming, so
    treating " " as absent here would introduce the normalization the
    contract prohibits. Such a value simply fails to match a stored key,
    which is the fail-closed outcome Section 5 already covers.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, not {type(value).__name__}")
    if value == "":
        raise ValueError(f"{field} must not be empty")
    return value


def optional_text(field: str, value: object) -> str:
    """Return `value` when it is a string, else raise ValueError.

    The empty string is the "explicit empty value" Section 7 permits for
    `template_name` and `template_version` when no database was opened. It is
    a value, not an absence, which is why these fields are never None.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field} must be a string, not {type(value).__name__}")
    return value


def required_flag(field: str, value: object) -> bool:
    """Return `value` when it is a bool, else raise ValueError.

    bool is checked before int deliberately: `connection_opened=1` would be
    truthy and would record a safeguard the runtime never took.
    """
    if not isinstance(value, bool):
        raise ValueError(f"{field} must be a bool, not {type(value).__name__}")
    return value


def text_tuple(field: str, value: object) -> tuple[str, ...]:
    """Return `value` as a tuple of non-empty strings, else raise ValueError."""
    if isinstance(value, str) or not hasattr(value, "__iter__"):
        raise ValueError(f"{field} must be an iterable of strings")
    items = tuple(value)
    for index, item in enumerate(items):
        required_text(f"{field}[{index}]", item)
    return items
