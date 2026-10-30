# NSPIRE AI PC prototype

AI Core 0.2 adds a provider registry/factory and an optional OpenAI adapter. The mock provider remains the default and runs locally without network access or API credentials.

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

OpenAI requests use the official Responses API via `httpx`. They may incur API charges and send the prompt to OpenAI. The adapter is synchronous and does not implement streaming, retries, conversation state, or tools.

## Test

```powershell
python -m pytest
```

Tests use `httpx.MockTransport`; no API key or live, billable request is needed.

The `AIProvider` protocol and `ProviderResponse` in `src/nspire_ai/providers/base.py` remain the provider seam. GUI, school workflows, conversation memory, multimodal features, and calculator hardware integration are outside this milestone.
