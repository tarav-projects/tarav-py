# Legacy Agentos Tape

Deprecated on 2026-05-06.

This directory archives the former `agentos tape` implementation. It was a
folder-backed JSONL tape system with:

- CLI surface: `agentos tape`
- Python package: `agentos.tape`
- manifest: `tape.manifest.json`
- directories: `staging/` and `segments/`
- typed record envelope: `class`, `writer`, `created_at`, and optional `data`
- extra behavior: allowed classes, JSON Schema validation, JMESPath query, and
  project-scoped resolution under `.agentos/tapes/`

The active tape system is now Tara tapes:

- CLI surface: `agentos tara-tapes`
- Python package: `agentos.tara_tapes`
- manifest: `tape.json`
- directories: `stage/` and `segments/`

This archive is for reference only. Do not import it from active code.
