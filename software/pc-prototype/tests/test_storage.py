import sqlite3
import os
import stat
import multiprocessing
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from threading import Event, Thread, current_thread

import pytest

from nspire_ai import (
    ConversationStorageConflictError,
    ConversationStorageCorruptionError,
    ConversationStorageError,
    Settings,
    create_conversation_engine,
)
from nspire_ai.conversations import ConversationEngine
from nspire_ai.errors import ConversationNotFoundError, ConversationProviderError
from nspire_ai.providers.base import ProviderResponse
from nspire_ai.providers.mock import MockProvider
from nspire_ai.storage import DATABASE_FILENAME, SCHEMA_VERSION, SQLiteConversationStore
from nspire_ai import storage as storage_module
from nspire_ai.messages import Message


def persistent_engine(path, *, provider=None, **settings_overrides):
    settings = Settings(data_dir=path, **settings_overrides)
    return create_conversation_engine(settings, provider=provider or MockProvider())


def create_v1_database_with_foreign_key(database, *, on_delete=None):
    reference = (
        f" REFERENCES conversations(id) ON DELETE {on_delete}"
        if on_delete is not None
        else ""
    )
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info VALUES (1)")
        connection.execute("CREATE TABLE conversations (id TEXT PRIMARY KEY, created_at TEXT NOT NULL, updated_at TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision >= 0))")
        connection.execute(
            "CREATE TABLE messages ("
            f"conversation_id TEXT NOT NULL{reference}, "
            "sequence INTEGER NOT NULL CHECK(sequence >= 0), "
            "role TEXT NOT NULL CHECK(role IN ('user','assistant')), "
            "content TEXT NOT NULL, created_at TEXT NOT NULL, "
            "PRIMARY KEY(conversation_id, sequence), CHECK(length(trim(content)) > 0))"
        )
        connection.execute("CREATE INDEX messages_by_conversation ON messages(conversation_id, sequence)")
        connection.execute("CREATE INDEX conversations_by_updated ON conversations(updated_at DESC)")


def _create_conversation_in_process(data_directory, ready, start, lock_blocked, results):
    original_acquire = storage_module._acquire_process_lock

    def observe_lock_acquisition(fd, timeout_ms):
        try:
            original_acquire(fd, 0)
        except ConversationStorageError:
            lock_blocked.set()
            original_acquire(fd, timeout_ms)

    storage_module._acquire_process_lock = observe_lock_acquisition
    store = SQLiteConversationStore(data_directory)
    ready.set()
    if not start.wait(10):
        results.put(("error", "start timeout"))
        return
    try:
        results.put(("created", store.create()))
    except BaseException as exc:
        results.put(("error", type(exc).__name__))
    finally:
        store.close()


def test_factory_persists_conversation_across_engine_restarts(tmp_path):
    first_engine = persistent_engine(tmp_path)
    conversation_id = first_engine.create_conversation()
    first_engine.send_message(conversation_id, "first question")
    first_engine.close()

    second_engine = persistent_engine(tmp_path)
    assert [message.content for message in second_engine.get_history(conversation_id)] == [
        "first question",
        "Mock provider received: first question",
    ]
    second_engine.send_message(conversation_id, "follow up")
    assert len(second_engine.get_history(conversation_id)) == 4
    second_engine.close()


def test_listing_and_logical_deletion(tmp_path):
    engine = persistent_engine(tmp_path)
    older = engine.create_conversation()
    newer = engine.create_conversation()
    engine.send_message(older, "question")
    summaries = engine.list_conversations()
    assert [item.conversation_id for item in summaries] == [older, newer]
    assert summaries[0].message_count == 2
    engine.delete_conversation(older)
    assert [item.conversation_id for item in engine.list_conversations()] == [newer]
    with pytest.raises(ConversationNotFoundError):
        engine.get_history(older)
    engine.close()


def test_direct_engine_and_factory_memory_only_option_remain_ephemeral(tmp_path):
    direct = ConversationEngine(MockProvider())
    conversation_id = direct.create_conversation()
    direct.close()

    first = persistent_engine(tmp_path, persistence_enabled=False)
    memory_id = first.create_conversation()
    first.close()
    second = persistent_engine(tmp_path, persistence_enabled=False)
    with pytest.raises(ConversationNotFoundError):
        second.get_history(memory_id)
    second.close()
    assert not (tmp_path / DATABASE_FILENAME).exists()


