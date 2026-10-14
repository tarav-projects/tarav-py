"""Static, declaration-driven consumer context for skill instruction blocks."""
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import FileRecord, Ship, TypeShip
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.references.structured import StructuredFileReference
from .document import Document, read, write
from .skills import SkillLink
# tarav.breadcrumb 1b91190ba3c46ec2a8d828da9b596086e9b950234134ca26c90d95eb0dca37fb
from .code import (BlockEntry, Contains, ExpectedLink, FileEntry,
                   IncludesBlock, ReadingGraph, ReadingLink, ReadingDependency)
from .generation import _hash
from .pois import (
    AttachmentCycle, Finding, InclusionCycle, InvalidBlockReference, InvalidContextTarget,
    InvalidLoadingRoot, InvalidParent, LoadingAnalysisIncomplete, LoadingDeclarationStale,
    LoadingRenderError, RootHasParent, UndeclaredBlock, UnreachableBlock,
)


class LoadingRecord(FileRecord):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('931ded86-5679-42be-b71c-71e84baf9d75'),
            name='Tarav.Skillware.SkillLoading',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )


class SkillDocument(Document):
    """Product rendering specialization; generic documents know no loading model."""

    def text(self):
        return self.loading.document_text(self)

    def lint(self, *, freshness=True):
        findings = super().lint(freshness=freshness)
        if (self.lock()['documents'].get(self.key, {}).get('loading_hash')
                != _hash(self.loading.data)):
            findings.append(Finding(LoadingDeclarationStale, path=self.key))
        try:
            self.text()
        except (ValueError, KeyError) as exc:
            findings.append(Finding(LoadingRenderError, detail=str(exc)))
        return findings

    def compile(self):
        self.text()  # Fail before mutation when a primitive cannot be materialized.
        result = super().compile()
        if result['written']:
            lock = self.lock()
            lock['documents'][self.key]['loading_hash'] = _hash(self.loading.data)
            write(self.lock_path, lock)
            result['findings'] = self.lint()
        return result


