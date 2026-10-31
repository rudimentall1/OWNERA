"""Content-addressed, integrity-checked artifact storage for OWNERA workers.

The initial implementation stores immutable artifact bytes and metadata in one
SQLite database. This gives atomic blob/metadata commits and simple single-node
durability. It is intentionally not a distributed object store.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


class ArtifactRegistryError(RuntimeError):
    """Base error for artifact registry operations."""


class ArtifactIntegrityError(ArtifactRegistryError):
    """Stored bytes do not match their content address."""


class ArtifactNotFoundError(ArtifactRegistryError):
    """The requested artifact digest is not registered."""


@dataclass(frozen=True)
class ArtifactRecord:
    sha256: str
    size_bytes: int
    task_id: str
    worker_id: str
    artifact_name: str
    created_at: datetime
    media_type: str | None = None


class SQLiteArtifactRegistry:
    """SQLite-backed immutable artifact registry with SHA-256 addressing."""

    DEFAULT_MAX_ARTIFACT_BYTES = 16 * 1024 * 1024
    _IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,127}$")
    _DIGEST = re.compile(r"^[a-f0-9]{64}$")

    def __init__(
        self,
        database_path: str | Path,
        *,
        max_artifact_bytes: int = DEFAULT_MAX_ARTIFACT_BYTES,
    ) -> None:
        if max_artifact_bytes < 1:
            raise ValueError("max_artifact_bytes must be positive")
        self.database_path = str(database_path)
        if self.database_path == ":memory:":
            raise ValueError("use a file-backed SQLite database for durable artifact storage")
        Path(self.database_path).parent.mkdir(parents=True, exist_ok=True)
        self.max_artifact_bytes = max_artifact_bytes
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(
            self.database_path, timeout=10, isolation_level=None
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 10000")
        connection.execute("PRAGMA journal_mode = WAL")
        connection.execute("PRAGMA synchronous = FULL")
        return connection

    def _initialize(self) -> None:
        connection = self._connect()
        try:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_artifact_blobs (
                    sha256 TEXT PRIMARY KEY CHECK(length(sha256) = 64),
                    size_bytes INTEGER NOT NULL CHECK(size_bytes >= 0),
                    content BLOB NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS worker_artifact_records (
                    record_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    sha256 TEXT NOT NULL REFERENCES worker_artifact_blobs(sha256),
                    task_id TEXT NOT NULL,
                    worker_id TEXT NOT NULL,
                    artifact_name TEXT NOT NULL,
                    media_type TEXT,
                    created_at TEXT NOT NULL,
                    UNIQUE(task_id, worker_id, artifact_name, sha256)
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_worker_artifacts_task
                ON worker_artifact_records(task_id, created_at, record_id)
                """
            )
        finally:
            connection.close()

    @classmethod
    def _validate_identifier(cls, value: str, field: str) -> None:
        if not isinstance(value, str) or not cls._IDENTIFIER.fullmatch(value):
            raise ValueError(f"{field} must be 1-128 safe identifier characters")

    @staticmethod
    def _validate_name(value: str) -> None:
        if (
            not isinstance(value, str)
            or not value
            or len(value) > 255
            or value in {".", ".."}
            or "/" in value
            or "\\" in value
            or any(ord(char) < 32 for char in value)
        ):
            raise ValueError("artifact_name must be a plain filename, not a path")

    def put(
        self,
        *,
        task_id: str,
        worker_id: str,
        artifact_name: str,
        content: bytes,
        media_type: str | None = None,
    ) -> ArtifactRecord:
        self._validate_identifier(task_id, "task_id")
        self._validate_identifier(worker_id, "worker_id")
        self._validate_name(artifact_name)
        if not isinstance(content, bytes):
            raise TypeError("content must be bytes")
        if len(content) > self.max_artifact_bytes:
            raise ValueError("artifact exceeds configured size limit")
        if media_type is not None and (
            not isinstance(media_type, str) or len(media_type) > 255
            or any(ord(char) < 32 for char in media_type)
        ):
            raise ValueError("media_type must be a safe string of at most 255 characters")

        digest = hashlib.sha256(content).hexdigest()
        created_at = datetime.now(timezone.utc).isoformat()
        connection = self._connect()
        try:
            connection.execute("BEGIN IMMEDIATE")
            blob = connection.execute(
                "SELECT size_bytes, content FROM worker_artifact_blobs WHERE sha256 = ?",
                (digest,),
            ).fetchone()
            if blob is None:
                connection.execute(
                    "INSERT INTO worker_artifact_blobs(sha256, size_bytes, content) VALUES (?, ?, ?)",
                    (digest, len(content), sqlite3.Binary(content)),
                )
            else:
                existing = bytes(blob["content"])
                if blob["size_bytes"] != len(content) or hashlib.sha256(existing).hexdigest() != digest:
                    raise ArtifactIntegrityError("existing content-addressed blob failed integrity check")
                if existing != content:
                    raise ArtifactIntegrityError("SHA-256 collision or corrupted existing blob")
            connection.execute(
                """
                INSERT OR IGNORE INTO worker_artifact_records
                    (sha256, task_id, worker_id, artifact_name, media_type, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (digest, task_id, worker_id, artifact_name, media_type, created_at),
            )
            row = connection.execute(
                """
                SELECT sha256, size_bytes, task_id, worker_id, artifact_name, media_type, created_at
                FROM worker_artifact_records
                WHERE task_id = ? AND worker_id = ? AND artifact_name = ? AND sha256 = ?
                """,
                (task_id, worker_id, artifact_name, digest),
            ).fetchone()
            connection.commit()
            return self._to_record(row)
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def get(self, digest: str) -> bytes:
        if not isinstance(digest, str) or not self._DIGEST.fullmatch(digest):
            raise ValueError("sha256 must be 64 lowercase hexadecimal characters")
        connection = self._connect()
        try:
            row = connection.execute(
                "SELECT size_bytes, content FROM worker_artifact_blobs WHERE sha256 = ?",
                (digest,),
            ).fetchone()
        finally:
            connection.close()
        if row is None:
            raise ArtifactNotFoundError(f"artifact not found: {digest}")
        content = bytes(row["content"])
        if len(content) != row["size_bytes"] or hashlib.sha256(content).hexdigest() != digest:
            raise ArtifactIntegrityError(f"artifact integrity check failed: {digest}")
        return content

    def list_for_task(self, task_id: str) -> tuple[ArtifactRecord, ...]:
        self._validate_identifier(task_id, "task_id")
        connection = self._connect()
        try:
            rows = connection.execute(
                """
                SELECT sha256, size_bytes, task_id, worker_id, artifact_name, media_type, created_at
                FROM worker_artifact_records
                WHERE task_id = ?
                ORDER BY created_at, record_id
                """,
                (task_id,),
            ).fetchall()
            return tuple(self._to_record(row) for row in rows)
        finally:
            connection.close()

    def verify(self, digest: str) -> bool:
        self.get(digest)
        return True

    @staticmethod
    def _to_record(row: sqlite3.Row) -> ArtifactRecord:
        return ArtifactRecord(
            sha256=row["sha256"],
            size_bytes=row["size_bytes"],
            task_id=row["task_id"],
            worker_id=row["worker_id"],
            artifact_name=row["artifact_name"],
            created_at=datetime.fromisoformat(row["created_at"]),
            media_type=row["media_type"],
        )
