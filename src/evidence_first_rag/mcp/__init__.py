"""Contract `mcp-v0.1`: the tool surface a host model reaches the runtime through.

One module, `surface`, and it needs the `mcp` package, which the `api` extra
carries because this surface is served from the same process as `api-v0.1`'s
(Section 4.5). Nothing is re-exported here for the reason `api/__init__.py`
gives: an install that never asked for a server should still import the
package.
"""
