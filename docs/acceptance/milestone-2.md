# Milestone 2 Acceptance Record

**Milestone:** 2 — Thin LLM Adapter

**Disposition:** _not yet recorded — the repository owner writes this line ([#58](https://github.com/OKJ1105/evidence-first-rag/issues/58))_

**Date:** _with the disposition_

**Recorded by:** repository owner

This record is drafted against the Milestone 2 acceptance gate in [Project Charter](../PROJECT_CHARTER.md) Section 9. Every gate item below names the evidence that exists — an automated assertion over registered inputs, or a field of the committed comparison artifact — and where it runs. No item rests on a claim made only here. Drafted from that evidence by Claude Code on the owner's instruction ([#58](https://github.com/OKJ1105/evidence-first-rag/issues/58), [#91](https://github.com/OKJ1105/evidence-first-rag/issues/91)); the disposition is the owner's alone, and a judged artifact that had not cleared the bar would have produced a Rejected record with the same care.

## The comparison this record rests on

[MVP Runtime Contract](../contracts/mvp-v0.1.md) Section 4.7 comparison, Section 8.3 thresholds and evaluation set, contract version `0.6.0`.

| | |
| --- | --- |
| Committed artifact | [`milestone-2/comparison.json`](milestone-2/comparison.json) |
| `run_identifier` | `cbe70f96-2209-4f1a-8823-1a27dceda627` |
| `started_at` | `2026-09-10T14:48:58Z` |
| Actions run | [34491474440](https://github.com/OKJ1105/evidence-first-rag/actions/runs/34491474440), head `392b5b7`, `workflow_dispatch` of `.github/workflows/milestone-2-comparison.yml` |
| Thresholds judged against | `task_coverage ≥ 0.90`, `false_resolution ≤ 0.00`, no weakened negative; `registered_at 2026-09-07T09:32:37Z` (Section 8.3, [#52](https://github.com/OKJ1105/evidence-first-rag/issues/52)) |
| Adapter | `task_coverage 1.0000` (48 of 48), `false_resolution 0.0000` (0 of 48), `weakened_negatives: []` |
| Baseline (Section 4.7 control) | `task_coverage 0.4583` (22 of 48), `false_resolution 0.0000`, `weakened_negatives: []` |
| `judgement` | `judged: true`, `adoptable: true`, `reasons: []` |

The committed file is the main document the run wrote, taken from the job log where `adapter/run.py` prints it after the summary byte for byte ([#117](https://github.com/OKJ1105/evidence-first-rag/issues/117)); the same document is the run's `milestone-2-comparison` Actions artifact. The run's raw per-call record is an Actions artifact only and is not committed, for the reasons `adapter/run.py` records. Every identifier in the committed file is a `SAMPLE_*` value; the pull request that carries this record was read for that by hand, which `adapter/run.py` names as the only guard there is.

**Every case is correct.** 48 of 48, including the one case the preceding run on this evaluation set missed (`EV-D-1`, "What messages are defined in …?"), which the independent review of [#121](https://github.com/OKJ1105/evidence-first-rag/pull/121) traced to one clause of the instruction text and whose repair is the head this run measured.

**Stability.** A model is not deterministic across runs, and the 0.00 false-resolution bar admits no false resolution, so a second run on the same head was dispatched as a check before this record was drafted: RUN7_PLACEHOLDER. The committed artifact is the first of the two; the second is cited by its Actions run for the reader who wants it.

**What the run measured.** The adapter as it stands on `main` after [#112](https://github.com/OKJ1105/evidence-first-rag/pull/112) (argument schema as a `[{name, value}]` list, [#111](https://github.com/OKJ1105/evidence-first-rag/issues/111)), [#118](https://github.com/OKJ1105/evidence-first-rag/pull/118) (log print, [#117](https://github.com/OKJ1105/evidence-first-rag/issues/117)) and [#121](https://github.com/OKJ1105/evidence-first-rag/pull/121) (the contradiction, operation and missing-key rules in the instructions, [#120](https://github.com/OKJ1105/evidence-first-rag/issues/120)); the artifact's `prompt_digest` and `schema_digest` are the digests of that text and schema, and gate item 7 says how to check them. The two earlier runs on this evaluation set (`d2f08cb8`, [#91](https://github.com/OKJ1105/evidence-first-rag/issues/91)) scored `0.1667` and are superseded: their argument schema locked three names out, which [#91](https://github.com/OKJ1105/evidence-first-rag/issues/91) records with an independent adjudication and the owner's dispositions.

## Gate item 1 — Adapter output can invoke only approved contracts

The output schema's `route` is a closed enum of the three Section 4.5 names plus the literal `unsupported` (`adapter/vocabulary.py` `schema()`, asserted by `tests/test_adapter_vocabulary.py`), so a fourth name cannot be returned. Behind the schema, deterministic revalidation checks the route name against the registry before any database access: Section 8.1 `FX-108`, `tests/test_adapter_revalidation.py` `test_fx_108_a_request_outside_the_three_routes`, with `producing_layer` recorded. The adapter selects no template and writes no SQL; the runtime executes only the registry's own template object under a registered name (Milestone 1 record, gate item 8).

## Gate item 2 — Explicit canonical entity references are preserved rather than rewritten

Every argument value must appear verbatim in the request text as a whole token — byte-exact, not a substring, not a prefix: `adapter/revalidation.py` `_values_come_from_the_request` and `_is_verbatim_token`; Section 8.1 `FX-112`, `tests/test_adapter_revalidation.py` `test_fx_112_an_argument_value_absent_from_the_request`, `test_a_rewrite_is_not_an_extraction`, `test_a_prefix_of_a_real_identifier_is_not_an_extraction`. In the artifact, every accepted outcome's `proposed_arguments` contains only values present in its case text; the 33 `P` outcomes are all `correct: true`, which by Section 8.3's definition means the argument mapping equals the registered one.

## Gate item 3 — Missing identifiers or scope do not become fabricated values

`FX-111` (route determined, no canonical reference formable → `needs_entity_discovery`) and `FX-112` (invented value → `invalid_request`), `tests/test_adapter_revalidation.py` `test_fx_111_…` and `test_fx_112_…`; the instructions say to leave an absent value out and never to invent an identifier (`adapter/vocabulary.py` `instructions()`). In the artifact, the four `D` outcomes carry only the four scope arguments in `proposed_arguments` and no lookup key, and each refusal's `refused_as` is `needs_entity_discovery` with a `refusal_detail` naming the absent key; no outcome in any family carries a value absent from its request.

## Gate item 4 — Every `needs_entity_discovery` result remains terminal, never reaching execution

`FX-111` with no connection opened: `tests/test_adapter_revalidation.py` `test_fx_111_a_route_with_no_canonical_reference_formable` and `test_every_one_of_them_opens_no_connection`; `runtime/request.py` raises the refusal before `runtime/service.py` is reached. In the artifact, all four `D` outcomes (`EV-D-1` to `EV-D-4`) are `status: needs_entity_discovery` with `refused_as: needs_entity_discovery` and a `limitations` entry of kind `entity_discovery_not_implemented` stating that the outcome is terminal. Milestone 3 is not opened by this record; contract Section 9 still defers Entity Discovery.

## Gate item 5 — At least one scope-complete `executable` case runs end to end through the deterministic runtime

The artifact's `report.executed_against_a_database` is `true`, and `judge` refuses a run that did not execute (`adapter/comparison.py`). Eighteen `P` outcomes are `status: success`; the first, `EV-P-FX-001-0` (message facts for `SAMPLE_MSG_ENGINE_STATUS` under a complete `SAMPLE_PROJECT_ALPHA` / `SAMPLE_REV_A` / `SAMPLE_NET_POWERTRAIN` / `SAMPLE_SNAP_BASE` scope), is named here as the gate requires. The remaining fifteen `P` outcomes are the registered non-`success` statuses of their Section 8.1 cases (`FX-103`, `FX-105`, `FX-106`, `FX-107`, `FX-113`), each observed as registered.

## Gate item 6 — Compared with the baseline on the same frozen set, adopted only against pre-registered thresholds without weakening negatives

The table above. `registered_at 2026-09-07T09:32:37Z` precedes `started_at 2026-09-10T14:48:58Z`, which is the order Charter Section 9 and contract Section 8.3 require; `judge` marks a run `not_judged` otherwise (`tests/test_adapter_run.py` `test_thresholds_registered_after_the_run_leave_it_unjudged_and_exit_2`). Adapter and baseline ran the same 48 cases in the same process against the same provisioned database. `weakened_negatives: []` — no case registering a non-`success` status was observed as `success`. The bar is the one registered on [#52](https://github.com/OKJ1105/evidence-first-rag/issues/52) and written into Section 8.3 at `0.6.0`; nothing in the comparison harness can adopt (`adapter/run.py` never prints "adopt"), and this record is the recorded human decision Section 8.2 defers to the gate.

## Gate item 7 — Model and decoding configuration pinned by the evaluation contract; a material change reopens this gate

Artifact `model: claude-opus-5` and `decoding: {"model": "claude-opus-5", "max_tokens": 4096, "output_config": {"effort": "low"}, "thinking": {"type": "adaptive"}}` equal the pin in `adapter/client.py` `MODEL` / `DECODING` (`tests/test_adapter_client.py`), which Section 4.6 pins; `judge` compares the artifact's decoding with the pinned configuration (`tests/test_adapter_run.py` `TheWiringPassesTheRealPin`). The fixed instructions and the vocabulary payload are recorded by digest: `prompt_digest.instructions_sha256 d158022655f168fe9eb5a8961f103abbcb584725de2d2e3a806612b03df10142`, `prompt_digest.payload_sha256 638e2287a01bb107a103a74e47d33e0fad30f93d0a1936e0020b8318e685cf22`; the output schema, which Section 4.6 does not pin, is recorded by `schema_digest d3dd40a9e9f961fc0dbdb77f3858122cb673602809fd89b38c64143059aa4702` ([#111](https://github.com/OKJ1105/evidence-first-rag/issues/111)). Each is recomputable from the tree: `python3 -c "from evidence_first_rag.adapter import run; print(run.prompt_digest(), run.schema_digest())"`. A change to the model, the decoding, the instructions or the payload reopens the comparison (Section 4.6), and with it this gate.

## Effect

- Contract Section 8.2's two deferred rows — Section 4.6 adapter adoption and the Section 4.7 baseline comparison — are discharged by this record, where Section 8.2 says they are. No amendment is needed.
- `needs_entity_discovery` stays terminal. Milestone 3 is not opened by this decision.
- `README.md`'s status table gains nothing new; this record is what turns the Section 4.6 and 4.7 rows from implemented into adopted.
- The instruction text, schema and decoding this record describes are pinned by digest in the committed artifact; a later change reopens the gate rather than inheriting it.
