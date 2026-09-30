from tarav.l0.kernel import entity

import json

import pytest
from skw_records import identify_blocks

from tarav.l3.runtime import create_runtime
from tarav.l2.skw.skills import SkwSkill
from tarav.l1.skw.loading import LoadingRecord
from tarav.l1.skw.skills import SkillLink
from tarav.l1.skw.reading import (BlockEntry, ConsultationLink, IncludesBlock,
                                  InlineDependency, ReferenceDependency)
from tarav.l2.skw.reading_checks import reading_checks
from tarav.l1.checks import run_checks
from tarav.l1.poi import POICollector, POIError


def reading_findings(graph, **options):
    analysis = graph.analyze(**options)
    return [poi.evidence['finding']
            for check in reading_checks(graph, analysis=analysis)
            for poi in check.run().pois()]


def package(tmp_path):
    source = tmp_path / '.skw/src/main.json'
    source.parent.mkdir(parents=True)
    blocks = [
        {'id': 'entry', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['# Test']},
        {'id': 'vocabulary', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['Vocabulary.']},
        {'id': 'bypass', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['Other path.']},
        {'id': 'use', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['Use vocabulary.']},
        {'id': 'orphan', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['Unreachable.']}]
    identify_blocks({'blocks': blocks}, scope='loading-main')
    blocks[3]['reading'] = [{'type': entity(InlineDependency).name,
                             'target': blocks[1]['id']}]
    source.write_text(json.dumps({'type': 'Tarav.Skillware.Document', 'schema_version': 1,
                                  'output': 'SKILL.md', 'blocks': blocks}))
    nodes = [{'id': b['label'], 'reference': {'type': 'Tarav.Reference.StructuredFile',
              'locator': {'path': 'src/main.json', 'pointer': f'/blocks/{i}'}}}
             for i, b in enumerate(blocks)]
    nodes[2]['parents'] = ['entry']
    nodes[3].update(parents=['vocabulary', 'bypass'])
    nodes[4]['parents'] = []
    (tmp_path / '.skw/loading.json').write_text(json.dumps({
        'type': entity(LoadingRecord).name, 'schema_version': 1, 'blocks': nodes}))
    (tmp_path / '.skw/main.json').write_text(json.dumps({
        'type': entity(SkwSkill).name, 'schema_version': 1,
        'entrypoint': 'SKILL.md', 'sources': ['.skw/src/main.json'],
        'files': ['SKILL.md'], 'loading': '.skw/loading.json'}))
    return create_runtime().load_object(tmp_path / '.skw')


def declare(p, owner, target, declaration, *, slot=None, caption=None, output=None):
    source = p.root / '.skw/src/main.json'
    data = json.loads(source.read_text())
    block = next(b for b in data['blocks'] if b['label'] == owner)
    target_block = next(b for b in data['blocks'] if b['label'] == target)
    record = {'type': entity(declaration).name, 'target': target_block['id']}
    if slot is not None:
        record.update(slot=slot, entry={'type': entity(BlockEntry).name, 'node': target})
    if caption is not None:
        record['caption'] = caption
    block.setdefault('reading', []).append(record)
    if output is not None:
        block['output'].append(output)
    source.write_text(json.dumps(data))
    return p.loading()


def test_static_paths_default_parent_and_coverage(tmp_path):
    p = package(tmp_path)
    assert p.loading().parents['vocabulary'] == ['entry']
    findings = reading_findings(p.loading())
    kinds = [f['kind'] for f in findings]
    assert kinds.count('missing-context') == 1
    assert 'path-dependent-context' in kinds
    assert {'kind': 'unreachable-block', 'block': 'orphan'} in findings
    assert p.loading().inspect('use', limit=1)['path_count'] == 2
    assert len(p.loading().inspect('use', limit=1)['paths']) == 1


# tarav.breadcrumb cd62bcd562ff3b404fa6f4a339987dfd2330a48ba753b1e78cb71ac6915d5bb8
def test_two_routes_supply_one_inline_dependency_and_explicit_poi_action(tmp_path):
    p = package(tmp_path)
    graph = p.loading()
    availability = graph.analyze()['availability']['use']['inlined']
    vocabulary = str(graph.bindings['vocabulary'][1].id)
    assert vocabulary in availability['union']
    assert vocabulary not in availability['intersection']

    collector = POICollector()
    results = run_checks(p.checks)
    missing = next(poi for result in results for poi in result.pois()
                   if poi.poi_class.__name__ == 'MissingContext')
    assert missing.evidence['finding']['path'][-2:] == ['bypass', 'use']
    assert collector.findings == []
    collector.emit(missing)
    assert collector.get(missing.identity) is missing
    with pytest.raises(POIError):
        missing.error()

    declare(p, 'entry', 'vocabulary', ConsultationLink)
    assert any(f['kind'] == 'missing-context' for f in reading_findings(p.loading()))
    section = graph.analyze(entry='use')
    assert section['availability']['use']['inlined']['intersection'] == []


