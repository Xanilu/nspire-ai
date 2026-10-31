# NSPIRE AI

**A smarter calculator.**

Bringing modern AI capabilities to the TI-Nspire CX II platform.

> NSPIRE AI is an experimental software project exploring how a TI-Nspire CX II can act as a compact interface for a more capable AI system. The calculator is the front end; computation and model inference are intended to run on a connected computer or other external device.

## Project status

<em>Early planning / prototype stage.</em>

The repository is being built software-first. No internal hardware modifications are planned until the PC prototype, communication design, and technical constraints have been investigated.

## Goals

- Build a clean, modular PC prototype before targeting calculator hardware.
- Explore a reliable communication layer between the calculator and an external host.
- Provide a useful assistant workflow for school subjects, including mathematics, physics, German, and English.
- Keep the architecture documented, testable, and reproducible.
- Investigate hardware options only after the software approach is validated.

## Planned architecture

```text
TI-Nspire CX II
  └── Calculator client (Ndless)
        └── Communication layer
              └── External host / phone / PC
                    └── AI engine
                          └── Model or cloud AI service
```

This is a conceptual direction, not a claim that a particular wireless or calculator interface is already supported. The communication method and device capabilities still need to be verified.

## Repository layout

```text
nspire-ai/
├── docs/                  # Architecture, research, and development notes
├── software/
│   ├── pc-prototype/      # First runnable prototype foundation
│   ├── ai-engine/         # Future AI provider and task orchestration
│   └── communication/     # Future host-side communication interfaces
├── calculator/
│   └── ndless-client/     # Future TI-Nspire client
└── hardware/
    └── research/          # Hardware investigation; no build commitment
```

## Development principles

1. **Software first** — validate the experience on a PC before touching hardware.
2. **Modular by design** — keep the calculator client, transport, and AI engine separate.
3. **Document decisions** — record assumptions, tests, and limitations.
4. **Verify before promising** — distinguish working features from experiments and ideas.
5. **Keep it practical** — avoid unnecessary purchases and premature complexity.

## Getting started

The PC prototype includes AI Core 0.5: bounded SQLite conversations and opt-in incremental response streaming. The mock provider remains the offline default and OpenAI is optional. Setup and conversation API instructions are in [software/pc-prototype/README.md](software/pc-prototype/README.md).

See [ROADMAP.md](ROADMAP.md) and [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the current plan.

## License

No license has been selected yet. All rights are reserved by default; please do not assume the code is licensed for reuse.
