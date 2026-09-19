"""Explicit context role hooks, independent from reference resolution."""
from dataclasses import dataclass
from typing import Callable


def user_grounding(content):
    if (not isinstance(content, dict)
            or content.get('type') != 'Tarav.Chatlas.Reference.Turn'
            or content.get('turn', {}).get('side') != 'user'):
        return 'user-grounding requires an exact Chatlas User Turn'
    return None


@dataclass(frozen=True)
class ContextRole:
    name: str
    tracks_changes: bool = False
    check: Callable = lambda content: None


class ContextRoles:
    def __init__(self):
        self.roles = {}
        for role in (ContextRole('maintenance'), ContextRole('dependency', True),
                     ContextRole('user-grounding', check=user_grounding)):
            self.register(role)

    def register(self, role):
        if not role.name or role.name in self.roles:
            raise ValueError('Invalid or duplicate context role')
        self.roles[role.name] = role

    def select(self, entry):
        names = entry.get('roles', [])
        if (not isinstance(names, list) or any(not isinstance(n, str) for n in names)
                or len(names) != len(set(names))):
            raise ValueError('roles must be an array of unique names')
        unknown = set(names) - self.roles.keys()
        if unknown:
            raise ValueError(f'Unknown context roles: {sorted(unknown)}')
        return [self.roles[n] for n in names]