def test_cli_context_defaults_to_rendered_and_preserves_json(tmp_path, capsys):
    from tarav.l3.cli.cli import main

    p = package(tmp_path)
    command = ['skw', 'skills', 'context', '--project', str(p.root),
               '--block', 'use', '--limit', '1']
    assert main(command) == 0
    rendered = capsys.readouterr().out
    assert 'block: use' in rendered
    assert 'parents: vocabulary, bypass' in rendered
    assert 'paths: 1 shown of 2' in rendered
    assert main([*command, '--rendered']) == 0
    assert capsys.readouterr().out == rendered
    assert main([*command, '--json']) == 0
    structured = json.loads(capsys.readouterr().out)
    assert structured == p.loading().inspect('use', limit=1)


def test_links_are_generated_but_do_not_imply_loaded_content(tmp_path):
    p = package(tmp_path)
    graph = declare(p, 'entry', 'vocabulary', ConsultationLink,
                    slot='vocab', caption='Read', output='{{skw:vocab}}')
    source = p.root / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][3]['reading'][0]['type'] = entity(ReferenceDependency).name
    source.write_text(json.dumps(data))
    graph = p.loading()
    assert not any(f['kind'] == 'missing-context' for f in reading_findings(graph))
    text = graph.document_text(next(iter(graph.documents.values())))
    anchor = data['blocks'][1]['id']
    assert f'[Read](SKILL.md#skw-{anchor})' in text
    assert f'<a id="skw-{anchor}"></a>' in text
    data['blocks'][3]['reading'][0]['type'] = entity(InlineDependency).name
    source.write_text(json.dumps(data))
    graph = p.loading()
    assert any(f['kind'] == 'missing-context' for f in reading_findings(graph))


def test_inclusions_generate_content_and_supply_context(tmp_path):
    p = package(tmp_path)
    graph = declare(p, 'entry', 'vocabulary', IncludesBlock,
                    slot='vocab', output='{{skw:vocab}}')
    assert not any(f['kind'] == 'missing-context' for f in reading_findings(graph))
    assert graph.render_block('entry', tmp_path / 'SKILL.md') == '# Test\nVocabulary.'
    graph = declare(p, 'vocabulary', 'entry', IncludesBlock,
                    slot='cycle', output='{{skw:cycle}}')
    assert any(f['kind'] == 'inclusion-cycle' for f in reading_findings(graph))
    with pytest.raises(ValueError, match='cycle'):
        graph.render_block('entry', tmp_path / 'SKILL.md')