def test_provider_failure_and_invalid_response_do_not_commit_turn(tmp_path):
    class FailingProvider:
        def generate_messages(self, messages):
            raise RuntimeError("private provider details")

    engine = persistent_engine(tmp_path, provider=FailingProvider())
    conversation_id = engine.create_conversation()
    with pytest.raises(ConversationProviderError) as caught:
        engine.send_message(conversation_id, "question")
    assert "private" not in str(caught.value)
    assert engine.get_history(conversation_id) == ()
    engine.close()

    class InvalidProvider:
        def generate_messages(self, messages):
            return ProviderResponse("", "test")

    engine = persistent_engine(tmp_path, provider=InvalidProvider())
    with pytest.raises(ConversationProviderError):
        engine.send_message(conversation_id, "question")
    assert engine.get_history(conversation_id) == ()
    engine.close()


def test_storage_failure_rolls_back_both_messages_in_turn(tmp_path):
    engine = persistent_engine(tmp_path)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "existing")
    before = engine.get_history(conversation_id)
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        connection.execute(
            "CREATE TRIGGER reject_assistant BEFORE INSERT ON messages "
            "WHEN NEW.role='assistant' BEGIN SELECT RAISE(ABORT, 'injected storage failure'); END"
        )
    with pytest.raises(ConversationStorageError):
        engine.send_message(conversation_id, "must roll back")
    assert engine.get_history(conversation_id) == before
    engine.close()


def test_history_pruning_preserves_whole_turns_after_restart(tmp_path):
    engine = persistent_engine(tmp_path, max_history_messages=2)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "first")
    engine.send_message(conversation_id, "second")
    engine.close()
    reopened = persistent_engine(tmp_path, max_history_messages=2)
    assert [item.content for item in reopened.get_history(conversation_id)] == [
        "second",
        "Mock provider received: second",
    ]
    reopened.close()


def test_existing_message_creation_times_are_preserved_on_new_turn(tmp_path):
    engine = persistent_engine(tmp_path)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "first")
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        first_times = connection.execute(
            "SELECT created_at FROM messages WHERE conversation_id=? ORDER BY sequence",
            (conversation_id,),
        ).fetchall()
    engine.send_message(conversation_id, "second")
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        all_times = connection.execute(
            "SELECT created_at FROM messages WHERE conversation_id=? ORDER BY sequence",
            (conversation_id,),
        ).fetchall()
    assert all_times[:2] == first_times
    engine.close()


def test_revision_conflict_does_not_overwrite_newer_history(tmp_path):
    store_a = SQLiteConversationStore(tmp_path)
    store_b = SQLiteConversationStore(tmp_path)
    conversation_id = store_a.create()
    snapshot = store_a.load(conversation_id)
    store_b.commit_turn(
        conversation_id, snapshot.revision,
        Message("user", "newer"),
        Message("assistant", "answer"),
        max_history_messages=20, max_history_chars=1000,
    )
    with pytest.raises(ConversationStorageConflictError):
        store_a.commit_turn(
            conversation_id, snapshot.revision,
            Message("user", "stale"),
            Message("assistant", "stale answer"),
            max_history_messages=20, max_history_chars=1000,
        )
    assert [message.content for message in store_a.load(conversation_id).messages] == ["newer", "answer"]
    store_a.close()
    store_b.close()


def test_concurrent_sends_in_one_engine_commit_without_lost_turns(tmp_path):
    engine = persistent_engine(tmp_path)
    conversation_id = engine.create_conversation()
    with ThreadPoolExecutor(max_workers=4) as executor:
        list(executor.map(lambda n: engine.send_message(conversation_id, f"question {n}"), range(12)))
    history = engine.get_history(conversation_id)
    assert len(history) == 24
    assert all(history[index].role == "user" and history[index + 1].role == "assistant" for index in range(0, 24, 2))
    engine.close()


