# Backend Documentation

This folder contains engineering documentation for backend systems in CapiLearn. It is intended for backend contributors and is separate from the root project README.

## Contents

| Document | Description |
|---|---|
| [rag/architecture.md](./rag/architecture.md) | Design decisions, system boundaries, and known limitations for the RAG layer |
| [rag/runbook.md](./rag/runbook.md) | How to run, rebuild, evaluate, and troubleshoot the RAG pipeline |
| [rag/metrics.md](./rag/metrics.md) | Dated live-ingestion measurements, schema population checks, and validation results |
| [rag/engineering-notes.md](./rag/engineering-notes.md) | Reusable chunker rollout, verification, and development process notes |
| [../../docs/readme/README.md](../../docs/readme/README.md) | Expanded project README material for setup, configuration, development, architecture, and deployment |

## Documentation Conventions

- **Architecture docs** explain design decisions and system boundaries. They describe what a component does, what it deliberately does not do, and why.
- **Runbooks** explain how to operate a component: how to run it, what outputs to expect, and how to troubleshoot common failures.
- **Implementation details** should stay close to code through docstrings and focused inline comments rather than being duplicated in doc files.
- **Do not duplicate the root README.** Project-level setup, environment configuration, and contributor onboarding belong in `docs/readme/`, with the root README kept as a concise entry point.

For project-wide credits and third-party attribution, see [../../CREDITS.md](../../CREDITS.md).