def test_markdown_never_discovers_edges(tmp_path):
    p = package(tmp_path)
    source = p.root / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'].append('[Vocabulary](SKILL.md#vocabulary)')
    data['blocks'][3]['reading'][0]['type'] = entity(ReferenceDependency).name
    source.write_text(json.dumps(data))
    graph = p.loading()
    assert sum(f['kind'] == 'missing-context' for f in reading_findings(graph)) == 2


def test_disconnected_cycle_and_analysis_limit(tmp_path):
    graph = package(tmp_path).loading()
    graph.parents['orphan'] = ['orphan']
    assert any(f['kind'] == 'attachment-cycle' for f in reading_findings(graph))
    assert any(f['kind'] == 'loading-analysis-incomplete'
               for f in reading_findings(graph, limit=1))


def test_slot_error_is_not_repaired(tmp_path):
    p = package(tmp_path)
    declare(p, 'entry', 'vocabulary', ConsultationLink,
            slot='missing', caption='Read')
    assert any(f['kind'] == 'invalid-source' for f in p.check())
    assert not (tmp_path / 'SKILL.md').exists()


def test_inclusion_is_a_loading_path_for_an_otherwise_unattached_block(tmp_path):
    p = package(tmp_path)
    graph = declare(p, 'entry', 'orphan', IncludesBlock,
                    slot='extra', output='{{skw:extra}}')
    assert not any(f['kind'] == 'unreachable-block' and f['block'] == 'orphan'
                   for f in reading_findings(graph))
    assert graph.inspect('orphan')['paths'][0]['path'] == ['entry', 'orphan']


def test_cli_compile_uses_declared_primitives(tmp_path, capsys):
    from tarav.l3.cli.cli import main
    p = package(tmp_path)
    declare(p, 'entry', 'vocabulary', ConsultationLink,
            slot='read', caption='Read', output='{{skw:read}}')
    main(['skw', 'document', 'compile', '--project', str(tmp_path), '--source', 'main.json'])
    anchor = p.documents()[0].blocks['vocabulary'].id
    assert f'[Read](SKILL.md#skw-{anchor})' in (tmp_path / 'SKILL.md').read_text()
    assert '{{skw:' not in (tmp_path / 'SKILL.md').read_text()
    assert p.documents()[0].lint() == []


def test_output_link_check_does_not_create_edges(tmp_path):
    p = package(tmp_path)
    path = tmp_path / '.skw/src/main.json'
    data = json.loads(path.read_text())
    data['blocks'][0]['output'].append('[Other](other.md)')
    path.write_text(json.dumps(data))
    model = p.loading()
    assert any(f['code'] == 'unannotated-output-link' for f in model.diagnostics)
    assert model.nodes['entry'].get('links', []) == []


def test_changed_declaration_invalidates_compilation(tmp_path):
    p = package(tmp_path)
    p.build()
    path = tmp_path / '.skw/src/main.json'
    data = json.loads(path.read_text())
    from tarav.l1.skw.reading import EitherDependency
    data['blocks'][3]['reading'][0]['type'] = entity(EitherDependency).name
    path.write_text(json.dumps(data))
    assert any(f['kind'] == 'source-uncompiled' for f in p.check())


def test_invalid_block_pointer_is_reported(tmp_path):
    p = package(tmp_path)
    path = tmp_path / '.skw/loading.json'
    data = json.loads(path.read_text())
    data['blocks'][1]['reference']['locator']['pointer'] = '/blocks/99'
    path.write_text(json.dumps(data))
    findings = reading_findings(p.loading())
    assert any(f['kind'] == 'invalid-block-reference' for f in findings)
    assert any(f['kind'] == 'invalid-parent' for f in findings)


def test_empty_block_does_not_add_a_newline(tmp_path):
    p = package(tmp_path)
    source = tmp_path / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'] = []
    source.write_text(json.dumps(data))
    assert p.documents()[0].text().startswith('Vocabulary.')


def test_typed_skill_link_retains_output_and_uses_one_target(tmp_path):
    p = package(tmp_path)
    source = tmp_path / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'] = ['Read {{skw:link}} now.']
    data['blocks'].append({'id': 'link', 'type': entity(SkillLink).name,
                           'target': 'vocabulary', 'caption': 'A [link]', 'output': None})
    identify_blocks(data, scope='loading-main')
    vocabulary_id = data['blocks'][1]['id']
    link_id = data['blocks'][-1]['id']
    data['blocks'][0].setdefault('reading', []).append({
        'type': entity(IncludesBlock).name, 'target': link_id,
        'entry': {'type': entity(BlockEntry).name, 'node': 'link'}, 'slot': 'link'})
    data['blocks'][-1]['reading'] = [{
        'type': entity(ConsultationLink).name, 'target': vocabulary_id,
        'entry': {'type': entity(BlockEntry).name, 'node': 'vocabulary'}}]
    source.write_text(json.dumps(data))
    declaration = tmp_path / '.skw/loading.json'
    loading = json.loads(declaration.read_text())
    loading['blocks'].append({'id': 'link', 'reference': {
        'type': 'Tarav.Reference.StructuredFile',
        'locator': {'path': 'src/main.json', 'pointer': '/blocks/5'}},
        'parents': []})
    declaration.write_text(json.dumps(loading))

    document = p.documents()[0]
    assert 'missing-output' in {f['kind'] for f in document.lint()}
    before = source.read_bytes()
    assert document.produce('link')['output'] == [rf'[A \[link\]](SKILL.md#skw-{vocabulary_id})']
    assert source.read_bytes() != before
    document = p.documents()[0]
    assert isinstance(document.blocks['link'], SkillLink)
    assert document.blocks['link'].to_record()['output'] == [rf'[A \[link\]](SKILL.md#skw-{vocabulary_id})']
    assert not any(f['kind'] == 'stale-produced-output' for f in document.lint())
    assert vocabulary_id in p.loading().analyze()['states']['entry'][0]['referenced']
    assert f'Read [A \\[link\\]](SKILL.md#skw-{vocabulary_id}) now.' in document.text()
    assert document.compile()['written']

    data = json.loads(source.read_text())
    data['blocks'][-1]['target'] = 'bypass'
    source.write_text(json.dumps(data))
    document = p.documents()[0]
    assert 'stale-produced-output' in {f['kind'] for f in document.lint()}
    assert f'[A \\[link\\]](SKILL.md#skw-{vocabulary_id})' in document.text()
    data['blocks'][-1]['target'] = 'absent'
    source.write_text(json.dumps(data))
    before = source.read_bytes()
    with pytest.raises(ValueError, match='Unknown SkillLink target'):
        p.documents()[0].produce('link')
    assert source.read_bytes() == before
