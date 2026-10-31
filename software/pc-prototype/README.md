# NSPIRE AI PC prototype

**A smarter calculator.**

AI Core 0.7 hardens provider failures and streamed output while preserving the provider-neutral conversation engine. The engine factory enables persistence by default; direct `ConversationEngine` construction remains in-memory. The mock provider remains the default.

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
nspire-ai --stream "Explain what a provider interface is"
nspire-ai --chat
```

Configuration is read from environment variables:

- `NSPIRE_AI_PROVIDER` defaults to `mock`; set it to `openai` to explicitly enable OpenAI.
- `NSPIRE_AI_MODEL` selects the model and defaults to `gpt-4.1-mini`.
- `NSPIRE_AI_REQUEST_TIMEOUT` sets the HTTP timeout in seconds and defaults to `30`.
- `NSPIRE_AI_SYSTEM_CONTEXT` optionally supplies trusted system context. This value is application configuration; callers cannot select a message role when sending conversation input.
- `NSPIRE_AI_MAX_INPUT_CHARS` limits one user message (default `10000`).
- `NSPIRE_AI_MAX_CONTEXT_CHARS` limits message content sent to the provider (default `24000`).
- `NSPIRE_AI_MAX_CONTEXT_MESSAGES` limits provider messages including system context (default `32`).
- `NSPIRE_AI_MAX_STREAM_CHARS` bounds assembled streamed output (default `24000`).
- `NSPIRE_AI_MAX_STREAM_CHUNK_CHARS` bounds one provider fragment (default `4096`).
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

OpenAI requests use the official Responses API via `httpx`. They may incur API charges and send the selected conversation context to OpenAI. `--stream` requests actual incremental Responses API text deltas. The configured HTTP timeout bounds connection, pool, write, and individual read waits (including idle time between stream fragments); it is not an overall wall-clock deadline, so a stream that continually produces data can run longer than that value. The synchronous adapter closes its response when the stream finishes or is closed; a blocked read ends at the configured read timeout. Retries and tools are not implemented.

## Interactive chat

Run `nspire-ai --chat` to open a guided, persistent chat. Press Enter to start a new chat, type `L` to see saved chats, or paste a chat ID to resume it. The list shows IDs, last activity, message and turn counts without showing message text. During chat, type a message normally; `:help`, `:history`, `:sessions`, and `:quit` are optional shortcuts. Completed turns are saved as they finish; an interrupted or failed turn is not added to history. Any already displayed fragment is explicitly marked as an incomplete response that was not saved. Press Ctrl+C to stop the current turn or Ctrl+D (Ctrl+Z then Enter on Windows) to close the chat. Use `nspire-ai --chat ID` to open a known chat directly.

Conversation history is stored locally as plaintext in the SQLite database described below. When OpenAI is selected, the context retained for that conversation, including prior turns, is sent to OpenAI with each request. The mock provider remains the default. One-shot commands and `--stream` continue to work as before.

## Conversations

The Python API creates an independent opaque ID for each conversation. Reuse it for later messages and retrieve or delete its retained history:

```python
from nspire_ai import Settings, create_conversation_engine

engine = create_conversation_engine(Settings.from_env())
conversation_id = engine.create_conversation()
reply = engine.send_message(conversation_id, "What is a quadratic equation?")
for fragment in engine.stream_message(conversation_id, "Show me a simple example."):
    print(fragment, end="", flush=True)
