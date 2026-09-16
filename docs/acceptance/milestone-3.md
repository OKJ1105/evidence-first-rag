# Milestone 3 Acceptance Record

**Milestone:** 3 — Entity Discovery

**Disposition:** Accepted

**Date:** 2026-09-16

**Recorded by:** repository owner

**Reasoning.** What this record establishes is not that the method retrieves well. It is that a method passed a test defined in advance, and that neither the cases nor the bars were changed after the run — evidence that the process was followed, and nothing more. I adopt it on that basis.

What the run had to show, and did, is the behaviour this system exists for: when the answer is not known, it says so; when a term does not determine a single entity, it returns the alternatives rather than choosing among them. The failure this is built to prevent is handing an engineer a fact from the wrong revision in a form they will not question, and every case registered for it — the ten ambiguous requests and the five that name nothing in the registry — behaved that way.

That `false_resolution` is zero by construction for any conforming method does not weaken it. Conformance is what the bar is for, and the bar earns its keep later: a retrieval method that ranks — BM25, vectors, or a learned layer — can drift here in a way the current one cannot, and this set is what will catch it.

The forty cases were authored from the same tier table the method implements, and Section 8.3 registers in advance what a difficult semantic case is and that this set holds none. The question that matters is whether the cases are sound, not whether their author had read the rules, and the gap is named and counted rather than hidden. `M-LEX-1` is adopted as the Milestone 3 baseline; a later method is registered as a minor version of this contract under Section 4.9 and is measured against this same registered set and these same bars, so that what changes between methods is the method.

