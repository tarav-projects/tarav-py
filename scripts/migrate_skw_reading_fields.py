"""Explicitly split legacy SKW reading declarations in selected source files.

Dry-run by default. Does not touch generation history, rendered text or locks.
"""
import argparse
import json
from pathlib import Path

from tarav.l1.skw.reading import Contains, ReadingDependency, ReadingLink, declaration_from_record


def migrate(data):
    # tarav.breadcrumb 3ac4bc17367a4de23c82b12f0c71921c5976b4397c82d46e0b43088f23bfc915
    changed = False
    for block in data.get('blocks', []):
        if 'reading' not in block:
            continue
        if any(field in block for field in ('contains', 'reading_deps', 'links')):
            raise ValueError('Mixed old/new declarations require manual reconciliation')
        groups = {'contains': [], 'reading_deps': [], 'links': []}
        for record in block['reading'] or []:
            value = declaration_from_record(record)
            if isinstance(value, Contains):
                field = 'contains'
            elif isinstance(value, ReadingDependency):
                field = 'reading_deps'
            elif isinstance(value, ReadingLink):
                field = 'links'
            else:
                raise ValueError(f'Unclassified declaration: {record}')
            groups[field].append(record)
        del block['reading']
        block.update({field: values for field, values in groups.items() if values})
        changed = True
    return changed


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('paths', nargs='+', type=Path)
    parser.add_argument('--write', action='store_true')
    args = parser.parse_args()
    updates = []
    for path in args.paths:
        data = json.loads(path.read_text())
        if migrate(data):
            updates.append((path, data))
    # Classify all files before writing any, so unknown types do not half-migrate.
    for path, data in updates:
        print(path)
        if args.write:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')


if __name__ == '__main__':
    main()
