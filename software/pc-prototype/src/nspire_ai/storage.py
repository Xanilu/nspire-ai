"""Provider-neutral conversation storage with in-memory and SQLite backends."""

from __future__ import annotations

import os
import errno
import sqlite3
import stat
import tempfile
import time
import uuid
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from threading import Lock, RLock
from typing import Iterator, Protocol
from uuid import uuid4

from nspire_ai.errors import (
    ContextLimitError,
    ConversationNotFoundError,
    ConversationStorageConflictError,
    ConversationStorageCorruptionError,
    ConversationStorageError,
)
from nspire_ai.messages import Message

SCHEMA_VERSION = 1
DATABASE_FILENAME = "conversations.sqlite3"
_PATH_LOCKS: dict[str, RLock] = {}
_PATH_LOCKS_GUARD = Lock()


def _local_path_lock(path: Path) -> RLock:
    key = os.path.normcase(str(path))
    with _PATH_LOCKS_GUARD:
        return _PATH_LOCKS.setdefault(key, RLock())


def _acquire_process_lock(fd: int, timeout_ms: int) -> None:
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        try:
            if os.name == "nt":
                import msvcrt

                os.lseek(fd, 0, os.SEEK_SET)
                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
            return
        except OSError as exc:
            is_busy = (
                exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK, errno.EBUSY}
                or getattr(exc, "winerror", None) in {33, 36}
            )
            if not is_busy:
                raise
            if time.monotonic() >= deadline:
                raise ConversationStorageError("Conversation storage is busy; try again shortly.") from None
            time.sleep(0.01)


