from tarav.l0.kernel import TaravClass, entity

import json

import pytest
from skw_records import identify_blocks

from tarav.l3.runtime import create_runtime
from tarav.l1.skw.depot import SkwDepot
from tarav.l2.skw.skills import SkwSkill


def package(tmp_path):
    root = tmp_path / 'skill'
    (root / '.skw/src').mkdir(parents=True)
    source = {'type': 'Tarav.Skillware.Document', 'schema_version': 1,
              'output': 'SKILL.md', 'blocks': [
                  {'id': 'main', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['# Skill']}]}
    identify_blocks(source, scope="skill-main")
    (root / '.skw/src/main.skw.json').write_text(json.dumps(source))
    manifest = {'type': entity(SkwSkill).name, 'schema_version': 1,
                'entrypoint': 'SKILL.md', 'sources': ['.skw/src/main.skw.json'],
                'files': ['SKILL.md'], 'dependencies': []}
    (root / '.skw/main.json').write_text(json.dumps(manifest))
    return create_runtime().load_object(root / '.skw')


def test_build_deploy_excludes_developer_surface(tmp_path):
    p = package(tmp_path)
    assert p.build() == []
    output = tmp_path / 'deployed'
    assert p.deploy(output)['findings'] == []
    assert sorted(x.name for x in output.iterdir()) == ['SKILL.md']
    assert (output / 'SKILL.md').read_text() == '# Skill\n'
    with pytest.raises(ValueError):
        p.deploy(output)


def test_build_and_deploy_cli_default_to_rendered(tmp_path, capsys):
    from tarav.l3.cli.cli import main

    p = package(tmp_path)
    base = ['--project', str(p.root)]
    assert main(['skw', 'skills', 'build', *base]) == 0
    rendered = capsys.readouterr().out
    assert rendered == 'build: 0 POIs\nshowing: 0 of 0 matching\n'
    assert main(['skw', 'skills', 'build', *base, '--rendered']) == 0
    assert capsys.readouterr().out == rendered
    assert main(['skw', 'skills', 'build', *base, '--json']) == 0
    structured = json.loads(capsys.readouterr().out)
    assert structured['total'] == 0
    assert structured['items'] == []

    destination = tmp_path / 'deployed-cli'
    assert main(['skw', 'skills', 'deploy', *base,
                 '--destination', str(destination)]) == 0
    output = capsys.readouterr().out
    assert output.startswith(f'deployed: {destination}\nfiles: 1\n')
    assert 'deploy check: 0 POIs' in output


def test_consumer_edges_require_consumer_declaration(tmp_path):
    p = package(tmp_path)
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'SKILL.md').write_text('# Other')
    source = p.root / '.skw/src/main.skw.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'] = ['[Other](../other/SKILL.md)']
    source.write_text(json.dumps(data))
    p.data['dependencies'] = [{'kind': 'skill', 'path': '../other',
                               'purposes': ['developer']}]
    assert any(f['kind'] == 'undeclared-consumer-link' for f in p.build())
    p.data['dependencies'][0]['purposes'].append('consumer')
    assert p.check() == []


def test_reject_escape_and_build_surface_deployment(tmp_path):
    p = package(tmp_path)
    for path in ('../outside', 'a/../SKILL.md', '.', '.skw/src/main.skw.json'):
        data = dict(p.data, files=['SKILL.md', path])
        (p.depot / 'main.json').write_text(json.dumps(data))
        with pytest.raises(ValueError):
            create_runtime().load_object(p.depot).data


def test_deploy_cannot_create_product_inside_source_package(tmp_path):
    p = package(tmp_path)
    p.build()
    with pytest.raises(ValueError, match='outside'):
        p.deploy(p.root / 'dist')
    assert not (p.root / 'dist').exists()


def test_duplicate_output_rejected_before_build(tmp_path):
    p = package(tmp_path)
    original = p.root / p.data['sources'][0]
    second = original.with_name('second.skw.json')
    second.write_bytes(original.read_bytes())
    p.data['sources'].append(str(second.relative_to(p.root)))
    with pytest.raises(ValueError, match='Duplicate'):
        p.build()
    assert not (p.root / 'SKILL.md').exists()


def test_runtime_load_specializes_skw_depot_and_accepts_stale_label(tmp_path):
    skill = package(tmp_path)
    data = skill.to_record()
    data['type'] = {'uuid': str(entity(SkwSkill).id), 'label': 'renamed Skill type'}
    (skill.depot / 'main.json').write_text(json.dumps(data))
    loaded = create_runtime().load_object(skill.depot)
    assert isinstance(loaded, SkwSkill)
    assert loaded.data['schema_version'] == 1


def test_runtime_load_can_select_another_skw_depot_subtype(tmp_path):
    from tarav.l0.kernel import TypeRegistry, TypeShip

    class OtherDepot(SkwDepot):
        @classmethod
        def class_entity(cls) -> TaravClass:
            return TaravClass(
                target=cls,
                id=TypeShip('e8387eeb-baa5-4f03-8ec8-9330017e6864'),
                name='Test.OtherSkwDepot',
            )

    depot = tmp_path / '.skw'
    depot.mkdir()
    (depot / 'main.json').write_text(json.dumps({'type': entity(OtherDepot).name}))
    loaded = TypeRegistry(SkwDepot, [SkwDepot, OtherDepot]).load(depot)
    assert type(loaded) is OtherDepot