def test_backup_and_restore_work_with_wal_and_preserve_conversation(tmp_path):
    original_dir = tmp_path / "original"
    backup_path = tmp_path / "backup.sqlite3"
    engine = persistent_engine(original_dir)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "backup me")
    assert engine.backup(str(backup_path)) == str(backup_path)
    engine.close()

    restored = persistent_engine(tmp_path / "restored")
    restored.restore_backup(str(backup_path))
    assert [message.content for message in restored.get_history(conversation_id)] == [
        "backup me",
        "Mock provider received: backup me",
    ]
    restored.close()


def test_backup_snapshot_is_stable_while_a_writer_waits_to_commit(tmp_path, monkeypatch):
    provider_started = Event()
    release_provider = Event()
    backup_snapshot_ready = Event()
    release_backup = Event()
    writer_lock_blocked = Event()
    writer_entered_critical = Event()
    writer_done = Event()

    class PausingProvider:
        def generate_messages(self, messages):
            latest = messages[-1].content
            if latest == "during backup":
                provider_started.set()
                if not release_provider.wait(10):
                    raise RuntimeError("provider synchronization timed out")
            return ProviderResponse(f"answer: {latest}", "test")

    engine = persistent_engine(tmp_path / "active", provider=PausingProvider())
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "known committed")
    backup = tmp_path / "active-backup.sqlite3"
    errors = []

    def pause_after_sqlite_snapshot(path, *args, **kwargs):
        if path.name.startswith(".nspire-ai-backup-"):
            backup_snapshot_ready.set()
            if not release_backup.wait(10):
                raise RuntimeError("backup synchronization timed out")
        return original_validate(path, *args, **kwargs)

    original_validate = storage_module._validate_database_file
    monkeypatch.setattr(storage_module, "_validate_database_file", pause_after_sqlite_snapshot)
    original_operation_lock = engine._store._operation_lock
    local_lock = storage_module._local_path_lock(engine._store._lock_path)

    @contextmanager
    def observe_writer_critical_section():
        if current_thread().name == "conversation-writer":
            if not local_lock.acquire(blocking=False):
                writer_lock_blocked.set()
            else:
                local_lock.release()
        with original_operation_lock():
            if current_thread().name == "conversation-writer" and writer_lock_blocked.is_set():
                writer_entered_critical.set()
            yield

    monkeypatch.setattr(engine._store, "_operation_lock", observe_writer_critical_section)

    def send_pending_turn():
        try:
            engine.send_message(conversation_id, "during backup")
        except BaseException as exc:
            errors.append(exc)
        finally:
            writer_done.set()

    def create_backup():
        try:
            engine.backup(backup)
        except BaseException as exc:
            errors.append(exc)

    writer = Thread(target=send_pending_turn, name="conversation-writer")
    backup_worker = Thread(target=create_backup, name="backup-worker")
    try:
        writer.start()
        assert provider_started.wait(10), "writer did not become active before backup"
        backup_worker.start()
        assert backup_snapshot_ready.wait(10), "backup did not reach post-snapshot validation"
        release_provider.set()
        assert writer_lock_blocked.wait(10), "writer's nonblocking lock probe did not observe the held backup lock"
        assert not writer_entered_critical.is_set()
        assert not writer_done.is_set()
        release_backup.set()
        backup_worker.join(10)
        writer.join(10)
        assert not backup_worker.is_alive()
        assert not writer.is_alive()
        assert writer_entered_critical.is_set()
        assert writer_done.is_set()
        assert errors == []

        restored = persistent_engine(tmp_path / "from-active-backup")
        restored.restore_backup(backup)
        snapshot_history = restored.get_history(conversation_id)
        assert [(message.role, message.content) for message in snapshot_history] == [
            ("user", "known committed"),
            ("assistant", "answer: known committed"),
        ]
        assert [(message.role, message.content) for message in engine.get_history(conversation_id)][-2:] == [
            ("user", "during backup"),
            ("assistant", "answer: during backup"),
        ]
        restored.close()
    finally:
        release_provider.set()
        release_backup.set()
        if backup_worker.is_alive():
            backup_worker.join(10)
        if writer.is_alive():
            writer.join(10)
        engine.close()