history = engine.get_history(conversation_id)
engine.delete_conversation(conversation_id)
engine.close()
```

`send_message` and `stream_message` accept user text only; roles are assigned by the engine. Unknown or deleted IDs raise a generic `ConversationNotFoundError`. Provider failures raise a sanitized `ConversationProviderError` and leave history unchanged. Streaming snapshots history under the per-conversation lock, then yields fragments without holding it. The complete user/assistant pair is persisted only after the provider completes successfully and the assembled output validates; a revision check detects updates made during streaming. Closing the iterator early leaves history unchanged and releases provider resources. Providers without the optional streaming methods use a one-shot response yielded as one fragment. The engine retains successful user/assistant pairs, capped by both configured history limits.

Context counts Python string characters in message content. The engine always retains configured system context and the current user message. If they cannot fit, the request fails. Otherwise, it includes the newest contiguous suffix of complete user/assistant turns that fits both context limits; it removes older turns first and never removes system context. OpenAI receives each retained message with its role. Legacy providers implementing only `generate(prompt)` receive the same context in a role-labeled text prompt.

The engine factory stores conversations in a local SQLite database. Conversation IDs and validated user/assistant turns survive process restarts. Each successful turn is committed atomically. The store uses SQLite transactions, foreign keys, WAL mode, a bounded busy timeout, and optimistic revisions to detect writes from another engine. On a revision conflict, the provider response is discarded and the caller receives a safe storage conflict error; provider calls are not retried automatically. Provider failures expose stable internal categories (`timeout`, `unavailable`, `http_error`, or a generic provider category) while user-facing messages omit provider response bodies and exception details.

### Failure behavior (AI Core 0.7)

- A timeout maps to `timeout`; connection or other network failures map to `unavailable`; non-success HTTP status maps to `http_error`. Malformed, rejected, or unsupported provider data uses a generic sanitized provider category. Raw response bodies, request content, and exception details are not shown.
- A failed one-shot request returns an error and does not append a conversation turn. A failed stream returns a nonzero status (2), and any already printed text is followed by an explicit incomplete/not-saved notice. Ctrl+C returns status 130 with the same notice if text was emitted.
- Interactive chat stays open after a failed or interrupted turn and retains earlier completed history. The failed turn is not committed. Users choose whether to submit another request; the application never automatically repeats a provider request.
- Storage revision conflicts keep their existing safe storage error behavior and are not retried. Protocol v1, the local transport contract, and SQLite schema v1 are unchanged; this milestone does not add transport timeouts or authentication.

List sessions with `engine.list_conversations()`. To make a consistent backup, including WAL contents, call `engine.backup(r"C:\Backups\nspire-ai.sqlite3")`; the destination must not already exist. Restore with `engine.restore_backup(path)` on a newly initialized, empty persistent engine. The restore checks schema, integrity, IDs, message sequences, and configured limits before replacing the empty database. A per-database OS lock serializes storage operations across engine instances and processes; concurrent operations wait for restore to finish, subject to the bounded storage lock timeout. `engine.close()` closes the engine, and the engine supports `with` blocks.

Direct `ConversationEngine(provider)` construction and factory-created engines configured with `persistence_enabled=False` remain in memory. Logical deletion removes database rows and cascades to messages, but does not guarantee forensic erasure from SQLite pages, WAL files, filesystem snapshots, or backups. Data is plaintext; the application does not provide encryption at rest. On POSIX systems, newly created storage directories and database/backup files use restrictive permissions where supported. Windows uses inherited directory ACLs.

The schema is versioned. Startup validates the database and refuses unsupported future schemas or malformed storage rather than resetting it. Back up the database regularly. If the database is corrupt, preserve the original file and restore a known-good backup into an empty storage directory; 0.4 does not attempt automatic salvage. Backups contain conversation text and should be protected like the original database.

Backup and restore first write a temporary file and then replace or publish it atomically. If the process is interrupted, the requested destination remains absent or unchanged; a hidden `.nspire-ai-backup-*.tmp` or `.nspire-ai-restore-*.tmp` file may remain. After confirming no NSPIRE AI process is using the directory, remove only those incomplete temporary files. Treat them as sensitive conversation data.

The CLI supports one-shot requests and an opt-in guided persistent chat; `--stream` remains opt-in for one-shot requests. An interrupted streamed turn is never committed and any emitted text is labeled incomplete. Keyboard interruption returns status 130; provider failures return status 2. Automatic retries are disabled because an uncertain provider outcome could create duplicate billable work. Protocol v1 and the stream transport schemas are unchanged.

## Testing

```powershell
python -m pytest
```

Tests use `httpx.MockTransport`; no API key or live, billable request is needed.

The `AIProvider.generate` contract and `ProviderResponse` in `src/nspire_ai/providers/base.py` remain unchanged. GUI, school workflows, user accounts, cloud synchronization, multimodal features, encryption-at-rest, and calculator hardware integration are outside this milestone.
