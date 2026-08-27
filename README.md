# Evidence-First RAG Runtime

Evidence-First RAG Runtime is a bounded backend for answering scoped message, signal, and mapping questions over structured engineering data.

The name is deliberate. This is a RAG architecture with the retrieval layer re-grounded: retrieval means executing registered, read-only SQL templates over structured data — never semantic search presented as fact. Augmentation means attaching an inspectable evidence bundle with a source trace and explicit limitations to every result. Generation is constrained rendering that cannot add facts.

The intended product user is an engineer who would otherwise open structured definition files and cross-check them by hand. The core rule is simple: AI may interpret intent and help locate an entity, but authoritative facts must come from approved, read-only queries over structured data.

## Status

This repository is in the contract-shaping phase. The Project Charter is frozen; runtime behavior is specified by reviewed contracts before it is implemented.

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
