"""Capture proposals remain outside the Model until exact reviewed landing."""
import hashlib
import json

import pytest

from tarav.l1.grounding import SupportMember
from tarav.l1.lines import Line
from tarav.l1.notebook import Notebook as Storage
from tarav.l1.notebook.evidence import ReviewedLine
from tarav.l2.notebook import Notebook
from tarav.l2.notebook_draft import NotebookDraft
from tarav.l3.runtime import create_runtime
from test_notebook_evidence import chat as chat_fixture, ship

chat = chat_fixture


def hashes(path):
    return {str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in path.rglob('*') if p.is_file() and '.git' not in p.parts}


@pytest.fixture
def book(tmp_path, monkeypatch):
    monkeypatch.setenv('TARAV_RECORDS', str(tmp_path / 'evidence'))
    return Notebook(id=ship(), storage=Storage(tmp_path / 'notebook', records=create_runtime().records)).create()


def approve(draft, add, token='capture:one'):
    proposal = add('agent', draft.propose(token))
    return proposal, add('user', '::approve ' + token)


# tarav.breadcrumb 04a258e42a38
def test_nested_additions_survive_plan_roundtrip_and_land_with_independent_evidence(book, tmp_path, chat):
    add, _ = chat
    user = add('user', 'Keep support and review independent.')
    another = add('user', 'The review concerns exact wording.')
    before = hashes(tmp_path)
    draft = book.draft()
    block = draft.add_block()
    child = draft.add_block(parent=block)
    line = draft.add('Keep support and review independent.', block=child)
    proposal, approval = approve(draft, add)
    plan = json.loads(json.dumps(draft.export()))
    restored = NotebookDraft.restore(book, plan)
    assert restored.propose('capture:one') == draft.propose('capture:one')
    assert hashes(tmp_path) == before
    review = restored.land(proposal=proposal, approval=approval, producer=proposal,
                           support={line.id: [SupportMember(user), SupportMember(another)]})
    loaded = book.storage.load(line.id)
    assert isinstance(loaded, ReviewedLine)
    assert loaded.scope.id == child.id and loaded.scope.parent.id == block.id
    assert len(loaded.support_ships) == 2 and loaded.review_ships == [review.id]
    current = book.storage.load(book.id)
    assert current.inspect(loaded)['support'] == ()
    assert current.inspect(loaded)['review'] == ()
    assert [len(record.typed.members) for record in current.evidence.support_records(loaded)] == [1, 1]
    with pytest.raises(FileExistsError):
        restored.land(proposal=proposal, approval=approval, producer=proposal)


def test_amendment_keeps_ship_and_prior_evidence_and_requires_unchanged_source(book, tmp_path, chat):
    add, _ = chat
    user = add('user', 'Preserve earlier claims when wording evolves.')
    producer = add('agent', 'Recording the design.')
    original = book.capture('Keep claims.', root=user, producer=producer)
    old_support = original.support_ships[0]
    draft = book.draft()
    draft.amend(original.id, 'Preserve earlier claims.')
    proposal, approval = approve(draft, add)
    assert book.storage.load(original.id).text == 'Keep claims.'
    review = draft.land(proposal=proposal, approval=approval, producer=proposal,
                        support={original.id: [SupportMember(user)]})
    loaded = book.storage.load(original.id)
    assert loaded.id == original.id and loaded.text == 'Preserve earlier claims.'
    assert loaded.support_ships[0] == old_support and len(loaded.support_ships) == 2
    assert loaded.review_ships == [review.id]
    stale = book.storage.load(book.id).draft()
    stale.amend(original.id, 'A later candidate.')
    p, a = approve(stale, add, 'capture:stale')
    live = book.storage.load(original.id)
    live.text = 'Someone else changed this.'
    book.storage.save(live)
    before = hashes(tmp_path)
    with pytest.raises(ValueError, match='context changed'):
        stale.land(proposal=p, approval=a, producer=p)
    assert hashes(tmp_path) == before


@pytest.mark.parametrize('failure', ['approval', 'wording', 'type', 'context', 'token'])
def test_invalid_or_changed_proposals_write_nothing(book, tmp_path, chat, failure):
    add, _ = chat
    context = Line(id=ship(), text='This context is stable.', scope=book)
    book.append(context)
    book.save()
    draft = book.draft()
    line = draft.add('Use exact wording.')
    rendered = draft.propose('capture:guard')
    if failure == 'wording':
        rendered = rendered.replace('Use exact wording.', 'Use different wording.')
    if failure == 'type':
        rendered = rendered.replace('Tarav.Notebook.ReviewedLine', 'Another.Type')
    proposal = add('agent', rendered)
    approval = add('agent' if failure == 'approval' else 'user', '::approve capture:guard')
    if failure == 'context':
        context.text = 'The authoring context changed.'
        book.storage.save(context)
    if failure == 'token':
        draft.amend(line.id, 'Changed after presentation.')
        with pytest.raises(ValueError, match='new token'):
            draft.propose('capture:guard')
    before = hashes(tmp_path)
    with pytest.raises(ValueError):
        draft.land(proposal=proposal, approval=approval, producer=proposal)
    assert hashes(tmp_path) == before


def test_separate_approved_blocks_merge_without_losing_unrelated_additions(book, chat):
    add, _ = chat
    first, second = book.draft(), book.draft()
    a, b = first.add_block(), second.add_block()
    first.add('First argument.', block=a)
    second.add('Second argument.', block=b)
    p1, a1 = approve(first, add, 'capture:first')
    p2, a2 = approve(second, add, 'capture:second')
    first.land(proposal=p1, approval=a1, producer=p1)
    second.land(proposal=p2, approval=a2, producer=p2)
    loaded = book.storage.load(book.id)
    assert [block.id for block in loaded.contents] == [a.id, b.id]
    assert loaded.inspect(loaded.contents[1].contents[0])['support'][0].kind == 'Missing'


def test_plain_line_is_not_silently_retyped(book, tmp_path):
    old = Line(id=ship(), text='Earlier plain text.', scope=book)
    book.append(old)
    book.save()
    draft = book.draft()
    before = hashes(tmp_path)
    with pytest.raises(TypeError, match='does not migrate Types'):
        draft.amend(old.id, 'Supported wording.')
    assert type(book.storage.load(old.id)) is Line
    assert hashes(tmp_path) == before
