# Fixtures

The registered inputs for [MVP Runtime Contract v0.1](../docs/contracts/mvp-v0.1.md), Section 4.11. One JSON Lines file per Section 4.1 table, one line per row.

Every identifier is synthetic and uses the `SAMPLE_*` convention. Nothing here describes a real vehicle, network, or product.

## Reading a row

Rows reference each other by the Section 4.2 canonical natural keys, never by a surrogate value. Surrogate keys are PostgreSQL identity columns assigned at load time; Section 6 permits them to differ between provisioning runs, so a fixture that named one would not be reproducible.

| File | Names its parent by |
| --- | --- |
| `source_snapshot.jsonl` | — . `superseded_by` is a snapshot reference or `null`. |
| `message_occurrence.jsonl` | `snapshot`: the four scope dimensions. |
| `signal_occurrence.jsonl` | `message`: the four scope dimensions plus `message_key`. |
| `signal_mapping.jsonl` | `asserting_snapshot`, and `source_signal` / `target_signal` as full signal references. |

## The snapshots

| Scope | Superseded by | `ingested_at` |
| --- | --- | --- |
| `ALPHA / REV_A / POWERTRAIN / SNAP_BASE` | — | 2026-02-01 |
| `ALPHA / REV_A / POWERTRAIN / SNAP_REVISED` | — | 2026-01-04 |
| `ALPHA / REV_A / CHASSIS / SNAP_BASE` | `ALPHA / REV_B / CHASSIS / SNAP_BASE` | 2026-01-15 |
| `ALPHA / REV_B / CHASSIS / SNAP_BASE` | — | 2026-03-01 |

Scope values are abbreviated here; the files carry the full `SAMPLE_*` names.

**`SNAP_REVISED` is older than `SNAP_BASE`, deliberately.** Section 4.2 forbids the runtime from resolving scope by newest `ingested_at`, highest `revision_label`, or the only loaded row. If the newest snapshot were also the one a correct runtime returns, an implementation that quietly sorts by `ingested_at` would pass by luck. Here the two orders disagree, so that implementation returns the wrong snapshot and the fixture catches it. `validate_fixtures.py` asserts the disagreement, so it cannot be tidied away later.

## What each row is for

Section 8.1 names fifteen cases. These files carry the ten that depend on data. `FX-108` through `FX-112` are properties of a request, not of the database, and are registered with the route and adapter slices.

| Case | Structure that makes it reachable |
| --- | --- |
| `FX-001` | Any message occurrence. |
| `FX-002` | Any signal occurrence. |
| `FX-003` | `SAMPLE_SIG_ENGINE_SPEED` is the source of two mappings, so a mapping query returns more than one row. |
| `FX-101` | `SAMPLE_MSG_ENGINE_STATUS` exists in both POWERTRAIN snapshots with different `transmit_period_ms`, and `SAMPLE_MSG_WHEEL_SPEED` exists in both CHASSIS snapshots. The differing period is what makes "resolved to the requested snapshot only" observable rather than merely asserted. Both messages keep `frame_identifier` 256 and 768 across snapshots, which is the Section 4.1 note that a frame identifier is not an identity column. |
| `FX-102` | `SAMPLE_SIG_TEMPERATURE` appears under two parent messages in the same snapshot, with different `scale_factor` and `scale_offset`. This is the case a snapshot-level unique constraint on `signal_key` would break, which Section 4.1 prohibits. |
| `FX-103` | `SAMPLE_SIG_TEMPERATURE` and several others are the source of no mapping, so a mapping lookup can return `not_found` against a resolved, covered snapshot. |
| `FX-104` | `SAMPLE_MAP_WHEEL_FL_CARRYOVER` is asserted by the superseded CHASSIS snapshot and crosses into `REV_B`. Continuity between the two `SAMPLE_SIG_WHEEL_SPEED_FL` occurrences is carried by this row, not inferred from the equal `signal_key` — which is the Section 4.2 rule the row exists to exercise. |
| `FX-105` | The two POWERTRAIN snapshots share `(project_code, revision_label, network_name)` and differ only in `snapshot_label`, so a request that omits `snapshot_label` has two candidates and must return `ambiguous`. |
| `FX-106` | `SAMPLE_NET_BODY` appears in no snapshot, so a request naming it is a coverage gap rather than an empty result. |
| `FX-107` | `SAMPLE_MSG_ABSENT` and `SAMPLE_SIG_ABSENT` appear nowhere, and the CHASSIS snapshots resolve unambiguously while carrying rows. Both halves matter: without a snapshot that resolves to exactly one candidate, a missing key would be a `coverage_gap` rather than the `not_found` this case tests, which is the distinction Section 5 draws between them. |

The three names above are reserved as absent. `validate_fixtures.py` fails if a later change adds one, because adding it would silently turn a negative case positive.

## Nulls

`transmit_period_ms` is null on the event-mode message, and `unit_label` is null on two signals. Section 6 requires every registered template to write `NULLS LAST` explicitly rather than rely on a database default, so the fixtures have to contain nulls in orderable columns for that clause to mean anything.

## Checking

```
python3 scripts/checks/validate_fixtures.py
python3 scripts/checks/test_validate_fixtures.py
```

The first validates these files against Sections 4.1, 4.2, 4.11, and 8.1. The second breaks each rule on a copy and asserts the first one notices — a validator nobody has seen fail is a validator nobody knows works. Both run in CI and in the agent loop's checks.

No database is involved. Loading these files, and the Section 4.11 rule that a bad reference aborts provisioning with no partial load, belong to the provisioning slice.
