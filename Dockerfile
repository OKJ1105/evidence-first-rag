# The image the Section 4.7 local stack runs the surface in.
#
# It holds the runtime identity's process and nothing else: provisioning runs
# in its own container from this same image (see compose.yaml), so the two
# `mvp-v0.1` Section 4.3 identities are separated by process and environment
# rather than by convention.
#
# `postgresql-client` is here because `evidence_first_rag.db.provision` applies
# the committed SQL with `psql` exactly as written -- Section 3.4 makes those
# files the provisioning path rather than a description of one, so the
# provisioning container needs the binary that runs them.
FROM python:3.11-slim

# Fail on an error anywhere in a pipeline rather than reporting the last
# command's status, so a failed download cannot look like a successful build.
SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update \
    && apt-get install --no-install-recommends --yes postgresql-client \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# The dependency list first, so a change to the source does not re-resolve the
# dependencies. `.[api]` is the extra that opts into serving `api-v0.1` over
# HTTP; the adapter extra is deliberately absent -- Section 4.7 makes the
# adapter optional, and an image that always carried it would make a model
# library a dependency of a stack that answers four of five routes without one.
COPY pyproject.toml README.md ./
COPY src ./src
RUN python -m pip install --no-cache-dir --quiet -e ".[api]"

# The SQL, the fixtures and the page. Copied rather than mounted so that what
# the stack serves is what the image was built from, which is the property a
# deployment needs; the compose file mounts nothing over them.
COPY sql ./sql
COPY fixtures ./fixtures
COPY ui ./ui

# No CMD: the two services in compose.yaml each state their own, and a default
# here would be a third thing to keep in step with them.
