"""Static, declaration-driven consumer context for skill instruction blocks."""
import os
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import quote

from markdown_it import MarkdownIt

from tarav.harness import FileRecord, TypeShip
from tarav.references.structured import StructuredFileReference
from tarav.skillware.document import Document, read, write
from tarav.skillware.generation import _hash


class LoadingRecord(FileRecord):
    type_name = 'Tarav.Skillware.SkillLoading'
    type_ship = TypeShip('931ded86-5679-42be-b71c-71e84baf9d75')


class SkillDocument(Document):
    """Product rendering specialization; generic documents know no loading model."""

    def text(self):
        return self.loading.document_text(self)

    def lint(self):
        findings = super().lint()
        if (self.lock()['documents'].get(self.key, {}).get('loading_hash')
                != _hash(self.loading.data)):
            findings.append({'kind': 'loading-declaration-stale', 'path': self.key})
        try:
            self.text()
        except (ValueError, KeyError) as exc:
            findings.append({'kind': 'loading-render-error', 'detail': str(exc)})
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


class LoadingModel:
    def __init__(self, package, documents):
        self.package = package
        self.source = package.path(package.data['loading'])
        self.data = read(self.source)
        if (self.data.get('type') != LoadingRecord.type_name
                or self.data.get('schema_version') != 1):
            raise ValueError('Expected skill loading schema 1')
        self.documents = {d.source: d for d in documents}
        self.nodes = {}
        self.bindings = {}
        self.by_block = {}
        self.findings = []
        for node in self.data['blocks']:
            identity = node['id']
            if (not isinstance(identity, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', identity)
                    or identity in self.nodes):
                raise ValueError('Loading blocks require unique simple IDs')
            self.nodes[identity] = node
            try:
                if node['reference'].get('type') != StructuredFileReference.type_name:
                    raise ValueError('Expected StructuredFile block reference')
                reference = StructuredFileReference(node['reference'])
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
                key = (document.source, block['id'])
                if key in self.by_block:
                    raise ValueError('Source block bound more than once')
                self.bindings[identity] = (document, block)
                self.by_block[key] = identity
                # Conformance signal only. Parsed links never become edges.
                content = block.get('lines', block.get('output'))
                if content is not None:
                    for token in MarkdownIt().parse('\n'.join(content)):
                        for child in token.children or []:
                            if child.type == 'link_open':
                                self.report('unannotated-output-link', identity,
                                            target=child.attrGet('href'))
            except (OSError, ValueError, KeyError, TypeError) as exc:
                self.report('invalid-block-reference', identity, detail=str(exc))
        for document in documents:
            for block in document.blocks:
                if (document.source, block) not in self.by_block:
                    self.report('undeclared-block', str(document.source), detail=block)
        self.parents = {}
        for identity, node in self.nodes.items():
            if 'parents' in node:
                parents = node['parents']
            elif identity in self.bindings:
                document, block = self.bindings[identity]
                ordered = list(document.blocks)
                index = ordered.index(block['id'])
                previous = self.by_block.get((document.source, ordered[index - 1])) if index else None
                parents = [previous] if previous else []
            else:
                parents = []
            if not isinstance(parents, list) or any(not isinstance(p, str) for p in parents):
                raise ValueError('parents must be an array of block IDs')
            self.parents[identity] = list(dict.fromkeys(parents))
            for parent in parents:
                if parent not in self.bindings:
                    self.report('invalid-parent', identity, target=parent)
            slots = set()
            for kind in ('links', 'includes', 'requires'):
                for edge in node.get(kind, []):
                    if edge['target'] not in self.bindings:
                        self.report('invalid-context-target', identity, target=edge['target'])
                    if kind == 'requires':
                        if edge.get('delivery', 'either') not in ('referenced', 'inlined', 'either'):
                            raise ValueError('Unknown required delivery form')
                    else:
                        slot = edge['slot']
                        if (not isinstance(slot, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+', slot)
                                or slot in slots):
                            raise ValueError('Link/include slots must be unique simple IDs')
                        slots.add(slot)
                        if kind == 'links' and not isinstance(edge['label'], str):
                            raise ValueError('Links require a label')
        roots = [identity for identity, (d, b) in self.bindings.items()
                 if d.target == package.path(package.data['entrypoint'])
                 and b['id'] == next(iter(d.blocks))]
        self.root = self.data.get('root', roots[0] if len(roots) == 1 else None)
        if self.root not in self.bindings:
            self.report('invalid-loading-root', str(self.root))
        elif self.parents[self.root]:
            self.report('root-has-parent', self.root)

    def report(self, kind, block, **extra):
        self.findings.append({'kind': kind, 'block': block, **extra})

    def analyze(self, *, limit=10000):
        findings = list(self.findings)
        children = defaultdict(list)
        for child, parents in self.parents.items():
            for parent in parents:
                children[parent].append(child)
        # Check cycles even in components disconnected from the entry root.
        done = set()
        def cycle(node, active):
            if node in active:
                findings.append({'kind': 'attachment-cycle', 'block': node})
                return
            if node in done:
                return
            done.add(node)
            for child in children[node]:
                cycle(child, (*active, node))
        for node in self.nodes:
            cycle(node, ())
        states = defaultdict(list)
        outcomes = defaultdict(list)
        def supply(node, inline, linked, active, checks, visits):
            if node in active:
                findings.append({'kind': 'inclusion-cycle', 'block': node})
                return
            if node not in self.bindings:
                return
            inline.add(node)
            declaration = self.nodes[node]
            linked.update(e['target'] for e in declaration.get('links', [])
                          if e['target'] in self.bindings)
            for edge in declaration.get('includes', []):
                supply(edge['target'], inline, linked, (*active, node), checks, visits)
            for requirement in declaration.get('requires', []):
                target = requirement['target']
                delivery = requirement.get('delivery', 'either')
                satisfied = ((delivery in ('inlined', 'either') and target in inline)
                             or (delivery in ('referenced', 'either') and target in linked))
                checks.append((node, target, delivery, satisfied))
            suffix = [*active[1:], node] if active else []
            visits.append((node, suffix, sorted(inline), sorted(linked)))
        stack = [(self.root, (), set(), set())] if self.root in self.bindings else []
        count = 0
        while stack and count < limit:
            node, path, inline, linked = stack.pop()
            if node in path or node not in self.bindings:
                continue
            count += 1
            path = (*path, node)
            inline, linked, checks, visits = set(inline), set(linked), [], []
            supply(node, inline, linked, (), checks, visits)
            for visited, suffix, present, reachable in visits:
                states[visited].append({'path': [*path, *suffix], 'inlined': present,
                                        'referenced': reachable})
            for owner, target, delivery, satisfied in checks:
                outcomes[(owner, target, delivery)].append(satisfied)
                if not satisfied:
                    findings.append({'kind': 'missing-context', 'block': owner,
                                     'target': target, 'delivery': delivery, 'path': list(path)})
            stack.extend((child, path, inline, linked) for child in children[node])
        if stack:
            findings.append({'kind': 'loading-analysis-incomplete', 'limit': limit})
        else:
            for node in self.nodes:
                if node not in states:
                    findings.append({'kind': 'unreachable-block', 'block': node})
        for (node, target, delivery), values in outcomes.items():
            if any(values) and not all(values):
                findings.append({'kind': 'path-dependent-context', 'block': node,
                                 'target': target, 'delivery': delivery})
        return {'root': self.root, 'states': dict(states), 'findings': findings}

    def render_block(self, identity, output, active=()):
        if identity in active:
            raise ValueError(f'Inclusion cycle: {identity}')
        document, block = self.bindings[identity]
        content = block['lines'] if block['kind'] == 'literal' else block.get('output')
        if content is None:
            raise ValueError(f'Missing output: {identity}')
        text = '\n'.join(content)
        declaration = self.nodes[identity]
        for kind in ('links', 'includes'):
            for edge in declaration.get(kind, []):
                token = '{{skw:' + edge['slot'] + '}}'
                if text.count(token) != 1:
                    raise ValueError(f'Expected exactly one slot {token} in {identity}')
                if kind == 'includes':
                    value = self.render_block(edge['target'], output, (*active, identity))
                else:
                    target_document, target_block = self.bindings[edge['target']]
                    path = quote(os.path.relpath(target_document.target, output.parent), safe='/')
                    first = target_block['id'] == next(iter(target_document.blocks))
                    if not first:
                        path += '#skw-' + edge['target']
                    label = edge['label'].replace('\\', '\\\\').replace('[', '\\[').replace(']', '\\]')
                    value = f'[{label}]({path})'
                text = text.replace(token, value)
        if '{{skw:' in text:
            raise ValueError(f'Undeclared slot in {identity}')
        # Anchors are a generated primitive only where a declared link needs one.
        linked = any(e['target'] == identity for n in self.nodes.values()
                     for e in n.get('links', []))
        if linked and block['id'] != next(iter(document.blocks)) and not active:
            text = f'<a id="skw-{identity}"></a>\n' + text
        return text

    def document_text(self, document):
        parts = []
        for identity, block in document.blocks.items():
            content = self.render_block(self.by_block[(document.source, identity)], document.target)
            original = block['lines'] if block['kind'] == 'literal' else block.get('output')
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
                'findings': [f for f in analysis['findings']
                             if f.get('block') == block or f['kind'] == 'loading-analysis-incomplete']}
