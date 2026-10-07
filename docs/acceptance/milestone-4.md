# Milestone 4 Acceptance Record

**Milestone:** 4 — End-to-end workflow and export

**Disposition:** Accepted

**Date:** 2026-10-07

**Recorded by:** the Claude Code writer session, at the repository owner's direction on 2026-10-07. The owner accepted this milestone with the limits stated under "What this record does not claim".

This record collects the evidence for the Milestone 4 acceptance gate in [Project Charter](../PROJECT_CHARTER.md) Section 9. For each gate item it names the evidence that exists and where that evidence runs: an automated assertion over registered inputs, or a recorded human decision. Claude Code, the writer session, drafted it from that evidence. **The disposition is the owner's alone.**

Unlike Milestones 2 and 3, Milestone 4 has no single judged run. Its gate items are checked by the repository's standing CI jobs. On every pull request, those jobs run the registered workflow fixtures of [`api-v0.1`](../contracts/api-v0.1.md) Section 8.1 (`WF-001` to `WF-025`) and the equality cases of [`mcp-v0.1`](../contracts/mcp-v0.1.md) (`MC-001` to `MC-025`).

## The deliverables

| Charter deliverable | Where it stands |
| --- | --- |
| Stable API flow from request or candidate selection to evidence-backed result | `api-v0.1` Sections 4.1 to 4.5, served by FastAPI ([ADR-0003](../adr/0003-fastapi-for-the-http-surface.md), #178). `mcp-v0.1` serves the same results as tools ([ADR-0004](../adr/0004-mcp-surface-and-the-tool-result-boundary.md)). |
| TSV export with a frozen column contract | **Moved out of scope** by ADR-0004 item 6 (Path B, decided by the owner on [#169](https://github.com/OKJ1105/evidence-first-rag/issues/169#issuecomment-5775122804)). It returns when a measured need exists. |
| End-to-end task fixtures | `api-v0.1` Section 8.1 `WF-*` and `mcp-v0.1` `MC-*`. |
| Minimal UI only if it materially supports evaluation or use | `ui/index.html` and `ui/view.mjs`. On 2026-09-16 the owner decided on #169, as decision C, that the UI be built ([comment](https://github.com/OKJ1105/evidence-first-rag/issues/169#issuecomment-5691031628)). See Gate item 2 for what this record does and does not carry of that decision. |

## Gate item 1 — Exported values are derived from the normalized runtime result

**Closed with its deliverable, not met and not failed.** `api-v0.1` Section 8 assigns this item (`G1`) to `export-v0.1`. That contract is not in this tree, and no route serves it. Path B moved the export out of Milestone 4. ADR-0004's Consequences therefore close the gate item with its deliverable. ADR-0004 also says this record cites the ADR for the item rather than recording a fail. Restoring the export restores the gate item. The Charter Section 9 text already carries the parenthetical that says so.

## Gate item 2 — Rendering does not add or alter facts

`api-v0.1` Section 4.6 registers seven presentation obligations, and Section 8 names `G2`'s evidence (row "Section 4.6 presentation"). The evidence is in `ui/view.test.mjs`, which has one `describe` block per obligation:

- **E1:** a test that every value the page shows as a fact is present in `result` or `rendered` (`mvp-v0.1` Section 4.9 Group E check E1, applied to the UI).
- **Candidate order:** candidates are rendered in rank order, with none omitted and nothing selected before an act.
- **Selection:** `/v1/select` is not sent without an act that names a rank (`maySend`).
- **Prefill:** the obligation-4 prefill tests.

Its fixtures are `tests/ui_envelopes.json`, checked by `tests/test_ui_envelopes.py`. CI runs the tests in the `repository-checks` job (`node --test … "ui/*.test.mjs"`).

The row also requires the recorded human decision C on #169, cited here "with the owner's stated reason". The decision is cited above: on 2026-09-16 the owner decided that the UI be built. **This record does not carry the owner's stated reason.** No artifact in this repository restates one, and the writer session cannot read #169 to restate it. Until the owner supplies the reason at disposition, or records that decision C gave none, the human half of `G2` is not discharged in this record's own text. **Since then, the owner's use of the page produced a fail, recorded on [#195](https://github.com/OKJ1105/evidence-first-rag/issues/195#issuecomment-5775152505) on 2026-09-22.** The page's form required `entity_kind` and the scope dimensions before a person had any reason to know them. ADR-0004 followed from that fail. The README now points a reader at the chat page and the MCP server first, and the page stays as a secondary surface. The fail is about usability, not about facts. No `G2` assertion failed. It does bear on decision C: that decision is the record that the UI materially supports use, and #195 records that a person could not use the form unaided. Whether decision C still discharges the human half of `G2` after #195, or whether the chat page and MCP server now carry that half, is the owner's to say at disposition.

## Gate item 3 — Representative workflows complete end to end with traceable failures

`api-v0.1` Section 8.1 registers `WF-001` to `WF-025`. `WF-003` is the whole target path: a request that needs entity discovery, then discovery, a selection naming one rank, and a fact carrying its selection record. The result/refusal boundary is `WF-016` to `WF-018` and `WF-022`. Every refusal carries exactly two keys, and every status family is reached by at least one registered case. That makes a failure traceable to the status or refusal kind it produced.

| Where | What runs | CI job |
| --- | --- | --- |
| `tests/test_api_surface.py` | every `WF-*` against an injected runtime | `adapter-checks`, which installs the `api` extra. `repository-checks` installs nothing, so it imports the module and skips these tests. |
| `tests_database/test_api_workflows.py` | the `WF-*` rows against a real PostgreSQL. The `WF-003` path is `test_the_three_steps_reach_a_fact_carrying_its_selection`. | `database-checks` |
| `tests_stack/test_workflows.py` | the rows over HTTP against the running local stack (Section 4.7) | `local-stack` |
| `tests/test_mcp_surface.py`, `tests_stack/test_mcp_rows.py` | `MC-*`, each the `/v1` result as a tool result. `MC-003` is `WF-003` as three tools. | `tests/test_mcp_surface.py` in `adapter-checks` (`mcp` is in the `api` extra; `repository-checks` skips it). `tests_stack/test_mcp_rows.py` in `local-stack`. |

The deployed environment runs the WF and MC rows that need no model, as `deploy-v0.1` Section 4.8's `WF/MC` group. See [the Milestone 5 records](milestone-5/README.md).

Decision D on #169 (the local stack, "as recommended") is cited from the same comment as decision C.

## What this record does not claim

- **The stack does not run three of `WF-001` to `WF-015`.** `WF-007`, `WF-008` and `WF-009` each drive `/v1/ask` with an *injected* proposal, and a stack has no way to inject one. They run in `tests/test_api_surface.py`, not against the stack. [#193](https://github.com/OKJ1105/evidence-first-rag/issues/193), which is still open, holds this reading of the "Section 4.7 local stack" row. ADR-0004 asks this record to state it. `/v1/ask` has since been retired from the documented path ([#203](https://github.com/OKJ1105/evidence-first-rag/issues/203)).
- **`WF-016` and `WF-017` do not run against the stack either.** The same row says they "inject a fault and run against it separately". No test in this tree does that: `tests_stack/` only quotes the row, and the `local-stack` job runs `tests_stack` alone. `WF-016` (an unreachable database) runs in `tests/test_api_surface.py` and, against PostgreSQL, in `tests_database/test_api_workflows.py` by pointing the client at a closed port. `WF-017` (an injected `statement_timeout`) runs only in `tests/test_api_surface.py`; `tests_database/test_api_workflows.py` excludes it as an injection. A stack started by `docker compose up` has a reachable database and no hook for injecting a fault, so neither row has stack evidence. This record does not know whether #193 covers these two rows; the owner's disposition has to account for them alongside `WF-007` to `WF-009`.
- **No judged run artifact.** The gate rests on CI jobs that run on every pull request, not on one committed run. A reader checks it by running those jobs, or by reading their latest result on `main`.
- **ADR-0003's and ADR-0004's status lines still read `Proposed`.** The owner adopted both, by merge and by the #169 decisions. This repository's ADR status lines have not been moved on merge; `deploy-v0.1` Section 2 states the same for ADR-0005.
- **Model prose is outside the gate.** Text that a host model writes beyond the tool boundary is outside `G2`, by ADR-0004 item 3 and ADR-0005.

## Effect

- `api-v0.1` Section 8's row "The #169 decision point on export" was discharged by ADR-0004 (Path B), as that ADR records.
- Once the owner records a disposition here, Milestone 4 closes. ADR-0004 says it closes "on the acceptance record".
