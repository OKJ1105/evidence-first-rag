"""The registered Section 8.1 workflow rows, driven against a running stack.

`tests/` runs them over fakes, `tests_database/` over a provisioned database
in-process, and this tree over HTTP against the stack `compose.yaml` starts --
which is what `api-v0.1` Section 8's acceptance row for Section 4.7 asks for:
"the stack provisions from a clean state and `WF-001` to `WF-015` pass against
it".
"""
