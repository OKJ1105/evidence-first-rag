"""Print the third-party license table in docs/third-party-licenses.md.

Run inside a fresh virtual environment after `pip install -e ".[api,adapter]"`,
which is what the Dockerfile installs:

    python3 -m venv /tmp/licenses
    /tmp/licenses/bin/pip install -e ".[api,adapter]"
    /tmp/licenses/bin/python scripts/third_party_licenses.py

Every installed distribution is listed except the installer's own (`pip`,
`setuptools`) and this project. A license is the distribution's
`License-Expression` metadata, or its `License ::` classifiers where it
declares no expression, or the first line of its `License` field where it has
neither.
"""

import importlib.metadata
import sys

SKIPPED = {"pip", "setuptools", "evidence-first-rag"}


def declared_license(metadata) -> str:
    expression = metadata.get("License-Expression")
    if expression:
        return expression
    classifiers = [
        value.split("::")[-1].strip()
        for value in metadata.get_all("Classifier") or []
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    first_line = (metadata.get("License") or "").strip().splitlines()[:1]
    return first_line[0][:60] if first_line else "(none declared)"


def rows(distributions):
    found = {}
    for distribution in distributions:
        metadata = distribution.metadata
        name = metadata["Name"].lower()
        if name not in SKIPPED:
            found[name] = (distribution.version, declared_license(metadata))
    return [f"| `{name}` | {version} | {license} |" for name, (version, license) in sorted(found.items())]


def main() -> int:
    print("| Package | Version | License, as declared |")
    print("| --- | --- | --- |")
    for row in rows(importlib.metadata.distributions()):
        print(row)
    return 0


if __name__ == "__main__":
    sys.exit(main())