def test_restore_rejects_invalid_backup_and_preserves_existing_store(tmp_path):
    target = tmp_path / "target"
    engine = persistent_engine(target)
    conversation_id = engine.create_conversation()
    engine.send_message(conversation_id, "keep existing")
    invalid = tmp_path / "bad.sqlite3"
    invalid.write_bytes(b"not a sqlite database")
    with pytest.raises(ConversationStorageCorruptionError):
        engine.restore_backup(str(invalid))
    assert [item.content for item in engine.get_history(conversation_id)][0] == "keep existing"
    engine.close()


def test_restore_requires_empty_store(tmp_path):
    source = persistent_engine(tmp_path / "source")
    source.create_conversation()
    backup = tmp_path / "backup.sqlite3"
    source.backup(str(backup))
    source.close()

    target = persistent_engine(tmp_path / "target")
    target.create_conversation()
    with pytest.raises(ConversationStorageError, match="empty"):
        target.restore_backup(str(backup))
    target.close()


def test_restore_excludes_other_process_until_database_replacement_finishes(tmp_path):
    source = SQLiteConversationStore(tmp_path / "source")
    source.create()
    backup = source.backup(tmp_path / "restore-source.sqlite3")
    source.close()

    target_dir = tmp_path / "restore-target"
    target = SQLiteConversationStore(target_dir)
    context = multiprocessing.get_context("spawn")
    ready = context.Event()
    start = context.Event()
    lock_blocked = context.Event()
    results = context.Queue()
    worker = context.Process(
        target=_create_conversation_in_process,
        args=(str(target_dir), ready, start, lock_blocked, results),
    )
    worker.start()
    restore_checked_empty = Event()
    allow_restore = Event()
    restore_errors = []
    original_check = target._check_integrity

    def pause_after_empty_check(connection):
        original_check(connection)
        restore_checked_empty.set()
        if not allow_restore.wait(10):
            raise RuntimeError("restore synchronization timed out")

    target._check_integrity = pause_after_empty_check

    def restore():
        try:
            target.restore_backup(backup)
        except BaseException as exc:
            restore_errors.append(exc)

    restore_worker = Thread(target=restore)
    try:
        assert ready.wait(10), "storage process did not initialize"
        restore_worker.start()
        assert restore_checked_empty.wait(10), "restore did not reach its empty-store check"
        start.set()
        assert lock_blocked.wait(10), "storage process did not observe the held restore lock"
        allow_restore.set()
        restore_worker.join(10)
        assert not restore_worker.is_alive(), "restore did not finish"
        result, value = results.get(timeout=10)
        worker.join(10)
        assert not worker.is_alive(), "storage process did not finish"
        assert worker.exitcode == 0
        assert restore_errors == []
        assert result == "created", value
        assert target.load(value).messages == ()
    finally:
        allow_restore.set()
        start.set()
        if restore_worker.is_alive():
            restore_worker.join(10)
        worker.join(10)
        if worker.is_alive():
            worker.terminate()
            worker.join(5)
        target.close()


def test_startup_rejects_malformed_database_without_replacing_it(tmp_path):
    database = tmp_path / DATABASE_FILENAME
    database.write_bytes(b"invalid database bytes")
    before = database.read_bytes()
    with pytest.raises(ConversationStorageError):
        SQLiteConversationStore(tmp_path)
    assert database.read_bytes() == before


def test_incomplete_or_invalid_stored_turn_is_rejected(tmp_path):
    store = SQLiteConversationStore(tmp_path)
    conversation_id = store.create()
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        connection.execute(
            "INSERT INTO messages(conversation_id, sequence, role, content, created_at) VALUES (?, 0, 'user', 'orphan turn', 'now')",
            (conversation_id,),
        )
    with pytest.raises(ConversationStorageCorruptionError):
        store.load(conversation_id)
    store.close()


def test_schema_version_is_stored_and_future_version_rejected(tmp_path):
    store = SQLiteConversationStore(tmp_path)
    store.close()
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        assert connection.execute("SELECT version FROM schema_info").fetchone()[0] == SCHEMA_VERSION
        connection.execute("UPDATE schema_info SET version = ?", (SCHEMA_VERSION + 1,))
    before = (tmp_path / DATABASE_FILENAME).read_bytes()
    with pytest.raises(ConversationStorageError, match="newer"):
        SQLiteConversationStore(tmp_path)
    assert (tmp_path / DATABASE_FILENAME).read_bytes() == before


