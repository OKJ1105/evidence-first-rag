# ADR-0001: PostgreSQL Runtime and Normalized Fixture Boundary

**Status:** Accepted at Milestone 0, 2026-08-12. See [Milestone 0 Acceptance Record](../acceptance/milestone-0.md).

**Date:** 2026-08-09

## Context

The portfolio project targets a production-oriented architecture using PostgreSQL locally and Azure Database for PostgreSQL Flexible Server behind an application deployed to Azure App Service. Using one runtime database engine reduces dialect and adapter divergence while preserving a local development path.

The public project also needs reproducible synthetic data without copying production records or making raw DBC and ARXML ingestion a prerequisite for the core runtime.

## Decision

- PostgreSQL is the only required runtime database for the initial implementation and deployment path.
- Milestone 1 uses a reproducible local PostgreSQL environment populated from version-controlled, normalized synthetic fixtures.
- The Milestone 1 compatibility boundary is restricted to capabilities available on the declared Azure Database for PostgreSQL Flexible Server target.
- Repeatable provisioning from the same versioned schema and fixtures produces the same logical rows, constraints, contract-visible values, and normalized registered-query ordering. Identical surrogate keys are required only if a public contract exposes them.
- Schema creation and fixture loading use a controlled setup path that is separate from the application runtime.
- The application runtime uses a dedicated least-privilege, read-only database identity.
- Milestone 5 deploys the same PostgreSQL schema, normalized data meaning, fixed SQL templates, and runtime contracts to Azure App Service and Azure Database for PostgreSQL Flexible Server.
- Raw DBC and ARXML ingestion adapters are optional, deferred extensions. If added, an adapter must satisfy the current normalized contract and pass dedicated provenance and tests; a required contract change is an ADR-level decision rather than assumed adapter parity.
- Source traces describe actual synthetic fixture provenance and do not cite raw artifacts that are absent from the public repository.

## Consequences

- SQLite-specific schema, safeguards, builders, and expected evidence are outside the implementation boundary.
- Read-only invariance must be demonstrated through PostgreSQL roles, privileges, transaction behavior, and database-state checks.
- Local and Azure environments share one database engine and one semantic contract, reducing adapter and SQL-dialect divergence.
- Schema, fixtures, SQL, code, names, and examples are newly authored for this repository, with synthetic data throughout.
- The exact PostgreSQL version, extensions, provisioning tool, fixture serialization, key-generation strategy, ordering and collation strategy, Azure identity, networking, and service sizing remain contract decisions for Milestones 1 and 5.
