# Milestone 1 Acceptance Record

**Milestone:** 1 — Deterministic PostgreSQL runtime

**Disposition:** _(to be written by the repository owner: `Accepted` or `Rejected`, with a sentence of reasoning)_

**Date:** _(the date of the disposition)_

**Recorded by:** repository owner

This record satisfies the Milestone 1 acceptance gate in [Project Charter](../PROJECT_CHARTER.md) Section 9. Every gate item below is an automated assertion over registered inputs, as Charter Section 9 permits; this record names the assertion and where it runs. No item rests on a claim made only here. Drafted from the evidence that exists by Claude Code on the owner's instruction ([#64](https://github.com/OKJ1105/evidence-first-rag/issues/64)); the disposition is the owner's alone.

## Gate item 1 — Every test registered by the Milestone 1 contract passes

The two CI jobs in `.github/workflows/repository-checks.yml` run on every push and pull request:

- `repository-checks`: the fixture validator and its own tests, the Markdown link check, and `python3 -m unittest discover --start-directory tests --top-level-directory .`, which needs no database and no model SDK.
- `database-checks`: provisioning from the version-controlled DDL against a `postgres:17` service container, the data-level invariant check, and `python3 -m unittest discover --start-directory tests_database --top-level-directory .`.

Both are green on `main` at the commit this record is merged at. The [MVP Runtime Contract](../contracts/mvp-v0.1.md) Section 8 table maps each obligation to the assertion that discharges it.

## Gate item 2 — The conformance run is deterministic, has no `fail` result, and every `review` result has a recorded disposition

Contract Section 4.9 check `D1`: the runner performs two consecutive runs and the artifacts compare equal with the two irreproducible fields (`run_identifier`, `started_at`) removed. `tests_database/test_conformance_run.py` asserts it against the sixteen registered expected documents in `src/evidence_first_rag/conformance/expected/`, and the run's verdict is `pass`.

No `review` result exists to dispose of: `conformance/artifact.py` records `advisories`, and nothing in the implementation produces one — every divergence it can observe violates a check and is therefore `fail`, not `review`. The field exists so the verdict rule is the contract's three outcomes rather than two.

## Gate item 3 — A `fail` result cannot be accepted as a pass by human override

`conformance/artifact.py`: `verdict` is a property computed from the recorded checks on every read. There is no field to set, no argument to pass, and no code path from a failing check to `pass`. `tests/test_conformance_artifact.py` enumerates the ways one might try, and each is refused.

## Gate item 4 — Unsupported and contract-defined No-Go requests never reach factual SQL success

Contract Section 8.1 fixtures `FX-106` (`coverage_gap`), `FX-107` (`not_found`), `FX-108` (`unsupported`), `FX-109`, `FX-110` and `FX-112` (`invalid_request`), `FX-111` (`needs_entity_discovery`), and `FX-105` / `FX-113` (`ambiguous`), each with its registered expected document recording `connection_opened: false` where the contract requires no connection. The Section 4.10 refusal assertions in `conformance/probes.py` show the runtime identity cannot write, alter, or escalate.

## Gate item 5 — An automated data-level check confirms the loaded database satisfies the identity and scope invariants in Section 3.6

`python -m evidence_first_rag.db.invariants`, run in `database-checks` after provisioning. `tests_database/test_invariants.py` proves the check is not vacuous: it fails on a schema from which a constraint has been removed.

## Gate item 6 — The runtime identity cannot write data or change the schema

Contract Section 4.10's four refusal assertions (`INSERT`, `UPDATE`, `DELETE`, `ALTER`) as the `mvp_runtime` identity, in `conformance/probes.py` and exercised by `tests_database/test_roles.py` and `tests_database/test_conformance_run.py`. The runtime opens a `REPEATABLE READ`, read-only session (`runtime/connection.py`), and the evidence bundle records `read_only_transaction: true` on every executed outcome.

## Gate item 7 — Representative source tables remain unchanged throughout conformance execution

Contract Section 4.10 state digest: `max(xmin)` per table over the four Section 4.1 tables, taken before and after the run, equal. In `conformance/probes.py`, asserted in `tests_database/test_conformance_run.py`.

## Gate item 8 — No arbitrary SQL path exists

Three layers, each asserted:

- Contract Section 4.4 registry safeguards in `tests/test_registry.py`: unregistered template, write-keyword registration, unknown parameter, missing required parameter, and the absence of any arbitrary-SQL entry point; `tests/test_registry_surface.py` scans every production module for a way to reach the seal.
- The session port ([#50](https://github.com/OKJ1105/evidence-first-rag/pull/50)): `runtime/connection.py` executes only the object the registry itself holds under that name, by identity, so a forgery taking a registered name is refused before the driver.
- Section 4.9 check `B1` at the driver: every executed statement is byte-identical to a registered template's text, and a run with no executions cannot pass vacuously.

## Effect

- Milestone 1 is closed on the terms above. Its deferral note — the provisioning mechanism and loader clause corrected at contract `0.5.0` — is recorded in contract Section 3.4 and is not repeated here.
- Milestone 2's gate proceeds under its own record, `milestone-2.md`, when the Section 4.7 comparison has run ([#58](https://github.com/OKJ1105/evidence-first-rag/issues/58)).
