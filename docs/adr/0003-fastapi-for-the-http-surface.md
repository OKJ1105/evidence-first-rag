# ADR-0003: FastAPI for the HTTP Surface

**Status:** Proposed. Recorded by the writer session with the Milestone 4 surface slice ([#178](https://github.com/OKJ1105/evidence-first-rag/issues/178)); the repository owner's disposition is the acceptance.

**Date:** 2026-09-17

## Context

[api-v0.1](../contracts/api-v0.1.md) Section 3.2 leaves the server library unfixed on purpose: it fixes an API under `/v1` and says nothing about how a process serves it. So the choice is an implementation decision, and it is recorded here rather than in a commit message because it is the first dependency added to the runtime path since psycopg, and because [Project Charter](../PROJECT_CHARTER.md) Section 3.7 fixes the deployment target that has to run it.

Three candidates were considered: Python's standard-library `http.server`, a WSGI application behind Gunicorn with no framework, and FastAPI behind Uvicorn.

Two facts about this repository bear on the choice more than the usual comparisons do.

**The default install has one runtime dependency.** `pyproject.toml` declares psycopg and nothing else, and the model SDK is an *extra* precisely so that `pip install evidence-first-rag` gives a system that answers questions with no SDK present. Any web framework added as a dependency would end that; added as an extra, it does not.

**This contract forbids most of what a web framework supplies.** Section 4.1 says the surface "has no allowlist of its own". Section 4.2 fixes the response envelope at four keys and calls a fifth "a defect". Section 4.5 fixes six refusal kinds, their HTTP codes, and a body of exactly two keys. A framework's automatic validation errors, automatic exception responses and automatic serialization are each the wrong shape here.

## Decision

**FastAPI behind Uvicorn, installed through a `[api]` extra, used as a router and a body parser and as nothing else.**

- The extra keeps the default install at one runtime dependency, the same way `[adapter]` keeps the model SDK off it.
- Pydantic models express Section 4.4's request-body rule — exactly the keys the route names, each of the stated type — which is the surface's one refusal. `extra="forbid"` is the extra-key clause; the non-string clause is the `str` annotation itself, which Pydantic 2 enforces in either mode, and `strict=True` is kept as a pin against a future release that relaxed it rather than as the thing producing the refusal today. This is the framework expressing the check the contract requires, not adding one it forbids.
- **Both of FastAPI's default error responses are replaced.** A body failing Section 4.4 leaves as 400 `malformed_request`, not 422 with a list-valued `detail`; an unknown path under `/v1` leaves as 404 `unknown_route`. A catch-all handler covers what neither names — a driver condition `runtime/connection.py` does not wrap, or a defect in the surface — because otherwise the framework answers with a plain-text 500 carrying neither a result nor a refusal. With it, every non-200 response is written by one function.
- **No response body is serialized by the framework.** Section 6 requires two identical requests to produce identical bytes, which is a claim about an escape set and a key order that no library default supplies, so every body is written by `api.serialize.dumps`.
- `/docs` and `/openapi.json` are served. Section 4.5 bounds `unknown_route` to `/v1` and says this contract "says nothing" about a path outside it, so they are permitted — and a reader can then see the route surface without reading the contract.
- Milestone 5 runs the same application under `gunicorn -k uvicorn.workers.UvicornWorker`, which is the ordinary Python startup on Azure App Service.

## Alternatives considered

**Python's standard-library `http.server`.** Adds no dependency at all, and was the writer's first recommendation. Rejected: its own documentation says it is not for production, it is not the standard startup path on the Charter Section 3.7 target, and it would mean hand-writing path dispatch, body reading and response writing — roughly twice the code, in exactly the places where a hand-written HTTP layer goes wrong.

**A bare WSGI application behind Gunicorn.** Keeps the dependency count at one, removes every framework default there is to fight, and is the standard App Service startup. Rejected on a ground outside the code: this repository is a portfolio, and its purpose is served by a surface a reader recognises. WSGI is an interface rather than a framework, and "wrote a WSGI application" communicates less than the thing every Python API job advertisement names. The technical case was close; the purpose broke the tie, and recording that openly is better than dressing it up as an engineering result.

## Consequences

- One extra, `[api]`, carrying `fastapi`, `uvicorn` and `httpx`. The default install is unchanged and the driver-free test suite still runs from a clean checkout.
- `tests/test_api_surface.py` skips when the extra is absent, so the `adapter-checks` CI job installs `.[adapter,api]`. Without that the whole suite would be a green skip — the failure [#101](https://github.com/OKJ1105/evidence-first-rag/issues/101) put that job in the tree to prevent.
- **`tests_database/test_api_workflows.py` needs the same extra in the `database-checks` job**, which therefore installs `-e ".[api]"` rather than `-e .`. Both install lines are recorded owner decisions — the first on [#178](https://github.com/OKJ1105/evidence-first-rag/issues/178), the second on [#179](https://github.com/OKJ1105/evidence-first-rag/pull/179) — because `.github/` is outside what a writer session changes on its own. Without the second, the registered `FX-*` and `DX-*` half of Section 8.1, `WF-003` included, would have been a green skip standing in for evidence. **That hazard is now closed rather than only described**: `tests_database/guards.py` makes `tests_database/test_api_workflows.py` fail, naming this workflow file, when the extra is missing in a job that provisioned a database — so removing the line is loud rather than silent.
- The framework's defaults are a standing hazard rather than a one-time cost: a route added later that returns a dict, or an `HTTPException` raised without a handler, would emit a body this contract does not admit. `tests/test_api_surface.py` asserts that no response carries a list-valued `detail` and that every body equals `dumps` of its own document, so a regression of that kind fails rather than ships.
- The surface's dependency is on FastAPI's routing and Pydantic's model validation. Neither the framework's serialization nor its error handling is relied on, so replacing it later is a change to one module.