def test_known_empty_v0_schema_migrates_transactionally(tmp_path):
    database = tmp_path / DATABASE_FILENAME
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info(version) VALUES (0)")
    store = SQLiteConversationStore(tmp_path)
    assert store.create()
    store.close()
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_info").fetchone()[0] == SCHEMA_VERSION


def test_regular_v1_schema_has_cascade_delete_and_deletes_messages(tmp_path):
    store = SQLiteConversationStore(tmp_path)
    conversation_id = store.create()
    snapshot = store.load(conversation_id)
    store.commit_turn(
        conversation_id, snapshot.revision,
        Message("user", "question"), Message("assistant", "answer"),
        max_history_messages=20, max_history_chars=1000,
    )
    store.delete(conversation_id)
    with sqlite3.connect(tmp_path / DATABASE_FILENAME) as connection:
        assert connection.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert connection.execute("PRAGMA foreign_key_list(messages)").fetchone()[6] == "CASCADE"
    store.close()


@pytest.mark.parametrize("on_delete", [None, "RESTRICT"])
def test_incompatible_v1_foreign_key_schema_is_rejected_without_modification(tmp_path, on_delete):
    database = tmp_path / DATABASE_FILENAME
    create_v1_database_with_foreign_key(database, on_delete=on_delete)
    before = database.read_bytes()
    with pytest.raises(ConversationStorageCorruptionError):
        SQLiteConversationStore(tmp_path)
    assert database.read_bytes() == before


def test_backup_with_incompatible_v1_schema_is_rejected(tmp_path):
    backup = tmp_path / "bad-schema-backup.sqlite3"
    create_v1_database_with_foreign_key(backup, on_delete=None)
    before = backup.read_bytes()
    target = SQLiteConversationStore(tmp_path / "target")
    with pytest.raises(ConversationStorageCorruptionError):
        target.restore_backup(backup)
    assert target.list() == ()
    assert backup.read_bytes() == before
    target.close()


def test_failed_v0_migration_rolls_back_and_preserves_database(tmp_path):
    database = tmp_path / DATABASE_FILENAME
    with sqlite3.connect(database) as connection:
        connection.execute("CREATE TABLE schema_info (version INTEGER NOT NULL)")
        connection.execute("INSERT INTO schema_info(version) VALUES (0)")
        connection.execute("CREATE TABLE conversations (unexpected TEXT)")
    with pytest.raises(ConversationStorageError):
        SQLiteConversationStore(tmp_path)
    with sqlite3.connect(database) as connection:
        assert connection.execute("SELECT version FROM schema_info").fetchone()[0] == 0
        assert connection.execute("PRAGMA table_info(messages)").fetchall() == []


def test_conversation_id_is_validated_before_storage_access(tmp_path):
    store = SQLiteConversationStore(tmp_path)
    for bad_id in ("../outside", "x" * 32, "A" * 32):
        with pytest.raises(ConversationNotFoundError):
            store.load(bad_id)
        with pytest.raises(ConversationNotFoundError):
            store.delete(bad_id)
    store.close()


@pytest.mark.skipif(os.name == "nt", reason="POSIX permission bits are not available on Windows")
def test_new_posix_storage_uses_private_permissions(tmp_path):
    data_dir = tmp_path / "private-store"
    store = SQLiteConversationStore(data_dir)
    assert stat.S_IMODE(data_dir.stat().st_mode) == 0o700
    assert stat.S_IMODE((data_dir / DATABASE_FILENAME).stat().st_mode) == 0o600
    store.close()


def test_storage_path_must_be_a_directory(tmp_path):
    path = tmp_path / "not-a-directory"
    path.write_text("file")
    with pytest.raises(ConversationStorageError):
        SQLiteConversationStore(path)


def test_malformed_paths_are_reported_as_storage_errors(tmp_path):
    store = SQLiteConversationStore(tmp_path)
    with pytest.raises(ConversationStorageError):
        store.backup(None)
    with pytest.raises(ConversationStorageError):
        store.restore_backup(None)
    store.close()

    with pytest.raises(ConversationStorageError):
        SQLiteConversationStore(None)
