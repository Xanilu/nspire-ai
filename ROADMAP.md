# Roadmap

This roadmap separates completed PC foundations from research and features that still need implementation or device evidence.

## Phase 0 — Project foundation
- [x] Create private repository
- [x] Establish documentation and contribution conventions
- [x] Define the first prototype's scope
- [x] Implement milestone 0.1 PC package foundation (settings, logging, errors, provider protocol, mock provider, CLI, tests)

## Phase 1 — PC prototype
- [x] Choose a simple, maintainable implementation stack (Python 3.13, standard library runtime)
- [x] Build a minimal local request/response smoke-test interface
- [x] Add a replaceable AI-provider layer (protocol and mock implementation)
- [x] Add basic tests and setup instructions
- [x] Define and validate a structured host request/response contract (Protocol v1)
- [x] AI Core 0.2: provider registry/factory, validated model and timeout configuration, optional OpenAI adapter, sanitized provider errors
- [x] AI Core 0.3: bounded in-memory conversations, message history, deterministic provider context mapping
- [x] AI Core 0.4: SQLite persistence, session listing, transactional turns, optimistic concurrency, and backup/restore
- [x] AI Core 0.5: bounded provider and conversation streaming with opt-in CLI output (independently reviewed and verified offline)
- [x] AI Core 0.6: guided persistent interactive CLI chat using the conversation engine; one-shot commands remain supported

## Phase 2 — Communication design
- [ ] Compare possible calculator-to-host communication paths
- [x] Define a transport-independent message format (Protocol v1)
- [x] Prototype framed local stream exchange between PC components (Transport Layer 0.1)
- [ ] Document latency, reliability, and security constraints

## Phase 3 — Calculator client
- [ ] Review Ndless APIs and TI-Nspire CX II compatibility
- [ ] Build a minimal calculator-side proof of concept
- [ ] Connect it to the tested host protocol
- [ ] Test failure handling and user experience

## Phase 4 — Hardware research
- [ ] Investigate physical interfaces and available space
- [ ] Assess power, thermal, and electrical constraints
- [ ] Evaluate feasibility before buying components or modifying the calculator

## Phase 5 — School assistant workflows
- [ ] Mathematics and step-by-step explanations
- [ ] Physics problem support
- [ ] German and English writing support
- [ ] Clear source/context handling and user controls

## Working rule

A milestone is not complete until its behavior has been tested and its limitations documented.
