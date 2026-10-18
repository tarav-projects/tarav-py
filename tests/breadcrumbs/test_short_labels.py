"""Submission, audit and commit messages carry 12-character Breadcrumb labels (request 918)."""

from __future__ import annotations

import json
from pathlib import Path
import subprocess

import pytest

from tarav.l1.breadcrumbs.auditing import audit_annotations
from tarav.l1.breadcrumbs.store import BreadcrumbAmbiguous, BreadcrumbStore
from tarav.l1.breadcrumbs.surfaces import submit_annotations
from tarav.l1.breadcrumbs.workflows import BreadcrumbAnnotationWorkflow, PreparedAnnotation
from tarav.l2.breadcrumb_workflows.chatlas_context.workflow import provisional_markers
from tarav.l2.git.breadcrumbs import CommitManifest, audit_commit, commit_from_manifest

MARKER = "tarav.context abcdef12:0123456789abcdef"


class _MarkerOnly(BreadcrumbAnnotationWorkflow):
    """Submits every chatlas-context marker with one test attachment."""

    name = "test-markers"

    def prepare(self, surface, request):
        return tuple(PreparedAnnotation(item.position, "provisional", item)
                     for item in provisional_markers(surface.text, surface.language))

    def attachments(self, annotation, breadcrumb_id):
        return ({"type": "Tarav.Test.Attachment", "breadcrumb_id": breadcrumb_id},)

    def audit(self, context, request):
        return ()


def _audit(surface: Path, store: BreadcrumbStore):
    return audit_annotations(surface, store=store, workflow=_MarkerOnly(), request=None)


@pytest.mark.parametrize("name, text, rendered", [
    ("note.md", f"Text\n<!-- {MARKER} -->\n", "<!-- {label} -->"),
    ("code.py", f"value = 1  # {MARKER}\n", "value = 1  # {label}"),
    ("view.ts", f"export const a = 1; // {MARKER}\n", "export const a = 1; // {label}"),
])
def test_submission_writes_twelve_characters_and_audit_resolves_them(
    tmp_path: Path, name: str, text: str, rendered: str,
) -> None:
    surface = tmp_path / name
    surface.write_text(text, encoding="utf-8")
    store = BreadcrumbStore(tmp_path / "store")
    (submitted,) = submit_annotations(surface, store=store, workflow=_MarkerOnly(),
                                      request=None).breadcrumbs
    assert submitted.label == f"tarav.breadcrumb {submitted.id[:12]}"
    assert rendered.format(label=submitted.label) in surface.read_text(encoding="utf-8")

    result = _audit(surface, store)
    assert result.ok and result.check_pois == ()
    (audited,) = result.context.breadcrumbs
    assert (audited.breadcrumb_id, audited.label) == (submitted.id, submitted.label)
    assert audited.resolution.status == "resolved"


def test_a_full_label_already_on_a_surface_still_resolves(tmp_path: Path) -> None:
    store = BreadcrumbStore(tmp_path / "store")
    breadcrumb_id = str(store.create().records.to_record()["id"])
    surface = tmp_path / "old.md"
    surface.write_text(f"Text\n<!-- tarav.breadcrumb {breadcrumb_id} -->\n", encoding="utf-8")
    store.observe_position(breadcrumb_id, file=str(surface), line=2)
    store.attach(breadcrumb_id, {"type": "Tarav.Test.Attachment"})

    result = _audit(surface, store)
    assert result.ok and result.check_pois == ()
    assert result.context.breadcrumbs[0].breadcrumb_id == breadcrumb_id


# tarav.breadcrumb 2b8b911a5372
def test_a_later_addition_makes_a_surface_label_ambiguous(tmp_path: Path) -> None:
    surface = tmp_path / "note.md"
    surface.write_text(f"Text\n<!-- {MARKER} -->\n", encoding="utf-8")
    store = BreadcrumbStore(tmp_path / "store")
    (submitted,) = submit_annotations(surface, store=store, workflow=_MarkerOnly(),
                                      request=None).breadcrumbs
    colliding = submitted.id[:12] + ("0" if submitted.id[12] != "0" else "1") * 52
    store.create(colliding)

    result = _audit(surface, store)
    (poi,) = result.check_pois
    assert type(poi).__name__ == "LabelAmbiguous"
    assert submitted.id in poi.message and colliding in poi.message


# tarav.breadcrumb 7c8583748c90
def test_a_colliding_submission_leaves_the_surface_untouched(
    tmp_path: Path, monkeypatch,
) -> None:
    store = BreadcrumbStore(tmp_path / "store")
    existing = "0123456789ab" + "0" * 52
    store.create(existing)
    drawn = iter(["fedcba987654" + "1" * 52, "0123456789ab" + "2" * 52])
    monkeypatch.setattr("tarav.l1.breadcrumbs.store.secrets.token_hex", lambda size: next(drawn))
    surface = tmp_path / "note.md"
    original = f"One\n<!-- {MARKER} -->\n\nTwo\n<!-- {MARKER} -->\n"
    surface.write_text(original, encoding="utf-8")

    with pytest.raises(BreadcrumbAmbiguous) as raised:
        submit_annotations(surface, store=store, workflow=_MarkerOnly(), request=None)
    assert existing in raised.value.candidates
    assert surface.read_text(encoding="utf-8") == original
    assert store.observations("fedcba987654") == ()


def _git(repository: Path, *arguments: str) -> str:
    return subprocess.run(["git", "-C", str(repository), *arguments], check=True,
                          capture_output=True, text=True).stdout


def test_commit_messages_carry_twelve_characters(tmp_path: Path) -> None:
    repository = tmp_path / "repo"
    repository.mkdir()
    _git(repository, "init", "-q")
    _git(repository, "config", "user.email", "test@example.com")
    _git(repository, "config", "user.name", "Test")
    (repository / "file.txt").write_text("content\n", encoding="utf-8")
    store = BreadcrumbStore(tmp_path / "store")
    manifest = CommitManifest.records.from_record({
        "type": "Tarav.Git.CommitEvidence.Manifest", "repository": str(repository),
        "files": ["file.txt"], "message": f"Subject\n\n- file.txt: added\n<!-- {MARKER} -->",
        "allow_empty": False})

    registered = commit_from_manifest(manifest, store=store, workflow=_MarkerOnly(), request=None)
    (breadcrumb_id,) = registered.breadcrumb_ids
    message = _git(repository, "log", "-1", "--format=%B")
    assert f"<!-- tarav.breadcrumb {breadcrumb_id[:12]} -->" in message.splitlines()
    assert json.dumps(breadcrumb_id) in message  # the evidence envelope keeps the full ID

    result = audit_commit(repository, "HEAD", store=store, workflow=_MarkerOnly(), request=None)
    assert result.ok and result.check_pois == ()
    assert result.context.breadcrumbs[0].breadcrumb_id == breadcrumb_id
    assert result.context.breadcrumbs[0].resolution.status == "resolved"
