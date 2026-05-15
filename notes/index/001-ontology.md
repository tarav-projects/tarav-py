# Agentos Ontology

Registered concepts currently used explicitly in this index surface.

---

## Core Agentos Concepts

- **`Agentos.Mission`** - mission control as a lightweight coordination surface for named blocks of work (`003`)
- **`Agentos.Project`** - project identity and targeting model for project-scoped Agentos behavior (`004`)
- **`Agentos.Skills`** - selection and import model for project-local skills (`005`)

## Project and Session Contracts

- **`Project.Selection.Protocol`** - explicit project selector contract for project-aware command surfaces (`100`)
- **`Agentos.Agent.Model`** - provider-native agent/session model using `<Provider>.Agent` and `<Provider>.Session` anchors (`102`)
- **`Agentos.Agent`** - abstract Agentos concept for a provider-native configured actor; concrete shapes are provider-specific (`102`)
- **`Provider.Agent`** - provider-specific configured actor such as `Codex.Agent`, `Claude.Agent`, or `Pi.Agent` (`102`)
- **`Provider.Session`** - provider-specific native session artifact model such as `Codex.Session` or `Claude.Session` (`102`)
- **`Relocation.Function`** - private function created to relocate an implementation block without creating a new interface or abstraction (`102`)
- **`Agentos.Session`** - provider-agnostic normalized session concept; currently represented concretely by `Session.Model` (`006`, `102`)
- **`Chatlas.Normalizer`** - provider-specific conversion boundary from `Provider.Session` to `Agentos.Session` / `Session.Model` (`102`)
- **`Session.Model`** - provider-neutral data model for agent session interchange (`006`)
- **`Chatlas.Standard.Model.Contract`** - Chatlas standard model contract and export-view boundary (`007`)

## Integration Declaration

- **`Tara.Integration.Ontology`** - consumer-side declaration of Tara concepts implemented by Agentos (`002`)
