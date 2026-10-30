# NSPIRE AI PC prototype

AI Core 0.4 adds local SQLite persistence, session listing, and validated backup/restore to the provider-neutral conversation engine. The engine factory enables persistence by default; direct `ConversationEngine` construction remains in-memory. The mock provider remains the default.

## Requirements

Python 3.13 or newer (developed with Python 3.13.17).

## Setup

From this directory, create and activate a virtual environment, then install the package and development dependency:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
```

## Run

```powershell
nspire-ai "Explain what a provider interface is"
```

Configuration is read from environment variables:

- `NSPIRE_AI_PROVIDER` defaults to `mock`; set it to `openai` to explicitly enable OpenAI.
- `NSPIRE_AI_MODEL` selects the model and defaults to `gpt-4.1-mini`.
- `NSPIRE_AI_REQUEST_TIMEOUT` sets the HTTP timeout in seconds and defaults to `30`.
- `NSPIRE_AI_SYSTEM_CONTEXT` optionally supplies trusted system context. This value is application configuration; callers cannot select a message role when sending conversation input.
- `NSPIRE_AI_MAX_INPUT_CHARS` limits one user message (default `10000`).
- `NSPIRE_AI_MAX_CONTEXT_CHARS` limits message content sent to the provider (default `24000`).
- `NSPIRE_AI_MAX_CONTEXT_MESSAGES` limits provider messages including system context (default `32`).
- `NSPIRE_AI_MAX_HISTORY_MESSAGES` bounds retained history per conversation (default `200`, rounded only by whole turns and must be even).
- `NSPIRE_AI_MAX_HISTORY_CHARS` bounds retained history content per conversation (default `100000`).
- `NSPIRE_AI_MAX_CONVERSATIONS` limits active conversations in one engine (default `1000`).
- `NSPIRE_AI_PERSISTENCE` enables SQLite persistence through the engine factory (default `true`; set `false` for memory-only mode).
- `NSPIRE_AI_DATA_DIR` overrides the storage directory. Defaults are `%LOCALAPPDATA%\NSPIRE AI` on Windows, `~/Library/Application Support/NSPIRE AI` on macOS, and `$XDG_DATA_HOME/nspire-ai` or `~/.local/share/nspire-ai` on Linux. The database filename is `conversations.sqlite3`.
- `NSPIRE_AI_LOG_LEVEL` defaults to `INFO`.
- `NSPIRE_AI_DEBUG` defaults to `false` and accepts true/false, yes/no, on/off, or 1/0.

For OpenAI, set `OPENAI_API_KEY` in the process environment. The key is never stored in project configuration or logged. For example, in PowerShell:

```powershell
$env:NSPIRE_AI_PROVIDER = "openai"
$env:OPENAI_API_KEY = "your-key"
$env:NSPIRE_AI_MODEL = "gpt-4.1-mini"
$env:NSPIRE_AI_REQUEST_TIMEOUT = "30"
nspire-ai "Explain what a provider interface is"
```

OpenAI requests use the official Responses API via `httpx`. They may incur API charges and send the selected conversation context to OpenAI. The adapter is synchronous and does not implement streaming, retries, or tools.

## Conversations

The Python API creates an independent opaque ID for each conversation. Reuse it for later messages and retrieve or delete its retained history:

```python
from nspire_ai import Settings, create_conversation_engine

engine = create_conversation_engine(Settings.from_env())
conversation_id = engine.create_conversation()
reply = engine.send_message(conversation_id, "What is a quadratic equation?")
engine.send_message(conversation_id, "Show me a simple example.")
history = engine.get_history(conversation_id)
engine.delete_conversation(conversation_id)
engine.close()
```

`send_message` accepts user text only; roles are assigned by the engine. Unknown or deleted IDs raise a generic `ConversationNotFoundError`. Provider failures raise a sanitized `ConversationProviderError` and leave history unchanged. The engine retains successful user/assistant pairs, capped by both configured history limits.

Context counts Python string characters in message content. The engine always retains configured system context and the current user message. If they cannot fit, the request fails. Otherwise, it includes the newest contiguous suffix of complete user/assistant turns that fits both context limits; it removes older turns first and never removes system context. OpenAI receives each retained message with its role. Legacy providers implementing only `generate(prompt)` receive the same context in a role-labeled text prompt.

The engine factory stores conversations in a local SQLite database. Conversation IDs and validated user/assistant turns survive process restarts. Each successful turn is committed atomically. The store uses SQLite transactions, foreign keys, WAL mode, a bounded busy timeout, and optimistic revisions to detect writes from another engine. On a revision conflict, the provider response is discarded and the caller receives a safe storage conflict error; provider calls are not retried automatically.

List sessions with `engine.list_conversations()`. To make a consistent backup, including WAL contents, call `engine.backup(r"C:\Backups\nspire-ai.sqlite3")`; the destination must not already exist. Restore with `engine.restore_backup(path)` on a newly initialized, empty persistent engine. The restore checks schema, integrity, IDs, message sequences, and configured limits before replacing the empty database. A per-database OS lock serializes storage operations across engine instances and processes; concurrent operations wait for restore to finish, subject to the bounded storage lock timeout. `engine.close()` closes the engine, and the engine supports `with` blocks.

Direct `ConversationEngine(provider)` construction and factory-created engines configured with `persistence_enabled=False` remain in memory. Logical deletion removes database rows and cascades to messages, but does not guarantee forensic erasure from SQLite pages, WAL files, filesystem snapshots, or backups. Data is plaintext; the application does not provide encryption at rest. On POSIX systems, newly created storage directories and database/backup files use restrictive permissions where supported. Windows uses inherited directory ACLs.

The schema is versioned. Startup validates the database and refuses unsupported future schemas or malformed storage rather than resetting it. Back up the database regularly. If the database is corrupt, preserve the original file and restore a known-good backup into an empty storage directory; 0.4 does not attempt automatic salvage. Backups contain conversation text and should be protected like the original database.

Backup and restore first write a temporary file and then replace or publish it atomically. If the process is interrupted, the requested destination remains absent or unchanged; a hidden `.nspire-ai-backup-*.tmp` or `.nspire-ai-restore-*.tmp` file may remain. After confirming no NSPIRE AI process is using the directory, remove only those incomplete temporary files. Treat them as sensitive conversation data.

The existing CLI remains a one-shot command and the Protocol v1 and stream transport schemas are unchanged. Applications that need multi-turn behavior use the Python conversation API above.

## Test

```powershell
python -m pytest
```

Tests use `httpx.MockTransport`; no API key or live, billable request is needed.

The `AIProvider` protocol and `ProviderResponse` in `src/nspire_ai/providers/base.py` remain the provider seam. GUI, school workflows, user accounts, cloud synchronization, multimodal features, streaming, encryption-at-rest, and calculator hardware integration are outside this milestone.
