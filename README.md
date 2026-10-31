# NSPIRE AI

**A smarter calculator.**

NSPIRE AI explores a practical path to a universal AI assistant with the TI-Nspire CX II-T CAS as a future interface. The project is software-first: model inference is intended to run on a connected host or cloud service, while the calculator would provide input and display.

## Status

The PC prototype is implemented through AI Core 0.6, including guided interactive chat, optional response streaming, and local conversation storage. Protocol v1 and a local stream transport are also implemented. No calculator client, calculator connection, phone integration, or hardware modification is implemented; those remain research and future work.

The eventual connectivity design is unverified. An iPhone hotspot can provide internet to a compatible host, but does not give the calculator network capability by itself. See [architecture](docs/ARCHITECTURE.md) and [hardware research](docs/HARDWARE_RESEARCH.md).

## Try the PC prototype

Requires Python 3.13 or newer. From the repository root, run in PowerShell:

```powershell
cd software/pc-prototype
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
nspire-ai "Explain what a provider interface is"
nspire-ai --stream "Explain what a provider interface is"
nspire-ai --chat
python -m pytest
```

The mock provider is the default and works offline. `nspire-ai --chat` opens a guided persistent chat; press Enter for a new chat, type `L` to list saved chats, or paste an ID to resume. OpenAI is optional and requires `OPENAI_API_KEY`; requests send the selected conversation context to the configured service and may incur charges. Conversation history is stored locally as plaintext. Configuration, persistence, and privacy limitations are in the [PC prototype guide](software/pc-prototype/README.md).

## Project map

- [Roadmap](ROADMAP.md) — completed milestones and planned investigations.
- [Architecture](docs/ARCHITECTURE.md) — intended components, current implementation, and constraints.
- [Protocol v1](docs/PROTOCOL_V1.md) — provider- and transport-neutral message format.
- [Transport Layer 0.1](docs/TRANSPORT_LAYER_V0_1.md) — local blocking stream framing; no network listener or device connector.
- [Hardware research](docs/HARDWARE_RESEARCH.md) — open feasibility questions and safety constraints.
- [Development log](docs/DEVELOPMENT_LOG.md) — decisions and verification history.
- [Changelog](CHANGELOG.md) and [contributing](CONTRIBUTING.md).

## Repository layout

```text
docs/                         Architecture, protocol, transport, and research
software/pc-prototype/        Runnable Python package and tests
```

## Project principles

- Validate the software experience on a PC before attempting calculator integration.
- Keep the calculator interface, communication layer, and AI engine replaceable.
- Record evidence, limitations, and open questions alongside implementation status.
- Avoid hardware purchases or modifications until feasibility is established.

## License

No license has been selected. Do not assume the code is licensed for reuse.
