# Milestone 5: deploy records

Each owner-started deploy's record (`deploy-<commit>.json`) is committed here
after the run, with its conformance artifacts. `deploy-v0.1` Section 4.8's
rollback target is the newest record here whose outcome is `success` and whose
deployed checks are `pass`; `evidence_first_rag.deploy.deployed` reads it.
