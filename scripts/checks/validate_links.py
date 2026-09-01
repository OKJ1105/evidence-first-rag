"""Validate local Markdown links.

Shared by CI (.github/workflows/repository-checks.yml) and the agent loop
(.github/agent-checks.json) so both verify the same thing with the same code.
Exits 1 and lists every broken link when any local target does not exist.
"""

import pathlib
import re
import sys
import urllib.parse

fence = re.compile(r"(?ms)^```.*?^```\s*$")
link = re.compile(r"\[[^\]]+\]\(([^)]+)\)")


def main() -> int:
    failures = []
    for document in pathlib.Path(".").rglob("*.md"):
        if ".git" in document.parts or "node_modules" in document.parts:
            continue
        text = fence.sub("", document.read_text(encoding="utf-8"))
        for match in link.finditer(text):
            raw_target = match.group(1).strip()
            if raw_target.startswith("<") and ">" in raw_target:
                raw_target = raw_target[1 : raw_target.index(">")]
            else:
                raw_target = raw_target.split(maxsplit=1)[0]
            target = urllib.parse.unquote(raw_target.split("#", 1)[0])
            if not target or urllib.parse.urlparse(target).scheme:
                continue
            resolved = (document.parent / target).resolve()
            if not resolved.exists():
                failures.append(f"{document}: {raw_target}")

    if failures:
        print("Broken local Markdown links:")
        print("\n".join(failures))
        return 1

    print("Local Markdown links: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
