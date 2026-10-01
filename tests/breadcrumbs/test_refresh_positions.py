from tarav.l1.breadcrumbs import BreadcrumbStore
from tarav.l1.breadcrumbs.auditing import audit_annotations
from tarav.l1.checks import CheckPOI
from tarav.l1.poi import NotificationPOI


class Workflow:
    name = 'test'

    def audit(self, context, request):
        return ()


# tarav.breadcrumb 7d1653f323416c4b29b1ac815541cc406ae9051d39be08c3c8c8229fa63bfea1
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
    assert isinstance(audit().findings[0], CheckPOI)
    assert audit().findings[0].check is not None
    check_context = audit().findings[0].check.context()
    assert "audit" in {entry.name for entry in check_context.ls()}
    assert check_context.open("audit").to_record()["value"]["surface"] == str(path)
    assert len(store.observations(key)) == 1
    result = audit(refresh_positions=True)
    assert result.ok
    assert result.notifications[0].code == 'breadcrumb-position-updated'
    assert isinstance(result.pois[0], NotificationPOI)
    assert len(store.observations(key)) == 2
    assert store.attachments(key) == ({'type': 'Example.Annotation'},)
    assert path.read_bytes() == before
    assert audit(refresh_positions=True).notifications == ()
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
    assert not result.notifications
    assert not store.observations(key)