This record collects the evidence for the Milestone 3 acceptance gate in [Project Charter](../PROJECT_CHARTER.md) Section 9. Every gate item below names the evidence that exists — an automated assertion over registered inputs, or a field of the committed run artifact — and where it runs. No item rests on a claim made only here. Drafted from that evidence by Claude Code, the writer session ([#167](https://github.com/OKJ1105/evidence-first-rag/issues/167)); **the disposition is the owner's alone**, and a judged artifact that had not cleared the registered bars would have produced a Rejected record with the same care.

## The run this record rests on

[Entity Discovery Contract v0.1](../contracts/entity-discovery-v0.1.md) Section 4.10 evaluation set, Section 8.3 thresholds, contract version `0.3.1`.

| | |
| --- | --- |
| Committed artifact | [`milestone-3/discovery-run.json`](milestone-3/discovery-run.json) |
| `run_id` | `872e04e9-5879-412c-bfe1-f1a6a0aa4136` |
| `started_at` | `2026-09-14T08:45:25Z` |
| Actions run | [34824294989](https://github.com/OKJ1105/evidence-first-rag/actions/runs/34824294989), run #2, head `d574f5c`, `workflow_dispatch` of `.github/workflows/milestone-3-run.yml` by the repository owner |
| Database | PostgreSQL 17.11, a job-scoped service container, provisioned from `fixtures/` in the same job |
| Method | `M-LEX-1` version `1` — the only registered method (Section 4.9) |
| Registry | `registry_digest 1b81429adae7a373bf434b6a7e1e912991808c94376df849fdfd5c230c608ddb`, `registry_built_at 2026-09-14T08:45:25Z` |
| Thresholds judged against | Section 8.3, per class, `registered_at 2026-09-13T15:55:00Z` |
| `authoring_failures` | `[]` — the judged set breaks no Section 4.10 authoring rule |
| `judgement` | `judged: true`, `adoptable: true`, `reasons: []` |

`adoptable` adopts nothing. It is a statement that the numbers cleared bars set in advance; Section 8's own row keeps adoption a recorded human decision taken after the run, which is the line above this table.

**The committed file is the document the run wrote.** It was retrieved from the run's Actions artifact and is 65,182 bytes, `sha256 9fa705c48100484e099eaf26d9ecdfbead00d4d67b09384c56bec8dc995296db`. Three checks were made before committing it, because the writer session cannot reach the blob host that serves Actions artifacts and so could not fetch it itself:

1. **It is the runner's own serialisation.** `artifact_text(json.loads(file)) == file` — so it was not re-serialised, reformatted or round-tripped by anything in transit.
2. **It is internally consistent, and that check is standing; that it reproduces is still the writer's word.** Run against the same fixture tree locally, all forty case records and every metric are identical once `run_id`, `started_at`, `registry_built_at` and the latency measurements are set aside — the only four kinds of value a second run may legitimately differ in. That was the writer's word, which this record's own rule does not accept, so [`tests/test_acceptance_milestone_3.py`](../../tests/test_acceptance_milestone_3.py) now asserts it in `package-unit-tests`: the committed artifact's forty `expected` blocks equal `REGISTERED_SET`, its `registry_digest` equals the Section 8.3 digest, its `judgement` cites `REGISTERED_AT` and the registered bars, and **every metric — per class and over the set, latency included — recomputes from the file's own case records**, each exactly but for the two reported `mrr` figures, which are held to four units in the last place. That one loosening is the interpreter and not the run: Python 3.12 changed `sum()` over floats from a left fold to Neumaier compensated summation, which moves the `Q-MULTI` mean of `1/2, 1/2, 1/2, 1/3, 1/7` by one unit in the last place, and the committed run was produced on the `3.11` this repository pins. A test demanding bit equality there would be asserting which interpreter ran it. Four units is still far below any edit that could change what a reader concludes. Fourteen edits to the committed file were each shown to fail it. One does not: a `completion` altered on a case that names no route, which Section 4.11 does not count; the test says so rather than implying more.
3. **It matches the job log.** [#166](https://github.com/OKJ1105/evidence-first-rag/pull/166) makes `discovery/runner.py` print the document after the summary, for the reason [#117](https://github.com/OKJ1105/evidence-first-rag/issues/117) gives for `adapter/run.py`: so a run can be read by someone who cannot download its artifact. The metrics and judgement read from that log agree with the committed file.

**Every value in the committed file was checked against the `SAMPLE_*` convention**, which is Charter Section 11's rule that this repository carries synthetic fixtures and portable placeholder identifiers only. Mechanically: every name in the file — every token that begins a word and carries an upper-case letter — is either `SAMPLE_*`, one of the forty registered case identifiers, one of the eight `Q-*` class names, or the method identifier `M-LEX-1`; nothing else upper-case appears, and in particular the file holds no capitalised word at all, which is the shape a person, product or company name would take. By reading: the only free text is the `term` of the cases that register a description rather than a key — the `Q-SEMANTIC`, `Q-MULTI`, `Q-SCOPE` and `Q-OUT` terms, all lower-case generic English such as "engine speed", "transmission state" and "network members", two of which ("sample msg", "sample sig") name the fixture convention itself — and there is no credential, host, URL, local path or personal name anywhere in the document. Neither standing check would have caught a lapse here: `scripts/checks/validate_fixtures.py` applies the convention under `fixtures/` only, and `scripts/checks/scan_sensitive_strings.py` records in its own docstring that nothing enforces it for prose. So the mechanical half is asserted over the committed file in [`tests/test_acceptance_milestone_3.py`](../../tests/test_acceptance_milestone_3.py) and runs in `package-unit-tests`, rather than resting on the writer's word as this record's own rule forbids; the human guard is the repository owner's review of the pull request that carries this record, recorded with the disposition above.

**What is *not* standing, stated plainly because the paragraphs above could be read as more than they are.** Nothing in this tree re-runs the registered forty against the fixture tree and compares the committed `observed` blocks: `tests_database/test_discovery_runner.py` drives one case per class and never opens this file. So the committed artifact is checked for *internal* consistency — its questions are the registered ones, its digest and registration are the Section 8.3 ones, and its metrics are what its own case records entail — and **an `observed` block edited consistently with the metric it feeds would pass every committed check**. Concretely: reorder `EV-SEMANTIC-4`'s candidate list to put the target at rank 1, raise `Q-SEMANTIC.recall_at_1` to `1.00` and its `mrr` to `1.00` to match, and nothing here objects. That the `observed` blocks are what a fresh run produces rests on the writer's local reproduction and on the job log of [run 34824294989](https://github.com/OKJ1105/evidence-first-rag/actions/runs/34824294989), not on a test. Making it standing needs a `tests_database/` test that runs `REGISTERED_SET` against a provisioned database and compares the result with this file, `run_id`, `started_at`, `registry_built_at` and the latencies removed; that is a slice this record does not carry.

**No stability run is committed, and none is owed.** Milestone 2 dispatched a second run because a model is not deterministic across runs and its `false_resolution` bar admitted none. `M-LEX-1` invokes no model; Section 6 already requires two runs over the same registry and request to compare byte-identical with `registry_built_at` removed, and that is asserted in `tests_database/`. Determinism here is a contract obligation with a standing test, not something a second dispatch would establish.

## What the run measured

Forty cases, five in each of Section 4.10's eight query classes. Per class, with the Section 8.3 bar in parentheses where one is registered:

| class | recall@1 | recall@5 | recall@10 | mrr | false_res. | correct_abst. | over_abst. | task_compl. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| `Q-EXACT` | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) | 1.00 | 0.00 (0.00) | — | 0.00 (0.00) | 1.00 (1.00) |
| `Q-ALIAS` | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) | 1.00 | 0.00 (0.00) | — | 0.00 (0.00) | 1.00 (1.00) |
| `Q-SEMANTIC` | 0.80 (0.80) | 1.00 (1.00) | 1.00 (1.00) | 0.90 | 0.00 (0.00) | 1.00 (1.00) | — | 1.00 (1.00) |
| `Q-SCOPE` | — | — | — | — | 0.00 (0.00) | 1.00 (1.00) | — | — |
| `Q-COLLIDE` | 1.00 (1.00) | 1.00 (1.00) | 1.00 (1.00) | 1.00 | 0.00 (0.00) | — | 0.00 (0.00) | 1.00 (1.00) |
| `Q-MULTI` | 0.00 | 0.80 (0.80) | 1.00 (1.00) | 0.3952… | 0.00 (0.00) | 1.00 (1.00) | — | 1.00 (1.00) |
| `Q-NOMATCH` | — | — | — | — | 0.00 (0.00) | 1.00 (1.00) | — | — |
| `Q-OUT` | — | — | — | — | 0.00 (0.00) | 1.00 (1.00) | — | — |

Over the set: `false_resolution 0.0000`, `correct_abstention 1.0000`, `over_abstention 0.0000`, `task_completion 1.0000`, median latency `0.0153 s`, p95 `0.0175 s` — and `recall_at_1 0.76`, `recall_at_5 0.96`, `recall_at_10 1.00`, `mrr 0.8590…`.

**Those four recall and `mrr` figures have a denominator of twenty-five, not forty**, and Section 8.3 states it plainly for exactly this reason: "it is stated here so that a whole-set number is not read as a retrieval score." Ten of the forty cases are refusals — `Q-SCOPE` and `Q-OUT` measure validation rather than retrieval and name no target, so Section 4.11 excludes them from the recall denominator. **`0.76` is nineteen of twenty-five, not thirty of forty**, and the six that are not hits at `k = 1` are named: the five `Q-MULTI` cases, which are zero at `k = 1` by construction because none registers a single reference, and `EV-SEMANTIC-4`, at the rank `2` its registration set. There is no retrieval miss in this run.

*Discovery* is the operative word in that sentence, and the record repeats the distinction rather than rounding it off: seven of the ten refusals — the five `Q-SCOPE` cases and `EV-OUT-4`/`EV-OUT-5` — do open a connection and execute the `mvp-v0.1` candidate query, which Section 4.3 runs on every request because it is what tells `coverage_gap` from `not_found`. Only `EV-OUT-1` to `EV-OUT-3`, refused on an `entity_kind` outside the two Section 4.1 enumerates, open none. The Section 4.10 artifact records no `template_name`, so that count is **not** checkable against the committed file; a reader wanting to check it wants a conformance artifact, and this record does not claim otherwise.

A dash is not a waiver. Section 8.3 distinguishes two reasons a cell carries no bar, and the artifact carries the distinction: **no denominator**, where the class's registered outcome leaves the Section 4.11 denominator empty, and **reported without a bar**, where the denominator exists and no bar would say anything. `Q-MULTI`'s `recall_at_1` is the second kind, and its `0.00` is arithmetic rather than a miss: **no `Q-MULTI` case registers a single reference**, so Section 4.11's rule that such a case counts at `k` only when every reference appears makes `recall_at_1` zero for any method whatever.

**Every case's observed status equals its registered outcome — forty of forty.** Five `resolved` in each of `Q-EXACT`, `Q-ALIAS` and `Q-COLLIDE`; five `candidates` in each of `Q-SEMANTIC` and `Q-MULTI`; five `ambiguous` in `Q-SCOPE`; five `not_found` in `Q-NOMATCH`; three `unsupported` and two `coverage_gap` in `Q-OUT`.

**Every registered rank bound is met exactly.** Section 4.10 rule 3 registers a bound per `Q-SEMANTIC` case because "somewhere in ten" and "first" are different claims, and `0.3.1` makes each bound a pass condition in its own right rather than only an input to the class bar:

| case | registered bound | observed rank |
| --- | --- | --- |
| `EV-SEMANTIC-1` | 1 | 1 |
| `EV-SEMANTIC-2` | 1 | 1 |
| `EV-SEMANTIC-3` | 1 | 1 |
| `EV-SEMANTIC-4` | 2 | 2 |
| `EV-SEMANTIC-5` | 1 | 1 |

`EV-SEMANTIC-4` is the case the `recall_at_1 0.80` bar was derived from, observed at the rank the derivation predicted.

**`Q-MULTI` reached the ceiling its registered list sizes entail.** The five cases register 2, 2, 2, 3 and 7 references, and each returned its whole reference set contiguously from rank 1 — ranks `[1,2]`, `[1,2]`, `[1,2]`, `[1,2,3]` and `[1,…,7]`. `recall_at_5 0.80` is therefore four of five, with only the seven-reference case unable to fit in five; `recall_at_10 1.00` is all five. The bars were the ceilings, and the method is at them.

## Gate item 1 — Each adopted method meets the pre-registered retrieval, false-resolution and abstention thresholds for every governed query class

The committed run, judged by `discovery/judgement.py` against the Section 8.3 registration: `judged: true`, `adoptable: true`, `reasons: []`. `M-LEX-1` is the only registered method, so "each adopted method" is one method.

The judge refuses before comparing any number when there are no registered thresholds (Charter Section 9), when the registration is not strictly before the run, when the run executed against a registry other than the one the set was authored against (Section 4.10 rule 8), when the judged cases are not the registered forty, or when the set breaks an authoring rule. **None of those refusals is a margin invented by the judge**; each names a Charter or contract sentence, and each is driven by a test shown failing under a named mutation (`tests/test_discovery_judgement.py`, `tests_database/test_discovery_runner.py`). In this run the ordering holds — `registered_at 2026-09-13T15:55:00Z` precedes `started_at 2026-09-14T08:45:25Z` — and the observed registry digest equals the one the set was authored against.

`discovery/runner.py` exits 0 when a run was judged and 2 when it was not, so an unjudged run is a red job rather than a silent one; `tests_database/` asserts both codes against a real database.

## Gate item 2 — Ambiguous requests do not silently resolve

Section 4.7 permits auto-resolution only from tiers 1 and 2, and only when exactly one entity matches; anything else returns a candidate list. Fixtures `DX-004` and `DX-005` are the two collisions that must **not** resolve, and the contract notes that either alone is satisfied by a rule the section rejects.

In this run, the five `Q-SCOPE` cases each returned `ambiguous` and the five `Q-MULTI` cases each returned `candidates`; `false_resolution` is `0.0000` in every class, and `correct_abstention` is `1.0000` wherever the denominator exists. Section 4.12 and the data-level check keep a discovery payload free of attribute columns, so an ambiguous result cannot leak a fact in place of a resolution.

## Gate item 3 — Selected candidates are canonical entity references present in the approved registry and resolvable in the approved data scope

Section 4.8's selection path re-derives the candidate list, checks `candidate_set_id`, and dispatches the selected reference to an `mvp-v0.1` fact route. `DX-017` asserts a verified selection reaching a fact route with both executed templates evidenced; `DX-018`, `DX-019` and `DX-021`–`DX-023` assert the five refusals. A changed registry changes `candidate_set_id`; `target_route` is not an input to that digest; the digest is recomputed from the Section 4.8 key list independently of the runtime and compared.

In this run, `task_completion` is `1.0000` in every class where the denominator exists — each case whose registered outcome is `candidates` completed through the Section 4.8 selection path selecting the registered target, and each `resolved` case dispatched its one reference directly, per Section 4.8. A reference absent from the registry cannot complete, because the route is driven from the reference the registry returned.

## Gate item 4 — Unapproved aliases do not auto-resolve to a single candidate

Section 4.7's adopted rule is that only tier 1 (`lookup_key` byte-equal) and tier 2 (an **approved** alias, byte-equal) may auto-resolve. The reading was adopted by the repository owner at contract review on 2026-09-11 ([#138](https://github.com/OKJ1105/evidence-first-rag/issues/138)), with the declined conservative alternative recorded beside it. An alias row requires an `approval_reference` and an asserting snapshot equal to its entity's; the data-level check asserts both, and asserts that there is deliberately no unique constraint on `alias_text` alone.

In this run, `Q-ALIAS`'s five cases resolved through approved aliases at rank 1, and `Q-NOMATCH`'s five returned `not_found` with `correct_abstention 1.0000` — a term that matches no approved entity or alias abstains rather than reaching for a near neighbour. Tiers 3 and 4 produce candidates and never a resolution, which is what keeps an unapproved surface form from becoming a single answer.

## Gate item 5 — Final facts still come only from the fixed-SQL runtime

Discovery executes only three *discovery* templates — `TPL_REGISTRY_STATE_V1`, `TPL_DISCOVERY_EXACT_V1` and `TPL_DISCOVERY_LEXICAL_V1` — plus `TPL_SNAPSHOT_CANDIDATES_V1` where Section 4.3 requires the scope and coverage query, which is the distinction this record draws above rather than a fourth discovery template. All four are registered under `mvp-v0.1` Section 4.4's safeguards; facts come from the `mvp-v0.1` routes, unchanged. The runtime identity is refused `INSERT`, `UPDATE`, `DELETE` and `CREATE TABLE` on the registry tables **by PostgreSQL privileges rather than an application guard**, and `tests_database/` asserts each refusal.

This run opened its database as that identity: the runner takes the runtime credentials from the environment as `conformance/runner.py` does, and reads the registry state through a registered template rather than ad-hoc SQL, so the digest this record cites is one a registered template returned. No model library is installed in the job at all — the workflow installs the package without the `adapter` extra.

## What this record does not claim

**The forty cases were authored by an AI writer session that had read the tier table the method implements.** Section 4.10 rule 5 requires each case to be authored without running a retrieval method over it, and that was honoured: every expected outcome was read off the registry rows and Section 4.5's tier table and checked against a second derivation written independently from the same table; no method was run over any case before registration; and `registered_at` precedes every run. But *not having run the method* and *not knowing how it works* are different claims, and only the first is true here. A case set authored from the same table the method implements is a **construct-validity** limitation, not a pre-registration failure — and it is the honest reading of why forty of forty cases land on their registered outcome.

**`Q-SEMANTIC`'s and `Q-MULTI`'s bars are derived, not chosen.** `Q-SEMANTIC`'s recall bars are the aggregate the five registered rank bounds entail; `Q-MULTI`'s are the ceilings the registered list sizes entail, given Section 4.11's rule that such a case counts at `k` only when every reference appears. A derived bar is exactly as strong as what it was derived from, and Section 8.3 states each derivation so a reader can disagree with a step rather than with a number. `false_resolution 0.00` is likewise derived on two independent grounds — Charter Section 3.3, and Section 4.9 point 4's rule that no method may auto-resolve outside tiers 1 and 2, which makes a conforming method score zero by construction rather than by effort.

**In-sample, and said so.** These are the forty cases Section 8.3 registers, and this record measures `M-LEX-1` on them. Nothing here claims the method generalises to terms it was not registered against. Milestone 2's record carries the same statement for its own frozen set, and [#123](https://github.com/OKJ1105/evidence-first-rag/issues/123) holds the out-of-sample question; a held-out set needs its own threshold registered before the run that judges it, for the reason Section 8.3 exists, and is not something to bolt onto this one.

**Two of the five `Q-MULTI` cases are degenerate requests, and one of them fixes the bar this record calls reached.** Section 8.3 records it: "`sample msg` and `sample sig` match on the fixture naming convention rather than on anything a person would type. They are registered because the loaded occurrences offer few genuinely ambiguous descriptions, and because a broad term is the request a method is most tempted to resolve. Replacing them takes more fixture rows and a patch version." Those are `EV-MULTI-4` and `EV-MULTI-5` — and **`EV-MULTI-5`'s seven references are what put the `recall_at_5` ceiling at `0.80`**, the ceiling the paragraph above says the method is at. A clean `Q-MULTI` result is therefore weaker evidence about behaviour on *plausible* ambiguity than its numbers suggest: two of the five questions are artefacts of how the fixtures are named, and the load-bearing one is among them.

**No vector or BM25 variant is registered, and none was run.** Section 3.2 leaves a vector variant's pre-registered budget unfixed; Charter Section 12's question of whether vector search materially outperforms lexical is unanswered by this record and is a later minor version of the contract, with an ADR if registry content would leave the process.

**Two cases the set does not contain.** Section 8.3 registers what a *difficult* semantic case is — a `Q-SEMANTIC` case whose term shares no token with any `match_text` of its target, so tier 4 cannot reach it — and registers that this set holds **zero** of them. That definition was fixed in advance precisely so a later registration could not choose it afterwards. `Q-SEMANTIC 1.00` at `recall_at_10` should be read with that in mind.

## Effect

- Contract Section 8.2's row for the adoption thresholds — "at the Milestone 3 gate, after Section 8.3 registers them and the run they judge has happened" — is discharged by the owner's disposition on this record, where Section 8.2 says it is. No amendment is needed.
- The Section 8 table's `4.9 M-LEX-1` row — "the method's results over the registered evaluation set, recorded in the run artifact with its identifier and version" — is discharged by the committed artifact, which carries `M-LEX-1` and version `1`.
- Section 3.3's three extension rows stay open as Section 9 records them: whether `mvp-v0.1` is patched to name this contract's routes, registry tables and `selection` record is the owner's under that contract's Section 10. Section 3.3 states the reading that holds in the interval, and the implementation built against it; nothing in this gate turns on the answer.
- `README.md`'s Milestone 3 table said the cases and the thresholds were registered and said nothing about a run. It now records that the run has happened and is committed, and that adoption remains the owner's — the same shape as the Milestone 2 paragraph beside it.
- A change to the registered cases, a threshold or the registry re-registers `registered_at` under Section 4.10 rule 8 and reopens this gate rather than inheriting it. The judge enforces that mechanically: a run against a registry other than `1b81429a…` is refused rather than scored.
