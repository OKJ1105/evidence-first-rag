# Development Workflow

This workflow keeps changes small, reviewable, and consistent with the repository's architecture and information-safety contracts.

## Source of truth and scope

- A GitHub Issue is the canonical record for each task. Record the intended behavior, acceptance criteria, affected contracts, and known limitations there before implementation.
- One pull request contains one independently reviewable behavior and the tests or other acceptance evidence for that behavior. Split unrelated cleanup, additional behaviors, and deferred improvements into separate Issues and pull requests.
- The [AI Development Workflow](ai-development-workflow.md) assigns the writer, independent-reviewer, and human responsibilities and defines the L0/L1/L2 review levels. This document remains authoritative for contract, acceptance, and merge gates.
- Before changing code or contracts, follow the read order and stop conditions in `AGENTS.md`.

## Change sequence

1. Create or refine the GitHub Issue and confirm that the requested behavior is covered by a reviewed contract and applicable fixtures.
2. Create a branch from the latest `main`.
3. Update the relevant contract and acceptance fixtures. Record source meaning and limitations, and define the automated assertion or recorded human decision that accepts the slice.
4. Obtain the required human review of the contract, fixtures, and acceptance evidence before implementation. If that review is not already recorded, split out a contract-only pull request and do not implement the behavior slice yet.
5. Implement only the Issue's behavior slice and its tests.
6. Run every lint, test, conformance, and read-only invariance check defined by the repository. Record each command and result in the pull request; do not claim a skipped check passed.
7. Open a Draft pull request that links the canonical Issue and completes the repository PR template.
8. Complete the review protocol and every applicable human review or approval gate below. Merge only after blocking findings are resolved, required human dispositions are recorded, and required human approval is recorded.

## Independent design review protocol

- One writer owns the change. Independence is carried by the five properties in [ai-development-workflow.md](ai-development-workflow.md). Model difference is not among them and is not required. Assigning the reviewer a different model on a high-risk slice remains available as an explicit per-pull-request choice, recorded in that pull request.

  > **Recorded decision by the repository owner, 2026-09-03, on Issue #30.** This bullet previously read "the reviewer must use a different model from the writer". The requirement did not appear among the independence properties, the two documents disagreed about how load-bearing it was, and the code had never implemented it. The owner's reasons for dropping it as a standing rule: review should not be handed to a lower-cost model merely to satisfy a rule the independence properties do not list; and the most capable model carries a weekly limit, which makes it a scarce resource better spent where model capability is itself the subject than on routine diff review.
  >
  > **What this gives up.** Two turns of the same model share their training priors, so a correlated blind spot — a mistake the writer makes and the reviewer does not see because it would have made it too — stays a live risk. Requiring a different model would not have removed that risk either, since no two models are independent in the statistical sense, but it would have reduced it, and dropping the requirement forgoes that reduction. What is relied on instead is the four properties that hold structurally rather than by instruction (separate process, base-branch instructions, withheld pull request body, read-only tool set) and the repository owner's own review, which is the one step in this workflow not performed by a language model. The per-pull-request option above is what remains of the mitigation: where a correlated blind spot would be expensive, assign the reviewer a different model and record that choice.
- The reviewer is read-only: they inspect repository artifacts, the Issue, contracts, diff, and validation evidence, but do not edit files or produce a competing patch.
- The reviewer reports only P0/P1-equivalent blocking findings, with at most five findings in total. Lower-severity suggestions are omitted from the blocking review or captured in a separate GitHub Issue when genuinely useful.
- After the writer addresses the findings, the reviewer performs one follow-up inspection of the resulting diff. That single confirmation pass ends the model-review cycle; any unresolved blocker is reported for human disposition rather than starting repeated model review loops.
- This bounded model review is an independent design review only. It does not replace any required human review or approval.

The P0/P1, five-finding, and one-follow-up limits apply only to the bounded model review. They do not limit required human review or any recorded human decision.

## Durable decisions

Do not leave an adopted technical or product decision only in pull request comments. When the decision changes or clarifies durable behavior, record it in the applicable contract, ADR, or test. Update the Project Charter only when the decision materially changes the architecture or project boundary.

## Architecture and information-safety guardrails

Every change must preserve the existing design contracts, including:

- authoritative facts come only from registered fixed SQL templates;
- database access remains read-only;
- unsupported, ambiguous, invalid, missing, and coverage-gap cases fail closed;
- normalized results preserve the required `evidence_bundle`, `source_trace`, and `limitations` information.

Never place production data, real-world identifiers, credentials, or confidential information in the repository, GitHub Issues, pull request descriptions, review comments, or test fixtures. Use synthetic fixtures and portable placeholder identifiers only.
