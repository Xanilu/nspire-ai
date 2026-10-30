# NSPIRE AI PC prototype

AI Core 0.3 adds a provider-neutral conversation engine on top of AI Core 0.2. It supports bounded multi-turn conversations with either the offline mock or the optional OpenAI Responses API adapter. The mock provider remains the default.

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
```

`send_message` accepts user text only; roles are assigned by the engine. Unknown or deleted IDs raise a generic `ConversationNotFoundError`. Provider failures raise a sanitized `ConversationProviderError` and leave history unchanged. The engine retains successful user/assistant pairs, capped by both configured history limits.

Context counts Python string characters in message content. The engine always retains configured system context and the current user message. If they cannot fit, the request fails. Otherwise, it includes the newest contiguous suffix of complete user/assistant turns that fits both context limits; it removes older turns first and never removes system context. OpenAI receives each retained message with its role. Legacy providers implementing only `generate(prompt)` receive the same context in a role-labeled text prompt.

Conversation storage is in memory and belongs to the `ConversationEngine` instance. It is lost when the process exits, is not shared between engines or processes, and has no user-account or persistence layer. Deleting a conversation frees its retained history.

The existing CLI remains a one-shot command and the Protocol v1 and stream transport schemas are unchanged. Applications that need multi-turn behavior use the Python conversation API above.

## Test

```powershell
python -m pytest
```

Tests use `httpx.MockTransport`; no API key or live, billable request is needed.

The `AIProvider` protocol and `ProviderResponse` in `src/nspire_ai/providers/base.py` remain the provider seam. GUI, school workflows, persistent storage, user accounts, multimodal features, streaming, and calculator hardware integration are outside this milestone.
