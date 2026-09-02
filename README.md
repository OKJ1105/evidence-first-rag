# Evidence-First RAG Runtime

Evidence-First RAG Runtime is a bounded backend for answering scoped message, signal, and mapping questions over structured engineering data.

The name is deliberate. This is a RAG architecture with the retrieval layer re-grounded: retrieval means executing registered, read-only SQL templates over structured data — never semantic search presented as fact. Augmentation means attaching an inspectable evidence bundle with a source trace and explicit limitations to every result. Generation is constrained rendering that cannot add facts.

The intended product user is an engineer who would otherwise open structured definition files and cross-check them by hand. The core rule is simple: AI may interpret intent and help locate an entity, but authoritative facts must come from approved, read-only queries over structured data.

## Status

The Project Charter is frozen and the [MVP runtime contract](docs/contracts/mvp-v0.1.md) is `Accepted`, so runtime behavior is specified by reviewed contracts before it is implemented. Implementation of that contract has started.

The table below says how much of the contract executes today, section by section. It is here because a repository that describes an architecture without saying how much of it runs is a design document, and the two are hard to tell apart from the outside. Every slice that changes what runs updates this table.

- **Contracted** — specified and reviewed. No code.
- **Types only** — the shape exists and is tested. Nothing executes it yet.
- **Implemented** — it runs, with the acceptance evidence its contract section requires.

| Contract section | Surface | State |
| --- | --- | --- |
| 3.4 Platform | PostgreSQL 17, plain-SQL provisioning under Docker Compose | Contracted |
| 4.1 Data model | Schema, columns, and uniqueness constraints | Contracted |
| 4.2 Identity and scope | Canonical message and signal reference types | Types only |
| 4.3 Database identities | Provisioning and read-only runtime roles | Contracted |
| 4.4 Template registry | Four fixed SQL templates, safeguards, limits, timeout | Contracted |
| 4.5 Routes | The three route names, as a closed set | Contracted |
| 4.6 Thin LLM Adapter | Adapter and deterministic revalidation | Contracted |
| 4.7 Deterministic baseline | Exact-match control group for the Milestone 2 comparison | Contracted |
| 4.8 Answer rendering | Fixed-template rendering over a normalized result | Contracted |
| 4.9 Conformance runner | Checks A through E, verdicts, failure classes | Contracted |
| 4.10 Read-only invariance | State digests and the four refusal assertions | Contracted |
| 4.11 Fixture serialization | The registered JSON Lines fixture files | Implemented |
| 4.11 Fixture serialization | The loader that resolves natural keys at load time | Contracted |
| 5 Outcome coverage | The seven status families, as a closed set | Types only |
| 6 Determinism | Ordering, collation, and no-normalization rules | Contracted |
| 7 Evidence obligations | `evidence_bundle`, `source_trace`, `limitations` types | Types only |
| 8.1 Required fixture cases | Structural fixture data for the registered cases | Implemented |
| 8.1 Required fixture cases | Registered expected results per fixture | Contracted |

Nothing in this repository opens a database yet.

See [Project Charter](docs/PROJECT_CHARTER.md) for the product direction, architecture boundaries, success criterion, roadmap, and release conditions.

## Intended flow

1. Interpret a bounded user request.
2. Produce an approved route and validated parameters.
3. If a scoped canonical entity reference is missing, return ranked candidates from the approved entity registry and abstain when scope or identity remains ambiguous.
4. Execute only a registered fixed SQL template against a read-only structured source.
5. Return normalized facts or relations with an evidence bundle, source trace, and limitations.
6. Render or export the validated result without changing its meaning.

## Repository policy

- Use synthetic fixtures and portable placeholder identifiers only.
- Do not commit production data, real-world identifiers, credentials, or internal URLs.
- The reviewed repository contracts are the normative implementation authority.
- Do not generate or execute free-form SQL.
- Do not treat semantic retrieval results as authoritative facts.
- Implement one reviewable behavior slice per pull request, with its contract and fixtures reviewed before its code.

Detailed contributor and agent constraints are in [AGENTS.md](AGENTS.md).
