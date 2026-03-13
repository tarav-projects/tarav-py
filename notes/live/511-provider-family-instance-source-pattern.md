# Provider Family / Instance / Source Pattern

## Context
- Goal: unify provider-backed data into one inventory without erasing provider-specific structure too early.
- This pattern is useful when one subsystem needs a provider-agnostic interface over multiple provider families.

## Core Pattern
- `ProviderFamily` holds behavior shared by one family.
- `ProviderInstance` describes one concrete member of that family.
- `Source` objects carry provider-native records discovered from one instance.
- One unified object wraps a source and exposes the generic product-level view.

## Responsibilities
- Family:
  - defines defaults
  - knows how to interpret one instance
  - owns provider-specific discovery/loading behavior
- Instance:
  - is resolved runtime data, not just raw config
  - describes one concrete store/root/namespace for a family
  - should stay mostly data-oriented
- Source:
  - keeps native fields and native semantics
  - owns provider-specific merge/extract/stats behavior
- Unified object:
  - is the provider-agnostic surface used by the rest of the subsystem
  - exposes normalized fields plus the original native payload

## Important Constraint
- Do not collapse multiple instances of the same family into one merged family bucket before discovery.
- Instance identity should survive through discovery, normalization, and output.

## Why This Split Helps
- Keeps family behavior separate from instance data.
- Preserves the identity of multiple instances from the same family.
- Allows one generic inventory without hiding native provider detail.
- Avoids forcing provider-specific branching logic into the unified surface.

## Deferred
- Exact class names.
- Exact URI shape for the unified object.
- Exact config representation for declaring additional instances.
