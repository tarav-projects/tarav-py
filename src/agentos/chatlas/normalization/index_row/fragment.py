"""`Model.Fragment` — a partial, sub-shape slice of a `Normal.Model`.

A fragment is a plain dict whose keys are paths in the target object's namespace
(here, the flat index row). Fragments compose by deep-merge. Merge *policy* is the
`Normal.Assembler`'s concern; this module only offers a structural deep-merge
primitive plus private timestamp candidate accumulators the index-row assembler
uses to coalesce a session's timestamp semantics across sources.
"""

from __future__ import annotations

from typing import Any

ModelFragment = dict[str, Any]

# Private fragment keys: numeric timestamp candidates contributed by normalizers.
# The assembler strips them from output and owns min/max timestamp policy.
CREATED_AT_CANDIDATES_KEY = "_created_at_candidates"
LAST_ACTIVITY_AT_CANDIDATES_KEY = "_last_activity_at_candidates"
TIMESTAMP_CANDIDATE_KEYS = frozenset(
    {
        CREATED_AT_CANDIDATES_KEY,
        LAST_ACTIVITY_AT_CANDIDATES_KEY,
    }
)


def empty_fragment() -> ModelFragment:
    return {}


def merge_fragment(into: ModelFragment, other: ModelFragment) -> ModelFragment:
    """Structural deep-merge of ``other`` onto ``into`` (mutates and returns ``into``).

    - nested dicts merge recursively
    - timestamp candidate lists accumulate (concatenate)
    - every other key is last-present-wins; normalizer ordering is the caller's lever
    """
    for key, value in other.items():
        if key in TIMESTAMP_CANDIDATE_KEYS:
            existing = into.get(key)
            base = list(existing) if isinstance(existing, list) else []
            base.extend(value if isinstance(value, list) else [value])
            into[key] = base
            continue
        if isinstance(value, dict) and isinstance(into.get(key), dict):
            merge_fragment(into[key], value)
            continue
        into[key] = value
    return into


def merge_fragments(fragments: list[ModelFragment]) -> ModelFragment:
    merged: ModelFragment = {}
    for fragment in fragments:
        merge_fragment(merged, fragment)
    return merged
