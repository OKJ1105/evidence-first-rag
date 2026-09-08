# Operating Policy

How work moves through this repository from 2026-09-08: the cadence between the writer and the repository owner. The [Development Workflow](DEVELOPMENT_WORKFLOW.md) and the [AI Development Workflow](ai-development-workflow.md) remain authoritative for contract, review, and merge gates, and nothing here loosens them. The live queue and the track assignments live on the tracking Issue named in the change record, not here; a session reads that Issue after this document.

## 1. The problem this solves

Every slice needs the owner twice: once to decide, once to merge. Until this policy those touchpoints alternated with the writer's work, so at any moment one party was waiting for the other: the owner idle while a slice was implemented, the writer idle until the next merge.

From the timestamps of the twenty pull requests merged between 2026-09-01 and 2026-09-08, the median time from opening a pull request to its merge was 13.6 hours, of which the loop's review took under twenty minutes; the owner merged in ten sittings, two pull requests per sitting; never more than four pull requests were open at once. The writer's work on a slice is on the order of an hour. Neither party's capacity is the limit. The serialization is.

The five-open-pull-request cap that the tracking Issue carried as its rule 1 never bound, so removing it changes nothing by itself. What changes throughput is that nobody waits.

## 2. Rules

1. **Pipelining: the writer never waits for a merge.** The moment a slice's pull request is open, the writer starts the next slice on a branch stacked on it, pushes that branch without opening a pull request, and drafts its pull request body. Before the dependency merges, the writer rehearses: cherry-pick the stacked commits onto the dependency's *current* head (the loop may have revised it), run every check in [.github/agent-checks.json](../.github/agent-checks.json), keep the result. When the dependency merges, the writer opens the pull request within an hour of noticing, and checks at least hourly.

2. **Every open pull request targets `main`, and its diff against `main` is its own slice only.** No pull request against a feature branch: the loop runs the *base* branch's machinery ([Agent Loop](agent-loop.md), BF4), so a stacked pull request would be judged by the wrong code and could never be labelled honestly. A slice whose dependency is unmerged waits as a pushed branch, not as a pull request.

3. **No numeric cap on open pull requests.** The binding constraints are the tracking Issue's rule 2 (one file tree per pull request; two open pull requests never touch the same file) and rule 2 above. Together they give the invariant the owner relies on: **any open pull request can be merged at any time, in any order, without reading the others.** Wave order is enforced by when pull requests are opened, not by how they are merged. This assumes the `main` Ruleset does not require branches to be up to date before merging; the [Manual Setup Checklist](manual-setup-checklist.md) does not ask for that.

4. **Owner sittings are batches, run off the queue.** The writer keeps one queue, on the tracking Issue, with three lists: pull requests ready to merge (head SHA, loop label, whether CI ran on that head); decisions waiting (options, the writer's recommendation, what each blocks); owner-only actions (Secrets, workflow dispatch, settings). The owner works it top to bottom, answers a decision in a word where a word will do, and leaves. Nothing in the queue requires reading a chat log. The writer's job between sittings is to fill the queue; the owner's job in a sitting is to empty it.

5. **Parallel tracks, so a blocker on one never idles the others.** Work is grouped into tracks, each with a default file tree, listed on the tracking Issue. When a track reaches an owner decision, the writer posts the decision to the queue and switches tracks. Waiting is not a state the writer is in. Tracks are default ownership only: the one-file-tree rule is still checked per pull request, against every open pull request and every claimed track.

6. **Several sessions may write at once, one per track.** A session claims a track by commenting on the tracking Issue before it starts and releases it when it stops. It never touches another track's tree while that track is claimed. Sessions coordinate only through GitHub — the Issue, the pull request, the diff — never through a chat's memory. Every session starts by reading [CLAUDE.md](../CLAUDE.md), the tracking Issue, and this document.

7. **What does not change.** The tracking Issue's rules 2 to 9. Every slice is L2 and goes through the loop; blocking findings are fixed without asking. Merging is the owner's act, and there is no automatic merge. A contract amendment is a recorded human decision under the contract's change-control section, and a contract-only pull request ends at `agent:needs-human` by design ([Contracts README](contracts/README.md), Section 2.1: contract acceptance never waits for a milestone). Agents change no Secrets, GitHub Apps, OAuth grants, or Rulesets ([AGENTS.md](../AGENTS.md)).

## 3. How to tell it is working

Two counts per owner sitting, appended to the tracking Issue's change record: pull requests merged and decisions answered. The policy holds when a sitting routinely clears more than two pull requests and a dependent slice's pull request is open within a day of its dependency merging. A sitting that finds an empty queue while a dependent slice sits unopened means rule 1 was broken; say so on the Issue.

## 4. Change record

- 2026-09-08 — adopted on the repository owner's decision, recorded on tracking Issue #68, which supersedes tracking Issue #17 rule 1 (the five-pull-request cap). #68 holds the queue and the tracks.
