## Canonical Issue

Closes #

## Behavior slice

Describe the one independently reviewable behavior in this pull request and why it is needed.

## Contract and evidence

- Contract or ADR changes:
- Fixture IDs or tests:
- Fixed SQL templates and allowed parameters affected:
- New or changed failure behavior:
- Known limitations and deferred follow-up Issues:

## Validation

List every lint, test, conformance, and read-only invariance command run, with its result. State explicitly when the repository defines no applicable check.

## Review protocol

- Review level: L0 / L1 / L2
- Writer/model (default: Claude Code):
- Independent reviewer/model (default: Codex; N/A for L0):
- Review stage: design / code or configuration / N/A
- Round 1 record: N/A / link or summary
- Round 2 final inspection: N/A / link or summary
- ChatGPT arbitration: not used / link to question and human disposition
- Required human contract/fixture review and approval record:

- [ ] The declared review level matches the change risk and affected surfaces.
- [ ] When required, the reviewer only inspected the Issue, contracts, diff, and evidence; the reviewer did not edit files.
- [ ] The review contains no more than five P0/P1-equivalent blocking findings and no lower-severity blocking comments.
- [ ] The applicable AI review stage ended after at most two rounds.
- [ ] Required human review, approval, and acceptance dispositions are recorded; the bounded model review did not replace them.
- [ ] Required CI checks pass and required review conversations are resolved.
- [ ] A human repository owner will initiate merge; no AI approval or automatic merge is used.

## Architecture and information safety

- [ ] Authoritative facts still come only from registered fixed SQL templates.
- [ ] Database access remains read-only and unsupported or ambiguous requests fail closed.
- [ ] Required `evidence_bundle`, `source_trace`, and `limitations` information is preserved.
- [ ] Adopted durable decisions are reflected in the applicable contract, ADR, or test rather than only in PR comments.
- [ ] The repository and PR discussion contain no production data, credentials, or confidential information.
