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
# tarav.breadcrumb 1b91190ba3c4
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

    def source_findings(self):
        findings = super().source_findings()
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


# tarav.breadcrumb f4d2fd588176
class SkillReadingGraph(ReadingGraph):
    """Skill-package binding, rendering, and reading-path analysis."""
    # tarav.breadcrumb f3128c51a370

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
        # tarav.breadcrumb 1f2a5d756e2d
        self.source = package.depot_path(package.loading_file or 'main.json')
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
                slot = getattr(declaration.typed, 'slot', None)
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
            node = entry.typed.node
            if node not in self.bindings:
                raise ValueError(f'Unknown block entry: {node}')
            return node
        if isinstance(entry, FileEntry):
            source = self.package.path(entry.typed.source)
            matches = [node for node, (document, block) in self.bindings.items()
                       if document.target == source
                       and block.label == next(iter(document.blocks))]
            if len(matches) != 1:
                raise ValueError(f'File entry has {len(matches)} roots: {source}')
            return matches[0]
        raise TypeError('Unsupported reading entry')

    # tarav.breadcrumb 3345174f24ae
    def report(self, poi, block, **extra):
        self.diagnostics.append(Finding(poi, block=block, **extra))

    # tarav.breadcrumb b51cf1b5125a
    # tarav.breadcrumb b12c36d82f34
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
            slot = getattr(declaration.typed, 'slot', None)
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

    # tarav.breadcrumb 7f13a0d4e0cb
    def prose_findings(self):
        """What the prose parts of the declared links find in the text of their blocks.

        This is verification for maintainers; the analysis never reads text.
        """
        return [found for identity, links in self.links.items() for link in links
                for found in self.link_prose_findings(identity, link)]

    def prose_href(self, identity, link):
        """The href the text of a block should hold for one declared link, or None
        when the link has no prose part or no block to point at."""
        declaration, destination, target = link
        node = destination if destination is not None else self.by_ship.get(target)
        if declaration.prose is None or node is None:
            return None
        return self.href(node, self.bindings[identity][0].target)

    def link_prose_findings(self, identity, link):
        """What the prose part of one declared link finds in the text of its block."""
        document, block = self.bindings[identity]
        href = self.prose_href(identity, link)
        if href is None or block.get('content') is None:
            return []
        text = '\n'.join(block.content_lines())
        return [found.at(block=str(block.id), path=document.key, label=block.label)
                for found in link[0].prose.findings(text, href)]

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
