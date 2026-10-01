import json
from pathlib import Path

from tarav.l3.cli.cli import main
from tarav.l1.blessings import BlessablePOI
from test_skw_skills import package


def test_skw_bless_inspect_score_and_paged_reporting(tmp_path, capsys):
    p = package(tmp_path)
    # This fixture has no loading model. Use the real loading fixture so
    # annotation omissions are emitted by its actual conformance check.
    from test_skw_loading import package as loading_package
    root = tmp_path / 'loading'
    p = loading_package(root)
    source = root / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'].append('[Existing](SKILL.md)')
    source.write_text(json.dumps(data))
    p.build()
    collector = p.evaluate()
    finding = next(f for f in collector.pois if isinstance(f, BlessablePOI))
    assert Path(type(finding).help()['source_path']).name == 'pois.py'
    actor = tmp_path / 'actor.json'
    actor.write_text(json.dumps({'type': 'Example.Agent', 'locator': {'session': 'fixture'}}))
    why = tmp_path / 'rationale.txt'
    why.write_text('The fixture deliberately retains a link outside the declared graph.')
    args = ['--project', str(root)]
    assert main(['skw', 'skills', 'bless', *args, '--id', finding.identity,
                 '--actor-file', str(actor), '--rationale-file', str(why), '--json']) == 0
    accepted = json.loads(capsys.readouterr().out)
    assert (root / '.skw/blessings' / (accepted['id'] + '.json')).exists()
    assert main(['skw', 'skills', 'check', *args, '--limit', '1', '--json']) == 1
    report = json.loads(capsys.readouterr().out)
    assert report['shown'] == 1 and report['by_blessing']['blessed'] == 1
    assert report['by_assessment_finding']['blessing-unassessed'] == 1
    assert main(['skw', 'skills', 'poi', *args, '--id', finding.identity, '--json']) == 0
    detail = json.loads(capsys.readouterr().out)
    assert detail['blessing']['status'] == 'blessed' and detail['evidence']
    assert main(['skw', 'skills', 'assess-blessing', *args, '--blessing-id', accepted['id'],
                 '--actor-file', str(actor), '--rationale-file', str(why),
                 '--assertion', 'acceptance-justified', '--score', '0.8', '--json']) == 0
    capsys.readouterr()
    data['blocks'][0]['output'].append('Changed surface.')
    source.write_text(json.dumps(data))
    assert p.blessings.standing(p.evaluate().get(finding.identity))['status'] == 'stale'


def test_skw_poi_commands_default_to_rendered(tmp_path, capsys):
    from test_skw_loading import package as loading_package

    root = tmp_path / 'loading'
    p = loading_package(root)
    source = root / '.skw/src/main.json'
    data = json.loads(source.read_text())
    data['blocks'][0]['output'].append('[Existing](SKILL.md)')
    source.write_text(json.dumps(data))
    p.build()
    finding = next(f for f in p.evaluate().pois if isinstance(f, BlessablePOI))
    actor = tmp_path / 'actor.json'
    actor.write_text(json.dumps({'type': 'Example.Agent', 'locator': {'session': 'fixture'}}))
    why = tmp_path / 'rationale.txt'
    why.write_text('This fixture deliberately retains the link.')
    args = ['--project', str(root)]

    assert main(['skw', 'skills', 'check', *args, '--limit', '1']) == 1
    check_output = capsys.readouterr().out
    assert check_output.startswith('check: ')
    assert 'POIs' in check_output
    assert main(['skw', 'skills', 'check', *args, '--limit', '1', '--rendered']) == 1
    assert capsys.readouterr().out == check_output

    assert main(['skw', 'skills', 'check', *args]) == 1
    assert finding.identity[:12] in capsys.readouterr().out
    assert main(['skw', 'skills', 'poi', *args, '--id', finding.identity[:12]]) == 0
    assert capsys.readouterr().out.startswith('POI: UnannotatedOutputLink\n')

    assert main(['skw', 'skills', 'bless', *args, '--id', finding.identity[:12],
                 '--actor-file', str(actor), '--rationale-file', str(why)]) == 0
    blessed = capsys.readouterr().out
    assert blessed.startswith('Blessing recorded: ')
    blessing_id = next((root / '.skw/blessings').glob('*.json')).stem

    assert main(['skw', 'skills', 'assess-blessing', *args,
                 '--blessing-id', blessing_id, '--actor-file', str(actor),
                 '--rationale-file', str(why), '--assertion', 'acceptance-justified',
                 '--score', '0.8']) == 0
    assert capsys.readouterr().out.startswith('Blessing assessment recorded: ')
