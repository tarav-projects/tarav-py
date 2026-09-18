import json

import pytest

from tarav.skw.skills import SkillPackage, SkillPackageRecord
from tarav.skw.loading import LoadingRecord


def package(tmp_path):
    source = tmp_path / '.skw/src/main.json'
    source.parent.mkdir(parents=True)
    blocks = [
        {'id': 'entry', 'kind': 'literal', 'lines': ['# Test']},
        {'id': 'vocabulary', 'kind': 'literal', 'lines': ['Vocabulary.']},
        {'id': 'bypass', 'kind': 'literal', 'lines': ['Other path.']},
        {'id': 'use', 'kind': 'literal', 'lines': ['Use vocabulary.']},
        {'id': 'orphan', 'kind': 'literal', 'lines': ['Unreachable.']}]
    source.write_text(json.dumps({'type': 'Tarav.Skillware.Document', 'schema_version': 1,
                                  'output': 'SKILL.md', 'blocks': blocks}))
    nodes = [{'id': b['id'], 'reference': {'type': 'Tarav.Reference.StructuredFile',
              'locator': {'path': 'src/main.json', 'pointer': f'/blocks/{i}'}}}
             for i, b in enumerate(blocks)]
    nodes[2]['parents'] = ['entry']
    nodes[3].update(parents=['vocabulary', 'bypass'],
                    requires=[{'target': 'vocabulary', 'delivery': 'inlined'}])
    nodes[4]['parents'] = []
    (tmp_path / '.skw/loading.json').write_text(json.dumps({
        'type': LoadingRecord.type_name, 'schema_version': 1, 'blocks': nodes}))
    (tmp_path / '.skw/skill.json').write_text(json.dumps({
        'type': SkillPackageRecord.type_name, 'schema_version': 1,
        'entrypoint': 'SKILL.md', 'sources': ['.skw/src/main.json'],
        'files': ['SKILL.md'], 'loading': '.skw/loading.json'}))
    return SkillPackage(tmp_path)


def test_static_paths_default_parent_and_coverage(tmp_path):
    p = package(tmp_path)
    analysis = p.loading().analyze()
    assert p.loading().parents['vocabulary'] == ['entry']
    kinds = [f['kind'] for f in analysis['findings']]
    assert kinds.count('missing-context') == 1
    assert 'path-dependent-context' in kinds
    assert {'kind': 'unreachable-block', 'block': 'orphan'} in analysis['findings']
    assert p.loading().inspect('use', limit=1)['path_count'] == 2
    assert len(p.loading().inspect('use', limit=1)['paths']) == 1


def test_links_are_generated_but_do_not_imply_loaded_content(tmp_path):
    p = package(tmp_path)
    graph = p.loading()
    graph.nodes['entry']['links'] = [{'target': 'vocabulary', 'slot': 'vocab', 'label': 'Read'}]
    graph.bindings['entry'][1]['lines'].append('{{skw:vocab}}')
    graph.nodes['use']['requires'][0]['delivery'] = 'referenced'
    assert not any(f['kind'] == 'missing-context' for f in graph.analyze()['findings'])
    text = graph.document_text(next(iter(graph.documents.values())))
    assert '[Read](SKILL.md#skw-vocabulary)' in text
    assert '<a id="skw-vocabulary"></a>' in text
    graph.nodes['use']['requires'][0]['delivery'] = 'inlined'
    assert any(f['kind'] == 'missing-context' for f in graph.analyze()['findings'])


def test_inclusions_generate_content_and_supply_context(tmp_path):
    graph = package(tmp_path).loading()
    graph.nodes['entry']['includes'] = [{'target': 'vocabulary', 'slot': 'vocab'}]
    graph.bindings['entry'][1]['lines'].append('{{skw:vocab}}')
    assert not any(f['kind'] == 'missing-context' for f in graph.analyze()['findings'])
    assert graph.render_block('entry', tmp_path / 'SKILL.md') == '# Test\nVocabulary.'
    graph.nodes['vocabulary']['includes'] = [{'target': 'entry', 'slot': 'cycle'}]
    graph.bindings['vocabulary'][1]['lines'].append('{{skw:cycle}}')
    assert any(f['kind'] == 'inclusion-cycle' for f in graph.analyze()['findings'])
    with pytest.raises(ValueError, match='cycle'):
        graph.render_block('entry', tmp_path / 'SKILL.md')


