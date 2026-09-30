from tarav.l1.breadcrumbs import BreadcrumbStore
from tarav.l1.breadcrumbs.auditing import audit_annotations


class Workflow:
    name = 'test'

    def audit(self, context, request):
        return ()


def test_refresh_is_opt_in_append_only_and_idempotent(tmp_path):
    store = BreadcrumbStore(tmp_path / 'store')
    key = 'a' * 64
    store.create(key)
    store.attach(key, {'type': 'Example.Annotation'})
    path = tmp_path / 'note.md'
    path.write_text(f'<!-- tarav.breadcrumb {key} -->\n')
    store.observe_position(key, file=str(path), line=1)
    path.write_text('\n' + path.read_text())
    before = path.read_bytes()
    def audit(**kwargs):
        return audit_annotations(path, store=store, workflow=Workflow(), request=None, **kwargs)
    assert not audit().ok
    assert len(store.observations(key)) == 1
    result = audit(refresh_positions=True)
    assert result.ok
    assert result.to_json()['updates'][0]['code'] == 'breadcrumb-position-updated'
    assert len(store.observations(key)) == 2
    assert store.attachments(key) == ({'type': 'Example.Annotation'},)
    assert path.read_bytes() == before
    assert audit(refresh_positions=True).updates == ()
    assert len(store.observations(key)) == 2


def test_refresh_does_not_guess_between_duplicates(tmp_path):
    store = BreadcrumbStore(tmp_path / 'store')
    key = 'b' * 64
    store.create(key)
    path = tmp_path / 'note.md'
    path.write_text(f'<!-- tarav.breadcrumb {key} -->\n' * 2)
    result = audit_annotations(path, store=store, workflow=Workflow(), request=None,
                               refresh_positions=True)
    assert not result.ok
    assert not result.updates
    assert not store.observations(key)
