"""Nothing in `tests/` is defined after its `if __name__ == "__main__":`.

A class placed below that block is still collected by `unittest discover`,
which is how CI runs this tree, so the defect is invisible where it is
looked for. It bites the reader instead: every other class in the file sits
above the block, and one below it reads as an afterthought or as dead code.
`__main__` is the last thing in a module, and this is that rule stated once
rather than trusted forty-two times.

Two files carried the defect when this was written, and only one of them was
named in the Issue that led here -- which is the argument for a check over
the tree rather than a fix to the file someone happened to notice.
"""

import ast
import pathlib
import unittest

SUITE = pathlib.Path(__file__).resolve().parent

MAIN_TEST = "__name__ == '__main__'"


def _stranded(source: str) -> list[str]:
    """Top-level names defined after the `__main__` block, in order.

    Read from the parsed tree rather than by matching text, so a string or a
    comment mentioning `__main__` cannot move the boundary.
    """
    tree = ast.parse(source)
    after = []
    seen_main = False
    for node in tree.body:
        if isinstance(node, ast.If) and ast.unparse(node.test) == MAIN_TEST:
            seen_main = True
        elif seen_main:
            after.append(getattr(node, "name", type(node).__name__))
    return after


class TheMainBlockIsLast(unittest.TestCase):
    def test_no_module_defines_anything_after_it(self):
        for path in sorted(SUITE.glob("*.py")):
            with self.subTest(module=path.name):
                self.assertEqual(_stranded(path.read_text(encoding="utf-8")), [])


class TheCheckItself(unittest.TestCase):
    """The assertion above passes on a tree with the defect removed, so it
    has to be shown to fail on one that has it. These two drive the reader
    rather than the suite."""

    def test_a_class_after_the_block_is_reported(self):
        self.assertEqual(_stranded(
            'import unittest\n'
            'class A(unittest.TestCase):\n    pass\n'
            'if __name__ == "__main__":\n    unittest.main()\n'
            'class B(unittest.TestCase):\n    pass\n'
        ), ["B"])

    def test_a_class_before_the_block_is_not(self):
        self.assertEqual(_stranded(
            'import unittest\n'
            'class A(unittest.TestCase):\n    pass\n'
            'if __name__ == "__main__":\n    unittest.main()\n'
        ), [])

    def test_another_conditional_does_not_move_the_boundary(self):
        # An `if` that is not the `__main__` guard leaves what follows it
        # where it was; a text match on "__main__" would not know that.
        self.assertEqual(_stranded(
            'import os, unittest\n'
            'if os.environ.get("__main__"):\n    pass\n'
            'class A(unittest.TestCase):\n    pass\n'
        ), [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
