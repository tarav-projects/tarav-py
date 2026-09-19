import json

from tarav.chatlas.references import ChatlasTurnReference
from tarav.skw.document import Document


def test_chatlas_exact_turn_and_grounding_role(tmp_path, monkeypatch):
    import tarav.chatlas.references as refs

    turn = {'side': 'user', 'turn_address': 'a' * 64, 'turn_hash': 'b' * 64,
            'message_refs': [{'message_address': 'c' * 64, 'message_hash': 'd' * 64}]}
    message = {'message_address': 'c' * 64, 'message_hash': 'd' * 64,
               'text': 'Exact user wording'}
    monkeypatch.setattr(refs, 'provide_normal_model', lambda **kw: {'turns': [turn], 'messages': [message]})
    reference = {'type': ChatlasTurnReference.type_name, 'locator': {
        'session_identity': 'e' * 64, 'turn_address': 'a' * 64, 'turn_hash': 'b' * 64}}
    path = tmp_path / '.skw/src/demo.skw.json'
    path.parent.mkdir(parents=True)
    data = {'type': 'Tarav.Skillware.Document', 'schema_version': 1, 'output': 'demo.md',
            'blocks': [{'id': 'body', 'kind': 'generation', 'prompt': [], 'output': ['Text'],
                        'context': [{'kind': 'reference', 'roles': ['maintenance', 'user-grounding'],
                                     'reference': reference}]}]}
    path.write_text(json.dumps(data))
    doc = Document(path)
    assert doc.context('body')[0]['turn_hash'] == 'b' * 64
    assert 'Exact user wording' in doc.read_context('body', 0)['text']
    doc.observe_context('body')
    assert doc.compile()['findings'] == []
    turn['side'] = 'agent'
    assert any('User Turn' in f['detail'] for f in doc.lint())
    turn['turn_hash'] = 'f' * 64
    assert not ChatlasTurnReference(reference).resolve().ok


def test_roles_control_tracking_and_unknown_roles_are_findings(tmp_path):
    source = tmp_path / '.skw/src/demo.skw.json'
    source.parent.mkdir(parents=True)
    target = tmp_path / 'input.txt'
    target.write_text('old')
    data = {'type': 'Tarav.Skillware.Document', 'schema_version': 1, 'output': 'out.md',
        'blocks': [{'id': 'body', 'kind': 'generation', 'prompt': [], 'output': ['output'],
                    'context': [{'kind': 'reference', 'roles': ['maintenance'], 'reference': {
                        'type': 'Tarav.Reference.StructuredFile', 'locator': {'path': '../../input.txt'}}}]}]}
    source.write_text(json.dumps(data))
    doc = Document(source)
    doc.observe_context('body')
    doc.compile()
    target.write_text('new')
    assert not doc.lint()
    data['blocks'][0]['context'][0]['roles'].append('dependency')
    source.write_text(json.dumps(data))
    doc = Document(source)
    doc.observe_context('body')
    target.write_text('newer')
    assert 'stale-context' in {f['kind'] for f in doc.lint()}
    data['blocks'][0]['context'][0]['roles'] = ['invented']
    source.write_text(json.dumps(data))
    assert 'Unknown context roles' in Document(source).context('body')[0]['finding']