def _release_process_lock(fd: int) -> None:
    if os.name == "nt":
        import msvcrt

        os.lseek(fd, 0, os.SEEK_SET)
        msvcrt.locking(fd, msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(fd, fcntl.LOCK_UN)


@dataclass(frozen=True, slots=True)
class ConversationSnapshot:
    conversation_id: str
    messages: tuple[Message, ...]
    revision: int
    created_at: str
    updated_at: str


@dataclass(frozen=True, slots=True)
class ConversationSummary:
    conversation_id: str
    created_at: str
    updated_at: str
    message_count: int


class ConversationStore(Protocol):
    """Small persistence seam used by ConversationEngine."""

    def create(self) -> str: ...
    def load(self, conversation_id: str) -> ConversationSnapshot: ...
    def list(self) -> tuple[ConversationSummary, ...]: ...
    def commit_turn(
        self, conversation_id: str, expected_revision: int, user: Message,
        assistant: Message, *, max_history_messages: int, max_history_chars: int,
    ) -> ConversationSnapshot: ...
    def delete(self, conversation_id: str) -> None: ...
    def backup(self, destination: str | Path) -> Path: ...
    def restore_backup(self, source: str | Path) -> None: ...
    def close(self) -> None: ...


def validate_conversation_id(conversation_id: str) -> str:
    if not isinstance(conversation_id, str) or len(conversation_id) != 32:
        raise ConversationNotFoundError("Conversation was not found.")
    try:
        uuid.UUID(hex=conversation_id)
    except (ValueError, AttributeError):
        raise ConversationNotFoundError("Conversation was not found.") from None
    if conversation_id.lower() != conversation_id:
        raise ConversationNotFoundError("Conversation was not found.")
    return conversation_id


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds")


def _validate_messages(messages: tuple[Message, ...], *, max_messages: int | None = None,
                       max_chars: int | None = None) -> None:
    if len(messages) % 2:
        raise ConversationStorageCorruptionError("Stored conversation history is incomplete.")
    if max_messages is not None and len(messages) > max_messages:
        raise ConversationStorageCorruptionError("Stored conversation exceeds configured limits.")
    if max_chars is not None and sum(len(message.content) for message in messages) > max_chars:
        raise ConversationStorageCorruptionError("Stored conversation exceeds configured limits.")
    for index, message in enumerate(messages):
        expected_role = "user" if index % 2 == 0 else "assistant"
        if not isinstance(message, Message) or message.role != expected_role:
            raise ConversationStorageCorruptionError("Stored conversation history is invalid.")


def _validate_sequence(rows: list[sqlite3.Row]) -> None:
    if [row["sequence"] for row in rows] != list(range(len(rows))):
        raise ConversationStorageCorruptionError("Stored conversation sequence is invalid.")


def _prune(messages: list[Message], max_messages: int, max_chars: int) -> list[Message]:
    while messages and (
        len(messages) > max_messages
        or sum(len(message.content) for message in messages) > max_chars
    ):
        del messages[:2]
    return messages


class InMemoryConversationStore:
    """Process-local store used by direct engine construction and tests."""

    def __init__(self, *, max_conversations: int = 1_000) -> None:
        if type(max_conversations) is not int or max_conversations < 1:
            raise ValueError("Maximum conversations must be a positive integer.")
        self._max_conversations = max_conversations
        self._items: dict[str, ConversationSnapshot] = {}
        self._lock = RLock()

    def create(self) -> str:
        with self._lock:
            if len(self._items) >= self._max_conversations:
                raise ContextLimitError("The conversation limit has been reached.")
            conversation_id = uuid4().hex
            now = _now()
            self._items[conversation_id] = ConversationSnapshot(conversation_id, (), 0, now, now)
            return conversation_id

    def load(self, conversation_id: str) -> ConversationSnapshot:
        conversation_id = validate_conversation_id(conversation_id)
        with self._lock:
            snapshot = self._items.get(conversation_id)
            if snapshot is None:
                raise ConversationNotFoundError("Conversation was not found.")
            return snapshot

    def list(self) -> tuple[ConversationSummary, ...]:
        with self._lock:
            items = sorted(self._items.values(), key=lambda item: item.updated_at, reverse=True)
            return tuple(ConversationSummary(i.conversation_id, i.created_at, i.updated_at, len(i.messages)) for i in items)

    def commit_turn(self, conversation_id: str, expected_revision: int, user: Message,
                    assistant: Message, *, max_history_messages: int,
                    max_history_chars: int) -> ConversationSnapshot:
        conversation_id = validate_conversation_id(conversation_id)
        with self._lock:
            current = self._items.get(conversation_id)
            if current is None:
                raise ConversationNotFoundError("Conversation was not found.")
            if current.revision != expected_revision:
                raise ConversationStorageConflictError("Conversation changed during this request; reload and try again.")
            messages = _prune([*current.messages, user, assistant], max_history_messages, max_history_chars)
            now = _now()
            updated = ConversationSnapshot(conversation_id, tuple(messages), current.revision + 1, current.created_at, now)
            self._items[conversation_id] = updated
            return updated

    def delete(self, conversation_id: str) -> None:
        conversation_id = validate_conversation_id(conversation_id)
        with self._lock:
            if self._items.pop(conversation_id, None) is None:
                raise ConversationNotFoundError("Conversation was not found.")

    def backup(self, destination: str | Path) -> Path:
        raise ConversationStorageError("Backups are available only for persistent storage.")

    def restore_backup(self, source: str | Path) -> None:
        raise ConversationStorageError("Backup restore is available only for persistent storage.")

    def close(self) -> None:
        return None


class SQLiteConversationStore:
    """Local SQLite store with transactional turn commits and validated reads."""

    def __init__(self, data_directory: str | Path, *, max_conversations: int = 1_000,
                 max_history_messages: int = 200, max_history_chars: int = 100_000,
                 busy_timeout_ms: int = 5_000) -> None:
        if type(max_conversations) is not int or max_conversations < 1:
            raise ValueError("Maximum conversations must be a positive integer.")
        if type(max_history_messages) is not int or max_history_messages < 2 or max_history_messages % 2:
            raise ValueError("Maximum history messages must be an even positive integer of at least two.")
        if type(max_history_chars) is not int or max_history_chars < 1:
            raise ValueError("Maximum history characters must be a positive integer.")
        if type(busy_timeout_ms) is not int or busy_timeout_ms < 1:
            raise ValueError("SQLite busy timeout must be a positive integer in milliseconds.")
        try:
            self._directory = Path(data_directory).expanduser().resolve()
        except (OSError, TypeError, ValueError):
            raise ConversationStorageError("Storage directory is invalid.") from None
        self._path = self._directory / DATABASE_FILENAME
        self._lock_path = self._directory / f"{DATABASE_FILENAME}.lock"
        self._max_conversations = max_conversations
        self._max_history_messages = max_history_messages
        self._max_history_chars = max_history_chars
        self._busy_timeout_ms = busy_timeout_ms
        self._closed = False
        try:
            was_new_directory = not self._directory.exists()
            self._directory.mkdir(parents=True, exist_ok=True)
            if not self._directory.is_dir():
                raise OSError("Storage path is not a directory.")
            if was_new_directory and os.name != "nt":
                self._directory.chmod(0o700)
            if self._path.is_symlink():
                raise OSError("Database path cannot be a symbolic link.")
            if self._path.exists() and not self._path.is_file():
                raise OSError("Database path is not a regular file.")
            _check_writable_directory(self._directory)
            with self._operation_lock():
                with self._connect() as connection:
                    self._initialize(connection)
                    self._check_integrity(connection)
                    connection.execute("PRAGMA journal_mode=WAL")
            if os.name != "nt":
                self._path.chmod(0o600)
        except ConversationStorageError:
            raise
        except (OSError, sqlite3.Error) as exc:
            raise _storage_error(exc) from None

    @contextmanager
    def _operation_lock(self) -> Iterator[None]:
        """Serialize operations for this database within and across processes."""
        local_lock = _local_path_lock(self._lock_path)
        with local_lock:
            if self._closed:
                raise ConversationStorageError("Conversation storage is closed.")
            fd = -1
            acquired = False
            try:
                if self._lock_path.is_symlink():
                    raise OSError("Storage lock path cannot be a symbolic link.")
                flags = os.O_CREAT | os.O_RDWR
                if hasattr(os, "O_NOFOLLOW"):
                    flags |= os.O_NOFOLLOW
                fd = os.open(self._lock_path, flags, 0o600)
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise OSError("Storage lock path is not a regular file.")
                if os.fstat(fd).st_size == 0:
                    os.write(fd, b"\0")
                if os.name != "nt":
                    os.fchmod(fd, 0o600)
                _acquire_process_lock(fd, self._busy_timeout_ms)
                acquired = True
                yield
            except ConversationStorageError:
                raise
            except OSError as exc:
                raise _storage_error(exc) from None
            finally:
                if fd >= 0:
                    try:
                        if acquired:
                            _release_process_lock(fd)
                    except OSError as exc:
                        raise _storage_error(exc) from None
                    finally:
                        os.close(fd)

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        if self._closed:
            raise ConversationStorageError("Conversation storage is closed.")
        connection = sqlite3.connect(self._path, timeout=self._busy_timeout_ms / 1000)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys=ON")
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def _initialize(self, connection: sqlite3.Connection) -> None:
        row = connection.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='schema_info'").fetchone()
        if row is None:
            existing_objects = connection.execute(
                "SELECT name FROM sqlite_master WHERE name NOT LIKE 'sqlite_%' AND type IN ('table','index','trigger','view')"
            ).fetchall()
            if existing_objects:
                raise ConversationStorageCorruptionError("Conversation database schema is incomplete.")
            connection.execute("BEGIN IMMEDIATE")
            connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
            connection.execute("INSERT INTO schema_info(version) VALUES (0)")
            self._migrate_zero_to_one(connection)
            connection.commit()
            self._validate_schema(connection)
            return
        try:
            versions = connection.execute("SELECT version FROM schema_info").fetchall()
        except sqlite3.Error as exc:
            raise ConversationStorageCorruptionError("Conversation database schema is invalid.") from exc
        if len(versions) != 1 or type(versions[0][0]) is not int:
            raise ConversationStorageCorruptionError("Conversation database schema version is invalid.")
        version = versions[0][0]
        if version > SCHEMA_VERSION:
            raise ConversationStorageError("Conversation database was created by a newer application version.")
        if version == 0:
            self._validate_empty_v0(connection)
            connection.execute("BEGIN IMMEDIATE")
            self._migrate_zero_to_one(connection)
            connection.commit()
            version = 1
        if version != SCHEMA_VERSION:
            raise ConversationStorageError("Conversation database schema migration is not supported.")
        self._validate_schema(connection)

    @staticmethod
    def _validate_empty_v0(connection: sqlite3.Connection) -> None:
        """Only migrate the known empty v0 marker; preserve unknown schemas untouched."""
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
            )
        }
        schema_info = connection.execute("PRAGMA table_info(schema_info)").fetchall()
        actual_columns = [
            (row["name"], row["type"].upper(), row["notnull"], row["pk"], row["dflt_value"])
            for row in schema_info
        ]
        if tables != {"schema_info"} or actual_columns != [("version", "INTEGER", 1, 0, None)]:
            raise ConversationStorageCorruptionError("Version 0 database is not the known empty schema.")
        schema_sql = connection.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name='schema_info'"
        ).fetchone()
        if schema_sql is None or "".join(schema_sql[0].lower().split()) != "createtableschema_info(versionintegernotnull)":
            raise ConversationStorageCorruptionError("Version 0 database is not the known empty schema.")
        if connection.execute("SELECT 1 FROM sqlite_master WHERE type IN ('trigger','view')").fetchone():
            raise ConversationStorageCorruptionError("Version 0 database contains unsupported schema objects.")
        if connection.execute("PRAGMA index_list(schema_info)").fetchone():
            raise ConversationStorageCorruptionError("Version 0 database contains unsupported schema objects.")

    @staticmethod
    def _validate_schema(connection: sqlite3.Connection) -> None:
        """Reject schemas that do not implement the complete v1 storage contract."""
        expected_table_sql = {
            "schema_info": "CREATE TABLE schema_info (version INTEGER NOT NULL)",
            "conversations": "CREATE TABLE conversations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 0))",
            "messages": "CREATE TABLE messages (conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, sequence INTEGER NOT NULL CHECK(sequence >= 0), role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(conversation_id, sequence), CHECK(length(trim(content)) > 0))",
        }
        expected_indexes = {
            "messages": {"messages_by_conversation", "sqlite_autoindex_messages_1"},
            "conversations": {"conversations_by_updated", "sqlite_autoindex_conversations_1"},
            "schema_info": set(),
        }
        expected_columns = {
            "schema_info": [
                ("version", "INTEGER", 1, 0),
            ],
            "conversations": [
                ("id", "TEXT", 0, 1),
                ("created_at", "TEXT", 1, 0),
                ("updated_at", "TEXT", 1, 0),
                ("revision", "INTEGER", 1, 0),
            ],
            "messages": [
                ("conversation_id", "TEXT", 1, 1),
                ("sequence", "INTEGER", 1, 2),
                ("role", "TEXT", 1, 0),
                ("content", "TEXT", 1, 0),
                ("created_at", "TEXT", 1, 0),
            ],
        }
        try:
            tables = {
                row[0]
                for row in connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                )
            }
            if tables != set(expected_columns):
                raise ConversationStorageCorruptionError("Conversation database schema is incompatible.")

            unexpected_objects = connection.execute(
                "SELECT name FROM sqlite_master WHERE type IN ('trigger','view')"
            ).fetchall()
            if unexpected_objects:
                raise ConversationStorageCorruptionError("Conversation database contains unsupported schema objects.")

            actual_table_sql = {
                row["name"]: "".join(row["sql"].lower().split())
                for row in connection.execute("SELECT name, sql FROM sqlite_master WHERE type='table'")
                if row["name"] in expected_table_sql
            }
            if actual_table_sql != {
                name: "".join(statement.lower().split())
                for name, statement in expected_table_sql.items()
            }:
                raise ConversationStorageCorruptionError("Conversation database constraints are incompatible.")

            for table_name, columns in expected_columns.items():
                rows = connection.execute(f"PRAGMA table_info({table_name})").fetchall()
                actual = [(row["name"], row["type"].upper(), row["notnull"], row["pk"]) for row in rows]
                if actual != columns or any(row["dflt_value"] is not None for row in rows):
                    raise ConversationStorageCorruptionError("Conversation database columns are incompatible.")

            foreign_keys = connection.execute("PRAGMA foreign_key_list(messages)").fetchall()
            actual_foreign_keys = [
                (row["table"], row["from"], row["to"], row["on_update"].upper(), row["on_delete"].upper())
                for row in foreign_keys
            ]
            if actual_foreign_keys != [("conversations", "conversation_id", "id", "NO ACTION", "CASCADE")]:
                raise ConversationStorageCorruptionError("Conversation database cascade-delete constraint is incompatible.")

            required_indexes = {
                "messages": ("messages_by_conversation", ["conversation_id", "sequence"], [0, 0]),
                "conversations": ("conversations_by_updated", ["updated_at"], [1]),
            }
            for table_name, (index_name, columns, descending) in required_indexes.items():
                indexes = connection.execute(f"PRAGMA index_list({table_name})").fetchall()
                if {row["name"] for row in indexes} != expected_indexes[table_name]:
                    raise ConversationStorageCorruptionError("Conversation database indexes are incompatible.")
                index = next((row for row in indexes if row["name"] == index_name), None)
                if index is None or index["unique"] != 0 or index["origin"] != "c" or index["partial"] != 0:
                    raise ConversationStorageCorruptionError("Conversation database indexes are incompatible.")
                index_columns = connection.execute(f"PRAGMA index_info({index_name})").fetchall()
                if [row["name"] for row in index_columns] != columns:
                    raise ConversationStorageCorruptionError("Conversation database indexes are incompatible.")
                key_columns = [row for row in connection.execute(f"PRAGMA index_xinfo({index_name})") if row["key"]]
                if [row["desc"] for row in key_columns] != descending:
                    raise ConversationStorageCorruptionError("Conversation database index ordering is incompatible.")

            expected_index_sql = {
                "messages_by_conversation": "CREATE INDEX messages_by_conversation ON messages(conversation_id, sequence)",
                "conversations_by_updated": "CREATE INDEX conversations_by_updated ON conversations(updated_at DESC)",
            }
            for index_name, statement in expected_index_sql.items():
                row = connection.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND name=?", (index_name,)
                ).fetchone()
                if row is None or "".join(row["sql"].lower().split()) != "".join(statement.lower().split()):
                    raise ConversationStorageCorruptionError("Conversation database indexes are incompatible.")
        except ConversationStorageError:
            raise
        except sqlite3.Error:
            raise ConversationStorageCorruptionError("Conversation database schema is invalid.") from None

    @staticmethod
    def _migrate_zero_to_one(connection: sqlite3.Connection) -> None:
        """Create the first schema transactionally from an empty v0 database."""
        connection.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 0))")
        connection.execute("CREATE TABLE messages (conversation_id TEXT NOT NULL REFERENCES conversations(id) ON DELETE CASCADE, sequence INTEGER NOT NULL CHECK(sequence >= 0), role TEXT NOT NULL CHECK(role IN ('user','assistant')), content TEXT NOT NULL, created_at TEXT NOT NULL, PRIMARY KEY(conversation_id, sequence), CHECK(length(trim(content)) > 0))")
        connection.execute("CREATE INDEX messages_by_conversation ON messages(conversation_id, sequence)")
        connection.execute("CREATE INDEX conversations_by_updated ON conversations(updated_at DESC)")
        connection.execute("UPDATE schema_info SET version=?", (SCHEMA_VERSION,))

    def _check_integrity(self, connection: sqlite3.Connection) -> None:
        try:
            result = connection.execute("PRAGMA quick_check").fetchone()
        except sqlite3.Error as exc:
            raise ConversationStorageCorruptionError("Conversation database integrity check failed.") from exc
        if result is None or result[0] != "ok":
            raise ConversationStorageCorruptionError("Conversation database integrity check failed.")
        if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
            raise ConversationStorageCorruptionError("Conversation database contains invalid references.")

    def create(self) -> str:
        conversation_id = uuid4().hex
        now = _now()
        try:
            with self._operation_lock():
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
                    if count >= self._max_conversations:
                        raise ContextLimitError("The conversation limit has been reached.")
                    connection.execute("INSERT INTO conversations(id, created_at, updated_at, revision) VALUES (?, ?, ?, 0)", (conversation_id, now, now))
                    connection.commit()
            return conversation_id
        except ConversationStorageError:
            raise
        except sqlite3.Error as exc:
            raise _storage_error(exc) from None

    def load(self, conversation_id: str) -> ConversationSnapshot:
        conversation_id = validate_conversation_id(conversation_id)
        try:
            with self._operation_lock():
                return self._load_unlocked(conversation_id)
        except (ConversationNotFoundError, ConversationStorageError):
            raise
        except (ValueError, TypeError, sqlite3.Error, KeyError) as exc:
            if isinstance(exc, sqlite3.Error):
                raise _storage_error(exc) from None
            raise ConversationStorageCorruptionError("Stored conversation history is invalid.") from None

    def _load_unlocked(self, conversation_id: str) -> ConversationSnapshot:
        with self._connect() as connection:
            row = connection.execute("SELECT id, created_at, updated_at, revision FROM conversations WHERE id=?", (conversation_id,)).fetchone()
            if row is None:
                raise ConversationNotFoundError("Conversation was not found.")
            rows = connection.execute("SELECT sequence, role, content FROM messages WHERE conversation_id=? ORDER BY sequence", (conversation_id,)).fetchall()
        _validate_sequence(rows)
        messages = tuple(Message(row["role"], row["content"]) for row in rows)
        _validate_messages(messages, max_messages=self._max_history_messages, max_chars=self._max_history_chars)
        return ConversationSnapshot(row["id"], messages, row["revision"], row["created_at"], row["updated_at"])

    def list(self) -> tuple[ConversationSummary, ...]:
        try:
            with self._operation_lock():
                with self._connect() as connection:
                    rows = connection.execute("SELECT c.id, c.created_at, c.updated_at, COUNT(m.sequence) AS message_count FROM conversations c LEFT JOIN messages m ON m.conversation_id=c.id GROUP BY c.id ORDER BY c.updated_at DESC, c.id").fetchall()
                # Validate every ID and message sequence/shape before exposing metadata.
                result = []
                for row in rows:
                    conversation_id = validate_conversation_id(row["id"])
                    snapshot = self._load_unlocked(conversation_id)
                    if row["message_count"] != len(snapshot.messages):
                        raise ConversationStorageCorruptionError("Stored conversation metadata is invalid.")
                    result.append(ConversationSummary(conversation_id, row["created_at"], row["updated_at"], len(snapshot.messages)))
                return tuple(result)
        except ConversationStorageError:
            raise
        except sqlite3.Error as exc:
            raise _storage_error(exc) from None

    def commit_turn(self, conversation_id: str, expected_revision: int, user: Message,
                    assistant: Message, *, max_history_messages: int,
                    max_history_chars: int) -> ConversationSnapshot:
        conversation_id = validate_conversation_id(conversation_id)
        if user.role != "user" or assistant.role != "assistant":
            raise ValueError("A turn must contain one user message and one assistant message.")
        try:
            with self._operation_lock():
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    conversation = connection.execute("SELECT created_at, revision FROM conversations WHERE id=?", (conversation_id,)).fetchone()
                    if conversation is None:
                        raise ConversationNotFoundError("Conversation was not found.")
                    if conversation["revision"] != expected_revision:
                        raise ConversationStorageConflictError("Conversation changed during this request; reload and try again.")
                    rows = connection.execute("SELECT sequence, role, content, created_at FROM messages WHERE conversation_id=? ORDER BY sequence", (conversation_id,)).fetchall()
                    _validate_sequence(rows)
                    messages = [Message(row["role"], row["content"]) for row in rows]
                    _validate_messages(tuple(messages), max_messages=self._max_history_messages, max_chars=self._max_history_chars)
                    messages = _prune([*messages, user, assistant], max_history_messages, max_history_chars)
                    connection.execute("DELETE FROM messages WHERE conversation_id=?", (conversation_id,))
                    now = _now()
                    dropped_count = len(rows) + 2 - len(messages)
                    timestamps = [row["created_at"] for row in rows] + [now, now]
                    retained_timestamps = timestamps[dropped_count:]
                    connection.executemany("INSERT INTO messages(conversation_id, sequence, role, content, created_at) VALUES (?, ?, ?, ?, ?)", ((conversation_id, i, message.role, message.content, retained_timestamps[i]) for i, message in enumerate(messages)))
                    connection.execute("UPDATE conversations SET updated_at=?, revision=revision+1 WHERE id=?", (now, conversation_id))
                    connection.commit()
            return ConversationSnapshot(conversation_id, tuple(messages), expected_revision + 1, conversation["created_at"], now)
        except (ConversationNotFoundError, ConversationStorageError):
            raise
        except (ValueError, sqlite3.Error) as exc:
            if isinstance(exc, sqlite3.Error):
                raise _storage_error(exc) from None
            raise ConversationStorageCorruptionError("Stored conversation history is invalid.") from None

    def delete(self, conversation_id: str) -> None:
        conversation_id = validate_conversation_id(conversation_id)
        try:
            with self._operation_lock():
                with self._connect() as connection:
                    connection.execute("BEGIN IMMEDIATE")
                    cursor = connection.execute("DELETE FROM conversations WHERE id=?", (conversation_id,))
                    if cursor.rowcount == 0:
                        raise ConversationNotFoundError("Conversation was not found.")
                    connection.commit()
        except (ConversationNotFoundError, ConversationStorageError):
            raise
        except sqlite3.Error as exc:
            raise _storage_error(exc) from None

    def backup(self, destination: str | Path) -> Path:
        temporary: Path | None = None
        try:
            with self._operation_lock():
                target = Path(destination).expanduser().resolve()
                if target == self._path or target.exists():
                    raise ConversationStorageError("Backup destination already exists or is the active database.")
                target.parent.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(prefix=".nspire-ai-backup-", suffix=".tmp", dir=target.parent, delete=False) as file:
                    temporary = Path(file.name)
                if os.name != "nt":
                    temporary.chmod(0o600)
                with self._connect() as source, closing(sqlite3.connect(temporary)) as destination_db:
                    with destination_db:
                        source.backup(destination_db)
                _validate_database_file(temporary)
                published_temp = temporary
                os.link(temporary, target)
                temporary = None
                # The published hard link is complete; remove the private temporary name.
                _cleanup_temporary_file(published_temp)
                return target
        except ConversationStorageError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise _storage_error(exc, operation="backup") from None
        finally:
            if temporary is not None:
                _cleanup_temporary_file(temporary)

    def restore_backup(self, source: str | Path) -> None:
        temporary: Path | None = None
        try:
            source_path = Path(source).expanduser().resolve()
            if source_path == self._path:
                raise ConversationStorageError("Restore source must be a separate backup file.")
            _validate_database_file(
                source_path,
                max_conversations=self._max_conversations,
                max_history_messages=self._max_history_messages,
                max_history_chars=self._max_history_chars,
            )
            with self._operation_lock():
                with self._connect() as connection:
                    conversation_count = connection.execute("SELECT COUNT(*) FROM conversations").fetchone()[0]
                    message_count = connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0]
                    if conversation_count != 0 or message_count != 0:
                        raise ConversationStorageError("Restore requires an empty conversation store.")
                    self._check_integrity(connection)
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                with tempfile.NamedTemporaryFile(prefix=".nspire-ai-restore-", suffix=".tmp", dir=self._directory, delete=False) as file:
                    temporary = Path(file.name)
                if os.name != "nt":
                    temporary.chmod(0o600)
                with closing(sqlite3.connect(source_path)) as backup_db, closing(sqlite3.connect(temporary)) as restored_db:
                    with restored_db:
                        backup_db.backup(restored_db)
                _validate_database_file(
                    temporary,
                    max_conversations=self._max_conversations,
                    max_history_messages=self._max_history_messages,
                    max_history_chars=self._max_history_chars,
                )
                for suffix in ("-wal", "-shm"):
                    Path(str(self._path) + suffix).unlink(missing_ok=True)
                os.replace(temporary, self._path)
                temporary = None
        except ConversationStorageError:
            raise
        except (OSError, sqlite3.Error, TypeError, ValueError) as exc:
            raise _storage_error(exc, operation="restore") from None
        finally:
            if temporary is not None:
                _cleanup_temporary_file(temporary)

    def close(self) -> None:
        with _local_path_lock(self._lock_path):
            self._closed = True