def test_runtime_load_rejects_unknown_depot_type(tmp_path):
    depot = tmp_path / '.skw'
    depot.mkdir()
    (depot / 'main.json').write_text(json.dumps({'type': 'Test.UnknownSkwDepot'}))
    with pytest.raises(ValueError, match='not registered'):
        create_runtime().load_object(depot)


def test_document_dispatch_uses_directory_entry_priority_and_concrete_type(tmp_path):
    from tarav.l2.skw.skills import skill_document

    skill = package(tmp_path)
    runtime = create_runtime()
    preferred = skill.depot / '__tarav.json'
    preferred.write_text(json.dumps({'type': entity(SkwDepot).name}))
    document = skill_document('main.skw.json', project=skill.root,
                              registry=runtime.records)
    assert document.data['output'] == 'SKILL.md'
    preferred.write_text(json.dumps({'type': 'Unknown.Depot'}))
    with pytest.raises(ValueError, match='not registered'):
        skill_document('main.skw.json', project=skill.root, registry=runtime.records)


def test_skill_validation_tracks_mutated_records(tmp_path):
    skill = package(tmp_path)
    assert skill.data['schema_version'] == 1
    assert skill._record is not None
    skill._record['files'] = ['../escape']
    with pytest.raises(ValueError, match='relative path'):
        _ = skill.data
    assert skill.check()


def test_skill_shape_is_checked_when_its_operation_reads_the_record(tmp_path):
    depot = tmp_path / '.skw'
    depot.mkdir()
    (depot / 'main.json').write_text(json.dumps({
        'type': entity(SkwSkill).name, 'schema_version': 1,
    }))
    skill = create_runtime().load_object(depot)
    with pytest.raises(KeyError, match='sources'):
        skill.data


def test_depot_root_is_canonical_for_a_relative_path_with_parent_segments(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    skill = package(tmp_path)
    relative = 'skill/../skill/.skw'
    loaded = create_runtime().load_object(relative)
    assert loaded.root == skill.root


def test_navigation_is_selective_and_does_not_resolve_context(tmp_path, capsys):
    from tarav.l3.cli.cli import main

    skill = package(tmp_path)
    source = skill.root / skill.data['sources'][0]
    data = json.loads(source.read_text())
    data['blocks'][0]['context'] = [{'kind': 'reference', 'reference': {
        'type': 'Unknown.Reference', 'locator': {'path': 'missing'}}}]
    data['blocks'].append({'id': 'second', 'type': 'Tarav.Skillware.LiteralBlock', 'output': ['Other']})
    identify_blocks(data, scope="skill-main")
    source.write_text(json.dumps(data))
    assert skill.ls()['items'][0]['source'] == 'main.skw.json'
    page = skill.ls(source='main.skw.json', limit=1)
    assert page['total'] == 2 and page['next_offset'] == 1
    assert page['items'] == [{'block': 'main', 'id': data['blocks'][0]['id'],
                              'type': 'Tarav.Skillware.LiteralBlock'}]
    assert skill.ls(source='main.skw.json', offset=1)['items'][0]['block'] == 'second'
    assert skill.read_block(source='main.skw.json', block='main')['block']['context']
    assert skill.read_block(source='main.skw.json', block=data['blocks'][0]['id'])['block']['label'] == 'main'
    with pytest.raises(ValueError):
        skill.read_block(source='../main.json', block='main')
    assert main(['skw', 'skills', 'ls', '--project', str(skill.root), '--limit', '1']) == 0
    rendered = capsys.readouterr().out
    assert 'main.skw.json' in rendered
    assert 'Showing 1 of 1.' in rendered
    assert main(['skw', 'skills', 'ls', '--project', str(skill.root), '--limit', '1',
                 '--rendered']) == 0
    assert capsys.readouterr().out == rendered
    assert main(['skw', 'skills', 'ls', '--project', str(skill.root), '--limit', '1',
                 '--json']) == 0
    assert json.loads(capsys.readouterr().out) == skill.ls(limit=1)
    assert main(['skw', 'skills', 'read', '--project', str(skill.root),
                 '--source', 'main.skw.json', '--block', 'main']) == 0
    rendered = capsys.readouterr().out
    assert rendered.startswith('main  Tarav.Skillware.LiteralBlock\n')
    assert rendered.endswith('# Skill\n')
    assert main(['skw', 'skills', 'read', '--project', str(skill.root),
                 '--source', 'main.skw.json', '--block', 'main', '--json']) == 0
    assert json.loads(capsys.readouterr().out) == skill.read_block(
        source='main.skw.json', block='main'
    )


def test_cli_explains_legacy_ancestor_depot(tmp_path, monkeypatch, capsys):
    from tarav.l3.cli.cli import main

    (tmp_path / '.skw').mkdir()
    (tmp_path / '.skw/skw.json').write_text('{"depots": ["skills/pkg"]}')
    child = tmp_path / 'skills/pkg'
    child.mkdir(parents=True)
    monkeypatch.chdir(child)
    assert main(['skw', 'skills', 'ls', '--limit', '5']) == 1
    output = capsys.readouterr()
    assert str(tmp_path / '.skw') in output.err
    assert 'no typed entry record' in output.err
    assert '--project' in output.err
    assert 'Traceback' not in output.err
    assert not (tmp_path / '.skw/main.json').exists()