# tarav.breadcrumb f4d2fd588176b0f1faadd7a1173874ad992004685b107fa4d1fb52f55c4e97a5
class SkillReadingGraph(ReadingGraph):
    """Skill-package binding, rendering, and reading-path analysis."""
    # tarav.breadcrumb f3128c51a3704497ef0342eead63829fff1db828630a02c4c04ac0c77ce3a836

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip("c6fa0495-acda-42ec-8669-380957fcdebe"),
            name="Tarav.SKW.Skills.ReadingGraph",
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    def __init__(self, package, documents):
        self.package = package
        # tarav.breadcrumb 1f2a5d756e2d5656f99872c4ef20e28c188475e20fd9454ac3ef0f4753e314a0
        self.source = package.path(package.loading_file or '.skw/main.json')
        if package.loading_file is not None:
            self.data = read(self.source)
        else:
            # Derived bindings are ephemeral, not a registry written to disk.
            self.data = {'type': entity(LoadingRecord).name, 'schema_version': 1,
                         'blocks': [
                             {'id': str(block.id), 'reference': {
                                 'type': entity(StructuredFileReference).name,
                                 'locator': {'path': os.path.relpath(document.source, self.source.parent),
                                             'pointer': f'/blocks/{index}'}}}
                             for document in documents
                             for index, block in enumerate(document.blocks.values())]}
        if (self.data.get('type') != entity(LoadingRecord).name
                or self.data.get('schema_version') != 1):
            raise ValueError('Expected skill loading schema 1')
        self.documents = {d.source: d for d in documents}
        self.nodes = {}
        self.bindings = {}
        self.by_block = {}
        self.by_ship = {}
        self.diagnostics = []
        for node in self.data['blocks']:
            identity = node['id']
            if (not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', identity)
                    or identity in self.nodes):
                raise ValueError('Loading blocks require unique simple IDs')
            self.nodes[identity] = node
            try:
                if node['reference'].get('type') != entity(StructuredFileReference).name:
                    raise ValueError('Expected StructuredFile block reference')
                reference = StructuredFileReference.records.from_record(node['reference'])
                reference.source = self.source
                result = reference.resolve()
                if not result.ok:
                    raise ValueError(result.message)
                address = reference.address()
                document = self.documents[Path(address['path'])]
                # Check both pointer and block identity: selecting a nested object
                # or a coincidentally identical value is not a block binding.
                pointer = address.get('pointer', '')
                if not re.fullmatch(r'/blocks/(0|[1-9][0-9]*)', pointer):
                    raise ValueError('Select one complete source block')
                block = result.target
                typed = document.blocks_by_ship[Ship(block['id'])]
                if typed.records.to_record() != block:
                    raise ValueError('Block reference disagrees with loaded Type')
                key = (document.source, typed.label)
                if key in self.by_block:
                    raise ValueError('Source block bound more than once')
                self.bindings[identity] = (document, typed)
                self.by_block[key] = identity
                if typed.id in self.by_ship:
                    raise ValueError('Block Ship bound more than once')
                self.by_ship[typed.id] = identity
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.report(InvalidBlockReference, identity, detail=str(exc))
        for document in documents:
            for block in document.blocks:
                if (document.source, block) not in self.by_block:
                    self.report(UndeclaredBlock, str(document.source), detail=block)
        self.reading = {}
        self.links = {}
        self.includes = {}
        self.requirements = {}
        self.contains = {}
        for identity, (_, block) in self.bindings.items():
            self.reading[identity] = tuple(
                declaration for declaration in block.annotations()
                if isinstance(declaration, (Contains, ReadingDependency, ReadingLink))
            )
            self.links[identity], self.includes[identity] = [], []
            self.requirements[identity] = []
            self.contains[identity] = []
            for declaration in self.reading[identity]:
                try:
                    target = self.resolve_target(declaration.target)
                    if isinstance(declaration, ReadingDependency):
                        self.requirements[identity].append((declaration, target))
                    elif isinstance(declaration, Contains):
                        destination = self.by_ship.get(target)
                        if isinstance(declaration, IncludesBlock):
                            rendered = self.resolve_entry(declaration.destination())
                            if rendered != destination:
                                raise ValueError('Included entry must identify its contained target')
                            self.includes[identity].append((declaration, destination, target))
                        self.contains[identity].append((target, destination))
                    elif isinstance(declaration, ReadingLink):
                        destination = (self.resolve_entry(declaration.destination())
                                       if isinstance(declaration, ExpectedLink) else
                                       self.resolve_entry_record(declaration.entry))
                        declaration.prose  # an unknown prose Type is an invalid declaration
                        self.links[identity].append((declaration, destination, target))
                except (ValueError, KeyError, TypeError) as exc:
                    self.report(InvalidContextTarget, identity,
                                target=declaration.target, detail=str(exc))
            if isinstance(block, SkillLink) and block['target'] not in self.bindings:
                self.report(InvalidContextTarget, identity, target=block['target'])
        self.parents = {}
        for identity, node in self.nodes.items():
            if 'parents' in node:
                parents = node['parents']
            elif identity in self.bindings:
                document, block = self.bindings[identity]
                ordered = list(document.blocks)
                index = ordered.index(block.label)
                previous = self.by_block.get((document.source, ordered[index - 1])) if index else None
                parents = [previous] if previous else []
            else:
                parents = []
            if not isinstance(parents, list) or any(not isinstance(p, str) for p in parents):
                raise ValueError('parents must be an array of block IDs')
            self.parents[identity] = list(dict.fromkeys(parents))
            for parent in parents:
                if parent not in self.bindings:
                    self.report(InvalidParent, identity, target=parent)
            if any(kind in node for kind in ('links', 'includes', 'requires')):
                raise ValueError('Reading declarations belong to source blocks')
            slots = set()
            for declaration, _, _ in self.includes.get(identity, ()):
                slot = declaration._record.get('slot')
                if slot is None:
                    continue
                if (not isinstance(slot, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', slot)
                        or slot in slots):
                    raise ValueError('Reading slots require unique simple IDs')
                slots.add(slot)
        roots = [identity for identity, (d, b) in self.bindings.items()
                 if d.target == package.entrypoint
                 and b.label == next(iter(d.blocks))]
        self.root = self.data.get('root', roots[0] if len(roots) == 1 else None)
        if self.root not in self.bindings:
            self.report(InvalidLoadingRoot, str(self.root))
        elif self.parents[self.root]:
            self.report(RootHasParent, self.root)

    def resolve_target(self, value):
        """Resolve a Ship exactly, or an unambiguous package-local block label."""
        try:
            return Ship(value)
        except ValueError:
            matches = [block.id for _, block in self.bindings.values()
                       if block.label == value]
            if len(matches) != 1:
                raise ValueError(f'Label {value!r} has {len(matches)} matching blocks')
            return matches[0]

    def resolve_entry_record(self, value):
        from .code import entry_from_record
        return self.resolve_entry(entry_from_record(value)) if value is not None else None

    def resolve_entry(self, entry):
        if isinstance(entry, BlockEntry):
            node = entry._record['node']
            if node not in self.bindings:
                raise ValueError(f'Unknown block entry: {node}')
            return node
        if isinstance(entry, FileEntry):
            source = self.package.path(entry._record['source'])
            matches = [node for node, (document, block) in self.bindings.items()
                       if document.target == source
                       and block.label == next(iter(document.blocks))]
            if len(matches) != 1:
                raise ValueError(f'File entry has {len(matches)} roots: {source}')
            return matches[0]
        raise TypeError('Unsupported reading entry')

    # tarav.breadcrumb 3345174f24aecf669f77659006724d7a9d999a8760cff229661e7eefb1bbdeb6
    def report(self, poi, block, **extra):
        self.diagnostics.append(Finding(poi, block=block, **extra))

    # tarav.breadcrumb b51cf1b5125ad0509724463bcb6a572c5c547f04e6c0ccbac83a1f07ce59a4c4
    # tarav.breadcrumb b12c36d82f34814d160e8c847240232341457362536894b8c6d27702938ffe09
    def analyze(self, *, limit=10000, entry=None):
        """Accumulate content on declared routes; links only supply references.

        The retained ``inlined`` result field denotes available content,
        including recursive Contains claims. It does not imply rendering.
        """
        diagnostics = list(self.diagnostics)
        children = defaultdict(list)
        for child, parents in self.parents.items():
            for parent in parents:
                children[parent].append(child)
        # Links expose references. Only declared route parents advance reading.
        for source, destinations in children.items():
            children[source] = list(dict.fromkeys(destinations))
        # Check cycles even in components disconnected from the entry root.
        done = set()
        def cycle(node, active):
            if node in active:
                diagnostics.append(Finding(AttachmentCycle, block=node))
                return
            if node in done:
                return
            done.add(node)
            for child in children[node]:
                cycle(child, (*active, node))
        for node in self.nodes:
            cycle(node, ())
        states = defaultdict(list)
        observations = []
        def supply(node, inline, linked, active, checks, visits):
            if node in active:
                diagnostics.append(Finding(InclusionCycle, block=node))
                return
            if node not in self.bindings:
                return
            _, block = self.bindings[node]
            incoming_inline = sorted(map(str, inline))
            incoming_linked = sorted(map(str, linked))
            suffix = [*active[1:], node] if active else []
            for requirement, target in self.requirements[node]:
                satisfied = requirement.satisfied(target, inline, linked)
                checks.append((node, str(target), requirement.delivery, satisfied,
                               incoming_inline, incoming_linked, suffix))
            inline.add(block.id)
            linked.update(target for _, _, target in self.links[node])
            for target, destination in self.contains[node]:
                if destination is None:
                    inline.add(target)
                else:
                    supply(destination, inline, linked, (*active, node), checks, visits)
            visits.append((node, suffix, incoming_inline, incoming_linked,
                           sorted(map(str, inline)), sorted(map(str, linked))))
        start = self.root if entry is None else entry
        if entry is not None and start not in self.bindings:
            raise ValueError(f'Unknown reading entry: {start}')
        stack = [(start, (), set(), set())] if start in self.bindings else []
        count = 0
        while stack and count < limit:
            node, path, inline, linked = stack.pop()
            if node in path or node not in self.bindings:
                continue
            count += 1
            path = (*path, node)
            inline, linked, checks, visits = set(inline), set(linked), [], []
            supply(node, inline, linked, (), checks, visits)
            for visited, suffix, incoming_inline, incoming_linked, present, reachable in visits:
                states[visited].append({'path': [*path, *suffix],
                                        'incoming_inlined': incoming_inline,
                                        'incoming_referenced': incoming_linked,
                                        'inlined': present, 'referenced': reachable})
            for owner, target, delivery, satisfied, present, reachable, suffix in checks:
                observations.append({'block': owner, 'target': target, 'delivery': delivery,
                                     'satisfied': satisfied, 'path': [*path, *suffix],
                                     'inlined': present, 'referenced': reachable})
            stack.extend((child, path, inline, linked) for child in children[node])
        if stack:
            diagnostics.append(Finding(LoadingAnalysisIncomplete, limit=limit))
        else:
            for node in self.nodes:
                if node not in states:
                    diagnostics.append(Finding(UnreachableBlock, block=node))
        availability = {}
        for node, paths in states.items():
            def sets(key):
                values = [set(state[key]) for state in paths]
                return {'intersection': sorted(set.intersection(*values)),
                        'union': sorted(set.union(*values))}
            availability[node] = {'inlined': sets('incoming_inlined'),
                                  'referenced': sets('incoming_referenced')}
        incomplete = any(f.poi in (InvalidBlockReference, InvalidParent, InvalidContextTarget,
                                   InvalidLoadingRoot, AttachmentCycle, InclusionCycle,
                                   LoadingAnalysisIncomplete) for f in diagnostics)
        return {'root': start, 'states': dict(states), 'availability': availability,
                'requirements': observations,
                'complete': not incomplete, 'diagnostics': diagnostics}

    def render_block(self, identity, output, active=()):
        if identity in active:
            raise ValueError(f'Inclusion cycle: {identity}')
        document, block = self.bindings[identity]
        text = '\n'.join(block.content_lines())
        for declaration, destination, _ in self.includes[identity]:
            slot = declaration._record.get('slot')
            if slot is None:
                continue
            token = '{{skw:' + slot + '}}'
            if text.count(token) != 1:
                raise ValueError(f'Expected exactly one slot {token} in {identity}')
            text = text.replace(token, self.render_block(destination, output, (*active, identity)))
        if '{{skw:' in text:
            raise ValueError(f'Undeclared slot in {identity}')
        # Anchors are a generated primitive only where a declared link needs one.
        linked = any(destination == identity for values in self.links.values()
                     for _, destination, _ in values) or any(
                         isinstance(other, SkillLink) and other['target'] == identity
                         for _, other in self.bindings.values())
        if linked and block.label != next(iter(document.blocks)) and not active:
            text = f'<a id="skw-{block.id}"></a>\n' + text
        return text

    def href(self, node, output: Path) -> str:
        """The href from the file `output` to the block bound at `node`."""
        target_document, target_block = self.bindings[node]
        path = quote(os.path.relpath(target_document.target, output.parent), safe='/')
        if target_block.label != next(iter(target_document.blocks)):
            path += '#skw-' + str(target_block.id)
        return path

    def link_output(self, block: SkillLink, output: Path) -> str:
        target = block['target']
        if target not in self.bindings:
            raise ValueError(f'Unknown SkillLink target: {target}')
        label = block['caption'].replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
        return f'[{label}]({self.href(target, output)})'

    # tarav.breadcrumb 7f13a0d4e0cb6be5e1972fffe7f7924aa7bda67b6c88eef97c2a38c43060268e
    def prose_findings(self):
        """What the prose parts of the declared links find in the text of their blocks.

        This is verification for maintainers; the analysis never reads text.
        """
        findings = []
        for identity, links in self.links.items():
            document, block = self.bindings[identity]
            content = block.get('content')
            if content is None:
                continue
            text = '\n'.join(block.content_lines())
            for declaration, destination, target in links:
                prose = declaration.prose
                node = destination if destination is not None else self.by_ship.get(target)
                if prose is None or node is None:
                    continue
                findings.extend(found.at(block=str(block.id), path=document.key, label=block.label)
                                for found in prose.findings(text, self.href(node, document.target)))
        return findings

    def document_text(self, document):
        parts = []
        for identity, block in document.blocks.items():
            if block.inline_only():
                continue
            content = self.render_block(self.by_block[(document.source, identity)], document.target)
            original = block.get('output')
            if original or content:
                parts.append(content)
        return '\n'.join(parts) + ('\n' if parts else '')

    def inspect(self, block, *, limit=5):
        if block not in self.nodes:
            raise ValueError('Unknown loading block')
        analysis = self.analyze()
        states = analysis['states'].get(block, [])
        return {'block': block, 'declaration': self.nodes[block],
                'parents': self.parents[block], 'path_count': len(states),
                'paths': states[:limit],
                'diagnostics': [f.to_json() for f in analysis['diagnostics']
                                if f.get('block') == block
                                or f.poi is LoadingAnalysisIncomplete]}
