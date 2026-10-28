# Milestone 1 completion ledger

Specification: ../milestone-1-crawler-implementation.md

User smoke: 10 discoveries, 14 version metadata, 10 reference snapshots,
7 source successes, 2 source HTTP 429 failures, 5 payload_or_transport failures.
429 is confirmed server throttling. The other errors cannot be reconstructed
from the legacy error code; preserve staged payloads and provide offline diagnosis.

Remaining: precise diagnostics; CSV migration; recovery and pagination;
models/config; scheduler/redirects; source guards; metrics/export;
full-range CLI, refresh, notebook and comprehensive offline verification.
