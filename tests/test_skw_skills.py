import json

import pytest

from tarav.skw.skills import SkillPackage, SkillPackageRecord


def package(tmp_path):
    root = tmp_path / 'skill'
    (root / '.skw/src').mkdir(parents=True)
    source = {'type': 'Tarav.Skillware.Document', 'schema_version': 1,
              'output': 'SKILL.md', 'blocks': [
                  {'id': 'main', 'kind': 'literal', 'lines': ['# Skill']}]}
    (root / '.skw/src/main.skw.json').write_text(json.dumps(source))
    manifest = {'type': SkillPackageRecord.type_name, 'schema_version': 1,
                'entrypoint': 'SKILL.md', 'sources': ['.skw/src/main.skw.json'],
                'files': ['SKILL.md'], 'dependencies': []}
    (root / '.skw/skill.json').write_text(json.dumps(manifest))
    return SkillPackage(root)


def test_build_deploy_excludes_developer_surface(tmp_path):
    p = package(tmp_path)
    assert p.build() == []
    output = tmp_path / 'deployed'
    assert p.deploy(output)['findings'] == []
    assert sorted(x.name for x in output.iterdir()) == ['SKILL.md']
    assert (output / 'SKILL.md').read_text() == '# Skill\n'
    with pytest.raises(ValueError):
        p.deploy(output)


def test_consumer_edges_require_consumer_declaration(tmp_path):
    p = package(tmp_path)
    other = tmp_path / 'other'
    other.mkdir()
    (other / 'SKILL.md').write_text('# Other')
    source = p.root / '.skw/src/main.skw.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['lines'] = ['[Other](../other/SKILL.md)']
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
        (p.root / '.skw/skill.json').write_text(json.dumps(data))
        with pytest.raises(ValueError):
            SkillPackage(p.root)


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
