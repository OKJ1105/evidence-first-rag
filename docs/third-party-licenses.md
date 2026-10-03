# Third-party licenses

The repository's own license is in [LICENSE](../LICENSE): all rights reserved, readable but not licensed for use. This page records the licenses of what it depends on, as [Project Charter](PROJECT_CHARTER.md) Section 11 requires before a public release ("confirm dependency licenses").

## How this was read

On 2026-10-03, in a fresh virtual environment (CPython 3.11, the Dockerfile's base) after `pip install -e ".[api,adapter]"`, which is what the [Dockerfile](../Dockerfile) installs. Each license below is that package's `License-Expression` metadata, or its `License ::` classifiers where it declares no expression, read with `importlib.metadata` by [`scripts/third_party_licenses.py`](../scripts/third_party_licenses.py), whose docstring gives the commands that regenerate the table. The table is the complete list of what that install put in the environment, less `pip`, `setuptools` and this project itself. It names the versions that resolved that day; the deployed image resolves the same ranges when it is built, so a later build can carry other versions.

`distro`, `httpx-sse` and `pydantic-settings`, which earlier releases of `anthropic` and `mcp` required, were not in the environment that day.

The direct dependencies (`pyproject.toml`) are `psycopg[binary]` (core); `fastapi`, `uvicorn[standard]`, `httpx` and `mcp` (extra `api`); and `anthropic` (extra `adapter`). Everything else in the table is pulled in by them.

| Package | Version | License, as declared |
| --- | --- | --- |
| `annotated-doc` | 0.0.5 | MIT |
| `annotated-types` | 0.8.0 | MIT |
| `anthropic` | 1.11.0 | MIT License |
| `anyio` | 4.15.1 | MIT |
| `attrs` | 26.1.0 | MIT |
| `certifi` | 2026.7.22 | Mozilla Public License 2.0 (MPL 2.0) |
| `cffi` | 2.1.1 | MIT-0 |
| `click` | 8.5.0 | BSD-3-Clause |
| `cryptography` | 50.0.2 | Apache-2.0 OR BSD-3-Clause |
| `docstring_parser` | 0.18.0 | MIT License |
| `fastapi` | 0.142.2 | MIT |
| `h11` | 0.16.0 | MIT License |
| `httpcore` | 1.0.9 | BSD-3-Clause |
| `httpcore2` | 2.13.1 | BSD-3-Clause |
| `httptools` | 0.8.0 | MIT |
| `httpx` | 0.28.1 | BSD License |
| `httpx2` | 2.13.1 | BSD-3-Clause |
| `idna` | 3.20 | BSD-3-Clause |
| `jiter` | 0.17.0 | MIT |
| `jsonschema` | 4.26.0 | MIT |
| `jsonschema-specifications` | 2025.9.1 | MIT |
| `mcp` | 2.3.0 | MIT License |
| `mcp-types` | 2.3.0 | MIT License |
| `opentelemetry-api` | 1.45.0 | Apache-2.0 |
| `psycopg` | 3.3.6 | LGPL-3.0-only |
| `psycopg-binary` | 3.3.6 | LGPL-3.0-only |
| `pycparser` | 3.0 | BSD-3-Clause |
| `pydantic` | 2.13.5 | MIT |
| `pydantic_core` | 2.46.5 | MIT |
| `pyjwt` | 2.15.1 | MIT |
| `python-dotenv` | 1.2.4 | BSD-3-Clause |
| `python-multipart` | 0.0.32 | Apache-2.0 |
| `pyyaml` | 6.0.3 | MIT License |
| `referencing` | 0.37.0 | MIT |
| `rpds-py` | 2026.6.3 | MIT |
| `sniffio` | 1.3.1 | MIT License; Apache Software License |
| `sse-starlette` | 3.5.0 | BSD-3-Clause |
| `starlette` | 1.7.0 | BSD-3-Clause |
| `truststore` | 0.10.4 | MIT |
| `typing-inspection` | 0.4.4 | MIT |
| `typing_extensions` | 4.16.0 | PSF-2.0 |
| `uvicorn` | 0.54.0 | BSD-3-Clause |
| `uvloop` | 0.23.0 | Apache Software License; MIT License |
| `watchfiles` | 1.3.0 | MIT License |
| `websockets` | 17.1 | BSD-3-Clause |

## Notes

- **This project's own packaging metadata** carries the classifier `License :: Other/Proprietary License`, and a built wheel carries `LICENSE` under `dist-info/licenses/`, by setuptools' default patterns.

- **`psycopg` is LGPL-3.0.** This repository uses it unmodified, as a separately installed library, and does not copy its code. The LGPL's obligations attach to distributing the library; this repository distributes none, and the deployed image is pushed only to the project's own private registry. If an image or bundle containing it is ever distributed, the LGPL's conditions for that distribution have to be met then. `psycopg-binary` also bundles `libpq` and the libraries it links; their licenses travel with that wheel.
- **`certifi` is MPL-2.0**, used unmodified.
- **The runtime image** is built `FROM python:3.11-slim` (Debian, with the Python Software Foundation License for CPython). It is not published.
- **The page under `ui/`** uses no third-party JavaScript. The agent scripts under `scripts/agent/` import only Node built-ins and each other, and declare no npm dependencies.
- **GitHub Actions** referenced by the workflows, and the Claude Code CLI the agent loop installs on its runner, are tools run on GitHub's runners. They are not part of what this repository distributes.
- This page is a record of what was read, not legal advice.
