"""Contract `relay-v0.1`: the chat relay, `POST /chat`.

The relay is the one component that holds the Anthropic key (ADR-0005). It
holds no database credential and reaches facts only through `/mcp`, as any
host does. `app.py` is the route over an injected Messages API client, and
`serve.py` is the one module that reads an environment.
"""
