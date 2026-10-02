# Milestone 5: deploy records

Each deploy-mode run's record (`deploy-<commit>.json`) is committed here
after the run, with its conformance artifacts, whether the owner or the writer
session started it (`deploy-v0.1` Section 4.2, ADR-0007). A checks-mode run's
record is not committed here (Section 4.8).

The other files of a run's artifact are committed beside it in
`run-<run id>/`, byte for byte as the run uploaded them.

| Record | Run | Outcome |
| --- | --- | --- |
| [`deploy-b36303d08268b5de5872f926e33f41af5e5443e3.json`](deploy-b36303d08268b5de5872f926e33f41af5e5443e3.json), [`run-36677427212/`](run-36677427212/) | [36677427212](https://github.com/OKJ1105/evidence-first-rag/actions/runs/36677427212), the first passing deploy (2026-09-30) | `success`; deployed checks `pass`; all seven groups ran |
| [`deploy-3676cebdbc9dbb147e07127622e0e57eee23423e.json`](deploy-3676cebdbc9dbb147e07127622e0e57eee23423e.json), [`run-36970121863/`](run-36970121863/) | [36970121863](https://github.com/OKJ1105/evidence-first-rag/actions/runs/36970121863), the first deploy with the surface's own request record (#259, #268) and uvicorn's access log off (#274) (2026-10-02) | `success`; deployed checks `pass`; all seven groups ran. `secret-scan.json` and `secret-scan-record.json` state their scan limitations; `log-checks.json` states that DP-008's positive control may have been met by an earlier request's line. |
| [`deploy-2b8e38bf02e1cf5dfa5bd3c5e21ea6db95d29083.json`](deploy-2b8e38bf02e1cf5dfa5bd3c5e21ea6db95d29083.json), [`run-36986435002/`](run-36986435002/) | [36986435002](https://github.com/OKJ1105/evidence-first-rag/actions/runs/36986435002), the first deploy serving `relay-v0.1` `0.5.0`, whose prompt calls `discover_entity` for an ordinary question (#295, #296), with `0.4.0`'s CORS preflight (#293, #294) (2026-10-02) | `success`; deployed checks `pass`; all seven groups ran. `DP-012` saw one `discover_entity` call answered, where the three runs before #296 saw a text block only (#286). `secret-scan.json` and `secret-scan-record.json` state their scan limitations; `log-checks.json` states that DP-008's positive control may have been met by an earlier request's line. No `EFR_CORS_ORIGIN` is set, so no preflight is admitted yet. |
| [`deploy-4ea91ffce9843d11795967a512c34843aefe6a66.json`](deploy-4ea91ffce9843d11795967a512c34843aefe6a66.json), [`run-36997257423/`](run-36997257423/) | [36997257423](https://github.com/OKJ1105/evidence-first-rag/actions/runs/36997257423), the first deploy with the portfolio origin `https://junokaniwa.com` set on both apps (`deploy-v0.1` `0.6.3`, #301, #302) (2026-10-02) | `success`; deployed checks `pass`; all seven groups ran. `DP-019` saw both apps admit the registered origin's preflight with the four headers, and `DP-005` still saw a foreign origin refused. `DP-019` sends the `Origin` header from the runner; a call from the site's own page in a browser is not yet observed. The owner confirmed on 2026-10-02, after this run, that the site opens over HTTPS at that origin. `secret-scan.json` and `secret-scan-record.json` state their scan limitations; `log-checks.json` states that DP-008's positive control may have been met by an earlier request's line. |

`deploy-v0.1` Section 4.8's rollback target is the newest record here whose
mode is `deploy` (a record without `mode` predates the field and is a deploy),
whose outcome is `success` and whose deployed checks are `pass`.
`evidence_first_rag.deploy.deployed` reads it.

A passing record must carry `stable_digest`: `DP-011` compares a rollback's
restored state with it, and a passing record without one stops the rollback's
comparison with an error rather than passing it.

## Cost computations

`cost-<date>*.json` are not deploy records: each is one owner-run output of
`evidence_first_rag.deploy.cost`, committed unedited as `relay-v0.1` Section
8.3 requires.

- `cost-2026-09-29.json`: at the 128 KiB body bound of `relay-v0.1` `0.1.0`.
  It predates the `after_fixed_cost` block. Every after-fixed-cost ceiling is
  0: 8,000 − 6,733.50 = 1,266.50 JPY a month, or 42.22 a day, against 44.93
  for one worst-case call.
- `cost-2026-09-29-body-32k.json`: at the 32 KiB body of `0.2.0`. The
  per-call bound is 13.91 JPY at one tool call and 61.11 at five. This is the
  worst-case evidence `relay-v0.1` `0.3.0` Section 8.3 cites.

The `ceiling_section_8_3` and `ceiling_after_fixed_cost` fields in either file
are worst-case counts reported for comparison. Since `relay-v0.1` `0.3.0`
neither is registered: the daily ceiling is the 67 that Section 8.3 registers,
and spend is bounded by the workspace spend limit (ADR-0006).
