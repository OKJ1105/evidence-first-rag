"""`api-v0.1` Section 4.7: the surface, built from the environment.

Everything else in `api/` takes its collaborators as arguments, which is what
lets `tests/` drive the whole surface over fakes and `tests_database/` drive it
over the registered data. **This module is the one place that reads an
environment**, so that a process can start without a test writing the wiring
for it, and it is deliberately small: it decides three things and nothing else.

1. **The connection is the runtime identity's.** Section 4.7 says the surface
   process "never holds the provisioning credentials", and `mvp-v0.1` Section
   4.3 gives the runtime identity read-only grants. That separation is what
   makes "the database refuses writes" a property of the deployment rather than
   of this code's good intentions, so the role name is fixed here rather than
   read from the environment: a deployment that wanted to run the surface as
   the provisioning identity would have to change this file, in a pull request,
   rather than change a variable.

   `MVP_PROVISIONING_PASSWORD` is not read here, and
   `tests/test_api_serve.py` asserts that this module never names it.

2. **The adapter is optional.** Section 4.7: "The adapter credential is read
   from the environment and is optional; absent, `/v1/ask` refuses per Section
   4.5 and every other route works." Absent means either no credential or no
   `[adapter]` extra installed, and both leave `proposer` as `None`, which
   Section 4.5 turns into `adapter_unavailable` on `/v1/ask` alone. A stack
   that would not start without a model key would make the LLM a dependency of
   a system built not to need one.

3. **Provenance is the committed fixture paths.** They are recorded on every
   trace and never discovered (`mvp-v0.1` Section 4.7), so they are a constant
   of this repository, listed once here.

No password is logged, and none is passed on a command line: psycopg reads the
one this builds from the mapping, and the adapter's SDK resolves its own.
"""

import os

from ..runtime.connection import PsycopgDatabase
from .app import SurfaceProposer, create_app, services
from .request_log import RequestLog, configure_logging

# `mvp-v0.1` Section 4.3's read-only identity. Fixed, not configurable -- see
# the module docstring.
RUNTIME_ROLE = "mvp_runtime"

DEFAULT_DATABASE = "mvp"

# The environment variable the surface reads for the runtime identity's
# password. Named here so the test that forbids the provisioning one has
# something to compare against.
RUNTIME_PASSWORD_VARIABLE = "MVP_RUNTIME_PASSWORD"

# The files the fixtures were loaded from, recorded on every `source_trace`.
# `mvp-v0.1` Section 4.7 makes this the caller's to state rather than the
# runtime's to discover, and for this repository it is these six.
FIXTURE_PROVENANCE = (
    "fixtures/source_snapshot.jsonl",
    "fixtures/message_occurrence.jsonl",
    "fixtures/signal_occurrence.jsonl",
    "fixtures/signal_mapping.jsonl",
    "fixtures/registry/approved_entity.jsonl",
    "fixtures/registry/approved_alias.jsonl",
)


def connection_parameters(environment=None) -> dict:
    """The runtime identity's connection, from the environment.

    The password is required: a surface that started without one would fail
    every request with `database_unavailable`, which reports a database
    condition for a deployment mistake. Failing here names the variable.
    """
    environment = os.environ if environment is None else environment
    return {
        "dbname": environment.get("MVP_DATABASE", DEFAULT_DATABASE),
        "user": RUNTIME_ROLE,
        "password": environment[RUNTIME_PASSWORD_VARIABLE],
        "host": environment.get("PGHOST"),
        "port": environment.get("PGPORT"),
    }


def proposer(environment=None):
    """A proposer, or `None` where the credential or the extra is absent.

    Returning `None` is not a failure path: it is Section 4.7's optional
    adapter, and Section 4.5 answers `/v1/ask` with `adapter_unavailable` for
    it while the other four routes work.
    """
    environment = os.environ if environment is None else environment
    if not environment.get("ANTHROPIC_API_KEY"):
        return None
    try:
        from ..adapter.client import Adapter
    except ImportError:  # pragma: no cover - exercised by the extra-free job
        return None
    return SurfaceProposer(adapter=Adapter.from_environment())


def build(environment=None):
    """The Section 4.1 surface and the Section 4.6 page, over a real database."""
    environment = os.environ if environment is None else environment
    # `deploy-v0.1` Section 4.7: one JSON line per request, outermost (#259).
    configure_logging()
    # `api-v0.1` Section 4.5 (`0.2.0`): the one origin a preflight is admitted
    # from. Unset in the Section 4.7 stack, so none is.
    return RequestLog(
        create_app(
            services(
                PsycopgDatabase(connection_parameters=connection_parameters(environment)),
                fixture_provenance=FIXTURE_PROVENANCE,
                proposer=proposer(environment),
            ),
            cors_origin=environment.get("EFR_CORS_ORIGIN") or None,
        )
    )


# `build` is the server's entry point, called rather than imported:
#
#     uvicorn --factory evidence_first_rag.api.serve:build
#
# A module-level `app = build()` would read the environment as a side effect of
# importing this file, so a test that wanted to check one of the three
# decisions above would have to satisfy all of them first. The factory keeps
# the reading inside a call.
#
# Nothing here opens a connection: `PsycopgDatabase` opens one per request, so
# a surface built against an unreachable database starts, and the first request
# answers `database_unavailable` -- Section 4.5's answer for exactly that,
# rather than a process that will not start.
