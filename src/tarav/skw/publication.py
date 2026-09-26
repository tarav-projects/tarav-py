"""Deterministic publication of explicitly selected Diagram Model blocks."""
import hashlib
import json
from pathlib import Path

from tarav.diagram import DiagramError, DiagramNamespace
from tarav.diagram.rendering import DiagramRenderTarget, renderer
from tarav.kernel import TaravClass, entity
from tarav.kernel import FileRecord, TypeShip
from tarav.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from .document import read, write


class ModelPublicationRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('47d909ef-47b2-427b-8f6e-f8bb21887fd5'),
            name='Tarav.Skillware.ModelPublication',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class PublicationLockRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('98f83a13-0d1b-4ab9-8e23-afcbe977b0a5'),
            name='Tarav.Skillware.PublicationLock',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False,
                                     allow_nan=False).encode()).hexdigest()


class ModelPublication:
    def __init__(self, source, *, root):
        self.source = Path(source).resolve()
        self.root = Path(root).resolve()
        self.key = self.source.relative_to(self.root).as_posix()
        self.data = read(self.source)
        if (self.data.get('type') != entity(ModelPublicationRecord).name
                or self.data.get('schema_version') != 1):
            raise ValueError('Expected model publication schema 1')
        output = self.data['output']
        if (not isinstance(output, str) or not output.endswith('.md')
                or Path(output).is_absolute() or '..' in Path(output).parts):
            raise ValueError('Expected package-relative Markdown output')
        self.target = (self.root / output).resolve()
        if (not self.target.is_relative_to(self.root)
                or self.target.is_relative_to(self.root / '.skw')):
            raise ValueError('Publication output must be a consumer surface')
        blocks = self.data['blocks']
        if (not isinstance(blocks, list) or not blocks
                or any(not isinstance(b, str) for b in blocks)
                or len(blocks) != len(set(blocks))):
            raise ValueError('Select a nonempty ordered list of unique Block Ships')
        self.lock_path = self.root / '.skw/publications.lock.json'

    def render(self):
        # Namespace paths are relative to the publication source, like other
        # source references. No ambient default Diagram is consulted.
        namespace = DiagramNamespace.open(
            (self.source.parent / self.data['namespace']).resolve())
        model = namespace.model(self.data['model'])
        projection = model.project()
        contents, findings = [], []
        for identity in self.data['blocks']:
            block = projection.block(identity)
            result = renderer('Kernel.Writing.Block').render(
                DiagramRenderTarget('block', block.ship, namespace.id, block))
            contents.append(f'<!-- diagram.block {namespace.id}:{block.ship} -->\n'
                            + result.content)
            findings.extend(item.to_dict() for item in result.findings)
        # Conservative model snapshot includes annotations (grounding/scores),
        # not only wording. Changes can request review even if bytes stay equal.
        records = [{'id': ship.id, 'record': ship.record}
                   for ship in sorted(model.ships(), key=lambda item: item.id)]
        annotations = [{'id': item.id, 'record': item.record}
                       for item in sorted(model.annotations(), key=lambda item: item.id)]
        snapshot = {'namespace': namespace.id, 'model': model.ship,
                    'selection': self.data['blocks'], 'ships': records,
                    'annotations': annotations}
        content = '\n\n'.join(contents).rstrip() + '\n'
        return content, {'source_hash': digest(self.data),
                         'model_hash': digest(snapshot), 'product_hash': digest(content)}, findings

    def check(self):
        try:
            content, state, findings = self.render()
        except (OSError, ValueError, KeyError, TypeError, DiagramError) as exc:
            return [{'kind': 'publication-unresolvable', 'detail': str(exc)}]
        lock = self.lock()
        if lock['publications'].get(self.key) != state:
            findings.append({'kind': 'publication-stale', 'path': self.key})
        if not self.target.exists() or self.target.read_text() != content:
            findings.append({'kind': 'publication-drift', 'path': str(self.target)})
        return findings

    def lock(self):
        if not self.lock_path.exists():
            return {'type': entity(PublicationLockRecord).name, 'schema_version': 1,
                    'publications': {}}
        lock = read(self.lock_path)
        if (lock.get('type') != entity(PublicationLockRecord).name
                or lock.get('schema_version') != 1
                or not isinstance(lock.get('publications'), dict)):
            raise ValueError('Expected publication lock schema 1')
        return lock

    def compile(self):
        content, state, findings = self.render()
        lock = self.lock()
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_text(content, encoding='utf-8')
        lock['publications'][self.key] = state
        write(self.lock_path, lock)
        return findings