def _check_writable_directory(directory: Path) -> None:
    fd, probe = tempfile.mkstemp(prefix=".nspire-ai-write-check-", dir=directory)
    os.close(fd)
    Path(probe).unlink()


def _cleanup_temporary_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        # Cleanup is best-effort after a failed or interrupted operation; the
        # documented recovery procedure removes only these private temp files.
        pass


def _validate_database_file(
    path: Path,
    *,
    max_conversations: int | None = None,
    max_history_messages: int | None = None,
    max_history_chars: int | None = None,
) -> None:
    try:
        if not path.is_file():
            raise ConversationStorageCorruptionError("Backup file is invalid.")
        uri = f"{path.as_uri()}?mode=ro"
        with closing(sqlite3.connect(uri, uri=True)) as connection:
            connection.row_factory = sqlite3.Row
            result = connection.execute("PRAGMA quick_check").fetchone()
            if result is None or result[0] != "ok":
                raise ConversationStorageCorruptionError("Backup integrity check failed.")
            if connection.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise ConversationStorageCorruptionError("Backup contains invalid references.")
            version = connection.execute("SELECT version FROM schema_info").fetchall()
            if len(version) != 1 or version[0][0] != SCHEMA_VERSION:
                raise ConversationStorageCorruptionError("Backup schema version is unsupported.")
            SQLiteConversationStore._validate_schema(connection)
            conversation_ids = [row[0] for row in connection.execute("SELECT id FROM conversations")]
            if max_conversations is not None and len(conversation_ids) > max_conversations:
                raise ConversationStorageCorruptionError("Backup exceeds configured conversation limits.")
            for conversation_id in conversation_ids:
                validate_conversation_id(conversation_id)
                rows = connection.execute("SELECT sequence, role, content, created_at FROM messages WHERE conversation_id=? ORDER BY sequence", (conversation_id,)).fetchall()
                _validate_sequence(rows)
                _validate_messages(
                    tuple(Message(row["role"], row["content"]) for row in rows),
                    max_messages=max_history_messages,
                    max_chars=max_history_chars,
                )
    except ConversationStorageError:
        raise
    except (OSError, sqlite3.Error, ValueError, TypeError) as exc:
        raise ConversationStorageCorruptionError("Backup database is malformed or corrupt.") from None


def _storage_error(exc: BaseException, *, operation: str = "access") -> ConversationStorageError:
    if isinstance(exc, sqlite3.OperationalError) and ("locked" in str(exc).lower() or "busy" in str(exc).lower()):
        return ConversationStorageError("Conversation storage is busy; try again shortly.")
    if (isinstance(exc, OSError) and getattr(exc, "errno", None) == 28) or "disk is full" in str(exc).lower():
        return ConversationStorageError("Conversation storage is full.")
    if isinstance(exc, sqlite3.DatabaseError) and any(
        marker in str(exc).lower() for marker in ("not a database", "malformed", "file is encrypted")
    ):
        return ConversationStorageCorruptionError("Conversation database is malformed or corrupt.")
    return ConversationStorageError(f"Could not {operation} conversation storage.")
