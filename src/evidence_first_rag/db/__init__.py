"""The database half of contract `mvp-v0.1`: provisioning, loading, and the
data-level invariant check.

Section 4.3 separates the provisioning identity from the runtime identity, and
nothing here is used by the query path. The runtime never holds the
provisioning credentials, so the runtime never imports this package.
"""