def test_markdown_never_discovers_edges(tmp_path):
    p = package(tmp_path)
    graph = p.loading()
    graph.bindings['entry'][1]['lines'].append('[Vocabulary](SKILL.md#vocabulary)')
    graph.nodes['use']['requires'][0]['delivery'] = 'referenced'
    assert sum(f['kind'] == 'missing-context' for f in graph.analyze()['findings']) == 2


def test_disconnected_cycle_and_analysis_limit(tmp_path):
    graph = package(tmp_path).loading()
    graph.parents['orphan'] = ['orphan']
    assert any(f['kind'] == 'attachment-cycle' for f in graph.analyze()['findings'])
    assert any(f['kind'] == 'loading-analysis-incomplete'
               for f in graph.analyze(limit=1)['findings'])


def test_slot_error_is_not_repaired(tmp_path):
    p = package(tmp_path)
    path = tmp_path / '.skw/loading.json'
    data = json.loads(path.read_text())
    data['blocks'][0]['links'] = [{'target': 'vocabulary', 'slot': 'missing', 'label': 'Read'}]
    path.write_text(json.dumps(data))
    assert any(f['kind'] == 'invalid-source' for f in p.check())
    assert not (tmp_path / 'SKILL.md').exists()


def test_inclusion_is_a_loading_path_for_an_otherwise_unattached_block(tmp_path):
    graph = package(tmp_path).loading()
    graph.nodes['entry']['includes'] = [{'target': 'orphan', 'slot': 'extra'}]
    graph.bindings['entry'][1]['lines'].append('{{skw:extra}}')
    assert not any(f['kind'] == 'unreachable-block' and f['block'] == 'orphan'
                   for f in graph.analyze()['findings'])
    assert graph.inspect('orphan')['paths'][0]['path'] == ['entry', 'orphan']


def test_cli_compile_uses_declared_primitives(tmp_path, capsys):
    from tarav.cli.cli import main
    p = package(tmp_path)
    path = tmp_path / '.skw/loading.json'
    data = json.loads(path.read_text())
    data['blocks'][0]['links'] = [{'target': 'vocabulary', 'slot': 'read', 'label': 'Read'}]
    path.write_text(json.dumps(data))
    source = tmp_path / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['lines'].append('{{skw:read}}')
    source.write_text(json.dumps(data))
    main(['skw', 'document', 'compile', '--project', str(tmp_path), '--source', 'main.json'])
    assert '[Read](SKILL.md#skw-vocabulary)' in (tmp_path / 'SKILL.md').read_text()
    assert '{{skw:' not in (tmp_path / 'SKILL.md').read_text()
    assert p.documents()[0].lint() == []


def test_output_link_check_does_not_create_edges(tmp_path):
    p = package(tmp_path)
    path = tmp_path / '.skw/src/main.json'
    data = json.loads(path.read_text())
    data['blocks'][0]['lines'].append('[Other](other.md)')
    path.write_text(json.dumps(data))
    model = p.loading()
    assert any(f['kind'] == 'unannotated-output-link' for f in model.findings)
    assert model.nodes['entry'].get('links', []) == []


def test_changed_declaration_invalidates_compilation(tmp_path):
    p = package(tmp_path)
    p.build()
    path = tmp_path / '.skw/loading.json'
    data = json.loads(path.read_text())
    data['blocks'][3]['requires'][0]['delivery'] = 'either'
    path.write_text(json.dumps(data))
    assert any(f['kind'] == 'loading-declaration-stale' for f in p.check())


def test_invalid_block_pointer_is_reported(tmp_path):
    p = package(tmp_path)
    path = tmp_path / '.skw/loading.json'
    data = json.loads(path.read_text())
    data['blocks'][1]['reference']['locator']['pointer'] = '/blocks/99'
    path.write_text(json.dumps(data))
    findings = p.loading().analyze()['findings']
    assert any(f['kind'] == 'invalid-block-reference' for f in findings)
    assert any(f['kind'] == 'invalid-context-target' for f in findings)


def test_empty_block_does_not_add_a_newline(tmp_path):
    p = package(tmp_path)
    source = tmp_path / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['lines'] = []
    source.write_text(json.dumps(data))
    assert p.documents()[0].text().startswith('Vocabulary.')
