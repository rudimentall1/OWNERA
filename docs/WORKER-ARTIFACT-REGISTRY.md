# Worker Artifact Registry

**Status:** Initial SQLite-backed content-addressed registry implemented; lifecycle integration and operational-scale storage remain open.  
**Code:** `ownera/artifact_registry.py`  
**Tests:** `tests/test_artifact_registry.py`

## Contract

The registry accepts bounded artifact bytes with a task ID, worker ID, plain artifact filename, and optional media type. It computes SHA-256 itself. Callers cannot choose the content address.

- Blob bytes are stored once per SHA-256 digest.
- Artifact records bind a blob to task, worker, filename, media type, and creation time.
- Identical bytes across tasks deduplicate to one blob and can have multiple provenance records.
- A changed output under the same filename receives a new digest and a separate record.
- Reads recompute SHA-256 and compare the byte count before returning content.
- Missing blobs and integrity failures raise explicit errors.

## Persistence and trust boundaries

The first version uses SQLite BLOB storage so blob insertion and provenance metadata commit in one database transaction. It uses WAL mode and synchronous FULL. This is appropriate for a bounded, single-node MVP, not a high-volume artifact platform.

The default maximum artifact size is 16 MiB and can be lowered or raised by the embedding application. A production deployment must set limits based on workload and disk budget. Database backups must include the SQLite database and its WAL state using a SQLite-consistent backup procedure.

The digest proves byte identity, not authorship, correctness, malware-freedom, or customer acceptance. Worker identity is metadata supplied by the trusted caller; the registry does not authenticate workers. The registry does not yet enforce task ownership or accepted-task lifecycle state.

No HTTP endpoint, object-store replication, retention/deletion policy, malware scanning, encryption-at-rest policy, or independent reviewer workflow is implemented here. The registry is not yet connected to Docker artifact extraction or PersistentWorkforce.

## Acceptance criteria

- [x] Content address is computed from bytes using SHA-256.
- [x] Identical content is stored once while retaining separate task provenance.
- [x] Reads validate both stored length and digest.
- [x] Metadata survives registry reopen.
- [x] Path-like artifact names and unsafe identifiers are rejected.
- [x] Per-artifact size limit is enforced.
- [ ] Run unit tests and CI on the repository commit.
- [ ] Integrate verified runtime outputs into the registry.
- [ ] Bind artifact digests into task submission and independent review evidence.
- [ ] Define retention, backup, encryption-at-rest, and disk quota operations.
