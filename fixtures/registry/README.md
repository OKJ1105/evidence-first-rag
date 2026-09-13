# Registry fixtures

The registered inputs for [Milestone 3 Entity Discovery Contract v0.1](../../docs/contracts/entity-discovery-v0.1.md), Sections 4.1 and 4.2: the approved entity registry. Two JSON Lines files, one per authored table, one line per row. The other two Section 4.1 tables, `entity_match_term` and `entity_registry_state`, are derived at load and have no file.

They live in this subdirectory rather than beside the `mvp-v0.1` files because `scripts/checks/test_validate_fixtures.py` pins `fixtures/*.jsonl` to exactly the four `mvp-v0.1` tables. Section 4.2 asks for the files "under `fixtures/`", which this satisfies. The structural checks `validate_fixtures.py` does for those files are done for these by the parser (`src/evidence_first_rag/db/registry_fixtures.py`) and by `tests/test_db_registry_fixtures.py`, which names the Section 8.1 case each row keeps reachable.

Every identifier is synthetic and uses the `SAMPLE_*` convention. `approval_reference` is opaque to the runtime and is a `SAMPLE_*` string here for the same reason.

## Reading a row

Rows name their entity by the Section 4.2 canonical reference of the occurrence — the four scope dimensions and `message_key`, plus `signal_key` for a signal — never by a surrogate. The registry is an **allowlist**: an occurrence can be loaded by the `mvp-v0.1` files and absent here, and Section 4.2 rule 4 says that absence from the registry is not absence from the data.

| File | Row |
| --- | --- |
| `approved_entity.jsonl` | `entity_kind` (`message` or `signal`), `reference`, `approval_reference`, `approved_at`. One row per occurrence discovery may return. |
| `approved_alias.jsonl` | `entity_kind` and `reference` of the entity, `alias_text` (byte-exact, not normalized), `alias_kind` (`approved_alias` or `spelling_variant`), `asserting_snapshot`, `approval_reference`, `approved_at`. |

`asserting_snapshot` is always the entity's own snapshot: Section 4.2 rule 1 refuses anything else at load, because an alias asserted by another snapshot would be a cross-snapshot claim, which Charter Section 3.6 makes a `signal_mapping` relation and never a naming fact. The column is still written out rather than implied, because it is a column of the table and a reader should not have to know the rule to read the file.

## What each row is for

Section 8.1 registers twenty-three cases. These rows carry the ones that depend on registry data; the request-only cases (`DX-010` to `DX-014`) and the selection cases (`DX-017` to `DX-023`) are registered with the route slices. Scope values are abbreviated; the files carry the full `SAMPLE_*` names.

| Case | Structure that makes it reachable |
| --- | --- |
| `DX-001` | `SAMPLE_MSG_ENGINE_STATUS` in `POWERTRAIN / SNAP_BASE` is approved, and no alias in that scope and kind equals it, so the key is unique at tier 1. |
| `DX-002` | `SAMPLE_ALIAS_GEARBOX_STATE`, an `approved_alias` on `SAMPLE_MSG_TRANSMISSION_STATE`. |
| `DX-003` | `SAMPLE_MSG_TRANSMISION_STATE`, a `spelling_variant` on the same message. |
| `DX-004` | `SAMPLE_SIG_GEAR_POSITION` is one signal's lookup key **and** the approved alias of `SAMPLE_SIG_FAULT_CODE`, both in `POWERTRAIN / SNAP_BASE`. Section 4.7 makes that term abstain into two candidates; Section 4.1 refuses a unique constraint on `alias_text` alone so that this row can exist. |
| `DX-005` | `SAMPLE_SIG_TEMPERATURE` is approved under both `SAMPLE_MSG_ENGINE_STATUS` and `SAMPLE_MSG_TRANSMISSION_STATE` in one snapshot. Without `parent_message_key`, two candidates. |
| `DX-006` | `SAMPLE_MSG_ENGINE_STATUS` is approved in both `POWERTRAIN` snapshots, so a fully scoped request resolves in one only. |
| `DX-007` | No alias equals `sample_msg_engine_status`, so the case-only variant of the `DX-001` key reaches tier 3 and never tier 2. |
| `DX-008` | `engine speed` normalizes to tokens contained in `SAMPLE_SIG_ENGINE_SPEED`'s, and equals no `match_text`, so the target is a tier-4 candidate. Its alias `SAMPLE_ALIAS_ENGINE_ROTATION_SPEED` contains them too and adds no second candidate: Section 4.6 lists one entity once. |
| `DX-009` | A term matching nothing at any tier. Nothing in the registry contains the token `nothing`. |
| `DX-015` | `SAMPLE_MSG_DIAGNOSTIC_EVENT` and both `SAMPLE_SIG_WHEEL_SPEED_FR` occurrences are loaded and **not** approved, in snapshots that do hold approved entities — so the case is "absent from the registry", not "absent from the data". |
| `DX-020` | `SAMPLE_ALIAS_WHEEL_SPEEDS` is asserted by `CHASSIS / REV_A / SNAP_BASE`, which is superseded. |

## The rows the Milestone 3 evaluation set needs

Six rows carry no `DX-*` case. They exist so that a set satisfying Section 4.10's authoring rules can be drawn from these files: rule 4 asks for five cases per class and rule 6 makes every case term distinct after normalization, and `Q-EXACT`, `Q-ALIAS` and `Q-COLLIDE` must each draw five terms that this registry holds. The pools were four, four and three.

| Row | Pool it completes |
| --- | --- |
| `SAMPLE_MSG_BRAKE_STATUS`, `SAMPLE_SIG_BRAKE_PRESSURE`, `SAMPLE_SIG_CLUTCH_STATE` (the occurrences `mvp-v0.1` `0.6.1` adds) | `Q-EXACT`: a key approved in one snapshot that reaches exactly one entity at tiers 1–2 |
| `SAMPLE_SIG_ENGINE_SPEED` and `SAMPLE_SIG_TEMPERATURE` in `POWERTRAIN / SNAP_REVISED` (occurrences already loaded) | `Q-COLLIDE`: approving them makes each key present in two snapshots |
| `SAMPLE_ALIAS_COOLANT_TEMPERATURE` on `SAMPLE_SIG_TEMPERATURE` under `SAMPLE_MSG_ENGINE_STATUS` | `Q-ALIAS`: an alias that resolves at tier 2 an entity its own key cannot resolve, since `SAMPLE_SIG_TEMPERATURE` is `DX-005`'s two-parent collision |

`Q-NOMATCH`'s five terms are names reserved as absent in [`fixtures/README.md`](../README.md), not rows here. **Nothing above registers a case or a number**: Section 8.3 stays reserved, and `tests/test_db_registry_fixtures.py` asserts pools rather than a set.

**`DX-016` is not reachable from these rows**, and `tests/test_db_registry_fixtures.py` pins that fact rather than hiding it. Section 4.6 counts entities, not aliases, and the largest kind-in-snapshot group among the `mvp-v0.1` occurrences is seven signals; eleven are needed. Reaching it takes either more `signal_occurrence` rows (a patch version of `mvp-v0.1` under its Section 10) or a fixture tree built by the test that needs it. See #141.

## Checking

```
python3 -m unittest tests.test_db_registry_fixtures
python3 -m evidence_first_rag.db.provision --recreate && python3 -m evidence_first_rag.db.invariants
```
