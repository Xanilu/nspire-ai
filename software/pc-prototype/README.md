# NSPIRE AI PC prototype

Milestone 0.1 provides a small, provider-neutral Python foundation. The mock provider runs locally and makes no network requests or paid API calls.

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

- `NSPIRE_AI_PROVIDER` defaults to `mock`; milestone 0.1 supports only `mock`.
- `NSPIRE_AI_LOG_LEVEL` defaults to `INFO`.
- `NSPIRE_AI_DEBUG` defaults to `false` and accepts true/false, yes/no, on/off, or 1/0.

No API key setting exists yet. Future providers should add narrowly scoped credential handling without logging or committing secrets.

## Test

```powershell
python -m pytest
```

The `AIProvider` protocol and `ProviderResponse` in `src/nspire_ai/providers/base.py` form the provider seam. Real cloud or local model adapters, GUI, school workflows, transport, and calculator hardware integration are outside this milestone.
