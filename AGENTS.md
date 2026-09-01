# Repository Instructions for Coding Agents

These instructions apply to the entire repository.

## Read order

Before changing code or contracts:

1. read `docs/PROJECT_CHARTER.md`;
2. read the contract and fixture files relevant to the requested slice;
3. inspect existing tests and the current branch diff;
4. stop if the requested behavior lacks a reviewed slice-specific contract or applicable fixtures.

The current repository phase is documentation and architecture-level contract-shape freeze. Do not implement a behavior until its slice-specific contract, applicable fixtures, and acceptance check have been committed and reviewed. Individual routes, SQL templates, and fixtures are added incrementally; they are not all frozen before the first implementation slice.

## Hard architecture boundaries

- Authoritative facts and relations come only from registered fixed SQL templates over approved structured sources.
- Never generate or execute free-form SQL from user text or model output.
- Never expose a public arbitrary-SQL, arbitrary-table, or arbitrary-column interface.
- Bind user input only through named, allowlisted parameters and validate it before database access.
- Database access is read-only. Reject write keywords, schema changes, unknown templates, and unknown parameters.
- Every registered query has deterministic result ordering; exact identifiers, limits, sort keys, null ordering, normalization, and collation behavior belong to the Milestone 1 contracts.
- Do not infer missing facts, identifiers, source relations, aliases, or coverage.
- Unsupported, ambiguous, invalid, missing, and coverage-gap cases must fail closed with an explicit status and limitation.
- `not_found` means the approved data scope covers the question but has no matching row. `coverage_gap` means the required coverage is absent or cannot be established.
- `unsupported` means the request is not representable by an approved contract at the producing layer; preserve the producing layer in the trace.
- User-facing prose and exports may render normalized runtime results and evidence bundles but may not add facts.

## AI and retrieval boundaries

- A Thin LLM Adapter may choose only an approved route and extract explicitly stated arguments.
- Model output is untrusted input to deterministic contract validation.
- Send an external model only the user request and approved route, argument, and schema metadata required by the adapter contract. Do not send database rows, fixture contents, or evidence bundles without a separately reviewed ADR.
- When a scoped canonical entity reference is missing, return `needs_entity_discovery`; do not fabricate one.
- Before Milestone 3, `needs_entity_discovery` is terminal and cannot reach database execution.
- Entity Discovery may return ranked canonical entity references from an approved entity registry. It is not an authoritative fact source.
- Discovery candidates must be resolvable in the approved data scope. An unapproved alias must not auto-resolve to one candidate.
- Do not add vector search until a lexical baseline, labeled evaluation set, and pre-registered acceptance metric exist.
- Never silently fall back from a failed fixed-SQL route to vector retrieval and present retrieved text as factual evidence.
- Do not use an LLM to judge deterministic conformance.

## Data and information safety

- The repository Charter and reviewed contracts are the normative implementation authority.
- Use synthetic fixtures and portable placeholder identifiers only.
- Never add production data, real records, credentials, secrets, internal URLs, local machine paths, or personal information.
- Source traces must describe fixture provenance that actually exists in this repository.

## Change process

- Follow the repository [Development Workflow](docs/DEVELOPMENT_WORKFLOW.md) for Issue ownership, pull request scope, writer/reviewer separation, validation reporting, and durable decision capture.
- Follow the [AI Development Workflow](docs/ai-development-workflow.md) for L0/L1/L2 classification and the writer, independent-reviewer, and human roles.
- Implement one independently reviewable behavior slice per pull request.
- Keep unrelated cleanup out of the slice.
- Add or update the contract and applicable acceptance fixtures before implementing new behavior.
- Every new route, entity, relation, data source, fixed SQL template, or failure status requires fixtures for every outcome it can produce.
- Include applicable positive, ambiguity, abstention, `not_found`, `invalid_request`, `unsupported`, and `coverage_gap` cases; do not add unreachable status cases merely to fill a checklist.
- Preserve deterministic ordering, normalized output contracts, evidence bundles, source trace, limitations, and read-only invariance.
- Record a material architecture change in an ADR and update the Charter when necessary.
- Do not expand deferred scope merely because it is convenient for an implementation.

## Pull request evidence

Each implementation pull request must state:

- the behavior slice and contract it implements;
- the fixture IDs or tests that prove it;
- the fixed SQL templates and allowed parameters affected;
- the new or changed failure behavior;
- the commands run and their results;
- known limitations and deferred follow-up.

A conformance `fail` result always blocks acceptance and cannot be overridden into a pass. A `review` result requires an explicit recorded human disposition before the milestone can pass. Do not claim completion when required checks were skipped.

## AI collaboration

- GitHub Issues, branches, commits, pull requests, review records, and CI results are the canonical development record. Nimbalyst may present or edit that record, but its local session or Issue state is not authoritative.
- Claude Code is the default writer. The independent reviewer is a separate, non-authoring Claude process — normally the [Agent Loop](docs/agent-loop.md) — and must not edit files during a review. A disagreement that survives the bounded review cycle goes to the repository owner.
- Record the L0, L1, or L2 review level in the canonical Issue and pull request. When in doubt, choose the higher level.
- L0 requires no AI review. L1 requires one independent review round. L2 requires a pre-implementation design review and a post-implementation code or configuration review.
- An AI review cycle has at most two rounds: the initial review and one final inspection after fixes. Do not start a third AI round; record the unresolved point for human disposition or L2 arbitration.
- No AI may approve or merge a pull request. Only the repository owner records final acceptance, resolves the required conversations, and initiates merge.
- Do not install GitHub Apps, enable automatic reviews, change OAuth grants, create or rotate Secrets, or modify repository Rulesets without explicit repository-owner approval.

## Code Review Rules

- Flag only P0/P1-equivalent regressions in the frozen architecture, contract, information-safety, read-only, fail-closed, evidence, or provenance boundaries.
- Verify that the pull request matches its declared L0/L1/L2 level and that required review stages and validation evidence are present.
- Treat formatting and other deterministic mechanical checks as CI responsibilities rather than review findings.
