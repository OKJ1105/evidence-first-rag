# ADR-0006: Relay Spend Is Bounded by the Provider Workspace

**Status:** Proposed. Recorded by the writer session on [#249](https://github.com/OKJ1105/evidence-first-rag/issues/249) from the repository owner's decision of 2026-09-29. The owner's disposition on the pull request is the recorded human decision.

**Date:** 2026-09-29

## Context

[ADR-0005](0005-the-chat-relay-is-a-host-this-project-operates.md) item 5 makes the relay bound cost with its own caps, a daily ceiling among them. It names the Anthropic Console usage limit as a backstop: "neither is the design". `relay-v0.1` Section 8.3 derived that ceiling from the worst-case cost of one call.

That derivation, run by the owner on 2026-09-29 ([record](../acceptance/milestone-5/cost-2026-09-29-body-32k.json)), leaves almost nothing to serve:

- The fixed Azure cost is 6,733.50 JPY of the 8,000 JPY monthly budget. That leaves 42.22 JPY a day.
- One worst-case call costs 13.91 JPY at one tool call and 61.11 JPY at five.
- The ceiling over what remains is therefore three calls a day at most, and one if the model calls the tool twice or three times.

That ceiling counts all visitors together, and each follow-up turn is a separate call. A count derived from the worst case makes the page unusable as the link it exists to be.

The worst case is also far from the typical request. A count cannot tell a short question from a 32 KiB conversation, so a count that is safe for the second starves the first.

## Decision

**Spend is bounded by the Anthropic Console workspace the relay's API key belongs to.**

- That workspace holds no other key.
- Its monthly spend limit is set to at most the budget left after the fixed cost, converted at the recorded rate. On the 2026-09-29 record that is USD 8.
- The provider refuses calls past the limit. The relay then answers `model_unavailable` until the month turns or the limit is raised.

**The relay keeps every cap ADR-0005 item 5 lists:** the per-client rate limit, the turn limit, the fixed `max_tokens` and a daily ceiling past which it refuses. The daily ceiling changes role. It keeps one day from spending the month (`relay-v0.1` Section 8.3 registers 67), and no longer carries the budget arithmetic.

**This supersedes one sentence of ADR-0005 item 5:** the Console limit is no longer only a backstop. The Azure budget alert remains a backstop.

## Alternatives considered

- **A ceiling derived from the worst case.** This was the design until now. It gives one to three calls a day, as described in Context.
- **Raising the budget.** The owner declined.
- **Stopping PostgreSQL when idle** to lower the fixed cost. This is deferred: the database is the only fact source, and a stopped server is restarted by the platform after a period.
- **A monthly count persisted by the relay.** It would need state the relay does not hold (ADR-0005 item 6), and it still would not bound spend.

## Consequences

- **What bounds spend is a setting outside this repository.** No check here can read it. `relay-v0.1` Section 8.3 therefore makes the owner's recorded statement that the limit is set its acceptance evidence, recorded before the first deployed run.
- **A month can end early.** Once the limit is reached, every visitor sees `model_unavailable` until the month turns. The page must render it as the relay's refusal, and that obligation is unchanged.
- **The worst-case computation stays committed.** It states what the limit buys at worst: about 91 worst-case calls a month at one tool call.
- **A misconfigured key breaks the bound.** A key from a workspace without the limit, or shared with other use, voids it. The deployment's key must come from the dedicated workspace, and replacing the key repeats the owner's statement.
