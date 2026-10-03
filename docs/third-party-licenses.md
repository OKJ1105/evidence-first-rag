# Third-party licenses

The repository's own license is in [LICENSE](../LICENSE): all rights reserved, readable but not licensed for use. This page records the licenses of what it depends on, as [Project Charter](PROJECT_CHARTER.md) Section 11 requires before a public release ("confirm dependency licenses").

## How this was read

On 2026-10-03, from the package metadata (`License-Expression`, or the `License ::` classifiers where none is given) of a virtual environment with `pip install -e ".[api,adapter]"`, which is what the [Dockerfile](../Dockerfile) installs. It names the versions that resolved that day. The deployed image resolves the same ranges at build time, so a later build can carry other versions; the licenses below did not change across the versions this project has used, as far as was checked, which is not exhaustively.

## Direct dependencies (`pyproject.toml`)

| Package | Extra | Version read | License |
| --- | --- | --- | --- |
| `psycopg[binary]` | (core) | 3.3.6 | LGPL-3.0-only |
| `fastapi` | `api` | 0.141.1 | MIT |
| `uvicorn[standard]` | `api` | 0.53.0 | BSD-3-Clause |
| `httpx` | `api` | 0.28.1 | BSD-3-Clause |
| `mcp` | `api` | 2.2.0 | MIT |
| `anthropic` | `adapter` | 1.7.0 | MIT |

## Everything else the same environment installed

MIT or MIT-0: `annotated-doc`, `annotated-types`, `anyio`, `attrs`, `cffi`, `docstring_parser`, `h11`, `httptools`, `jiter`, `jsonschema`, `jsonschema-specifications`, `mcp-types`, `pydantic`, `pydantic_core`, `pyjwt`, `pyyaml`, `referencing`, `rpds-py`, `truststore`, `watchfiles`.

BSD-3-Clause: `click`, `httpcore`, `httpcore2`, `httpx2`, `idna`, `pycparser`, `python-dotenv`, `sse-starlette`, `starlette`, `websockets`.

Apache-2.0: `opentelemetry-api`, `python-multipart`. Dual: `cryptography` (Apache-2.0 or BSD-3-Clause), `uvloop` (Apache-2.0 and MIT), `sniffio` (MIT or Apache-2.0).

Other: `certifi` (MPL-2.0), `psycopg-binary` (LGPL-3.0-only), `typing_extensions` (PSF-2.0).

## Notes

- **`psycopg` is LGPL-3.0.** This repository uses it unmodified, as a separately installed library, and does not copy its code. The LGPL's obligations attach to distributing the library; this repository distributes none, and the deployed image is pushed only to the project's own private registry. If an image or bundle containing it is ever distributed, the LGPL's conditions for that distribution have to be met then. `psycopg-binary` also bundles `libpq` and the libraries it links; their licenses travel with that wheel.
- **`certifi` is MPL-2.0**, used unmodified.
- **The runtime image** is built `FROM python:3.11-slim` (Debian, with the Python Software Foundation License for CPython). It is not published.
- **The page under `ui/`** uses no third-party JavaScript. The agent scripts under `scripts/agent/` import only Node built-ins and each other, and declare no npm dependencies.
- **GitHub Actions** referenced by the workflows, and the Claude Code CLI the agent loop installs on its runner, are tools run on GitHub's runners. They are not part of what this repository distributes.
- This page is a record of what was read, not legal advice.
