from __future__ import annotations

from tarav.l0.kernel import entity

from tarav.breadcrumb_workflows.chatlas_context import (
    ChatlasContextBreadcrumbWorkflow,
    ChatlasContextRequest,
)
from tarav.breadcrumbs import (
    BreadcrumbAnnotationWorkflow,
    BreadcrumbStore,
    PreparedAnnotation,
    SurfaceMarker,
    submit_annotations,
)
from tarav.chatlas.references import ChatlasTurnReference


IDENTITY = "1a2b3c4d" + "0" * 56
TURN_HASH = "d" * 64
TURN_ADDRESS = "e" * 64


def _resolver(alias: str, prefix: str):
    assert alias == IDENTITY[:8]
    assert TURN_HASH.startswith(prefix)
    return {
        "type": entity(ChatlasTurnReference).name,
        "locator": {
            "session_identity": IDENTITY,
            "turn_address": TURN_ADDRESS,
            "turn_hash": TURN_HASH,
        },
    }


def _submit_chatlas_markers(surface, store):
    return submit_annotations(
        surface,
        store=store,
        workflow=ChatlasContextBreadcrumbWorkflow(),
        request=ChatlasContextRequest(resolver=_resolver),
    )


def test_markdown_submission_ignores_fences_and_resolves_canonical_label(tmp_path):
    surface = tmp_path / "note.md"
    surface.write_text(
        f"<!-- tarav.sessions\n{IDENTITY[:8]} = codex:session @${IDENTITY}\n".replace(
            "@$", "@"
        )
        + "-->\n"
        "paragraph\n"
        f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]} -->\n"
        "```md\n"
        f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]} -->\n"
        "```\n",
        encoding="utf-8",
    )
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    result = _submit_chatlas_markers(surface, store)

    assert len(result.breadcrumbs) == 1
    submitted = result.breadcrumbs[0]
    rewritten = surface.read_text()
    assert f"<!-- {submitted.label} -->" in rewritten
    assert rewritten.count("tarav.context") == 1
    assert store.resolve(submitted.id).ok
    attachment = store.attachments(submitted.id)[0]
    assert attachment["context"]["locator"]["turn_hash"] == TURN_HASH


def test_python_submission_uses_tokenized_comments_not_strings(tmp_path):
    surface = tmp_path / "module.py"
    provisional = f"tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]}"
    surface.write_text(
        f'value = "# {provisional}"\n# {provisional}\n',
        encoding="utf-8",
    )
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    result = _submit_chatlas_markers(surface, store)

    rewritten = surface.read_text()
    assert f'value = "# {provisional}"' in rewritten
    assert f"# {result.breadcrumbs[0].label}" in rewritten
    assert store.resolve(result.breadcrumbs[0].id).ok


class _ExampleWorkflow(BreadcrumbAnnotationWorkflow):
    name = "example"

    def prepare(self, surface, request):
        assert request == {"meaning": "example"}
        marker = "EXAMPLE"
        start = surface.text.index(marker)
        return (
            PreparedAnnotation(
                SurfaceMarker(1, start, start + len(marker)),
                marker,
                None,
            ),
        )

    def attachments(self, annotation, breadcrumb_id):
        assert annotation.state is None
        return ({"type": "Example.Breadcrumb.Attachment", "id": breadcrumb_id},)

    def audit(self, context, request):
        assert request == {"meaning": "example"}
        return ()


def test_generic_submission_accepts_an_independent_workflow(tmp_path):
    surface = tmp_path / "note.md"
    surface.write_text("EXAMPLE\n", encoding="utf-8")
    store = BreadcrumbStore(tmp_path / "breadcrumbs")

    result = submit_annotations(
        surface,
        store=store,
        workflow=_ExampleWorkflow(),
        request={"meaning": "example"},
    )

    assert result.workflow == "example"
    assert surface.read_text().startswith("<!-- tarav.breadcrumb ")
    assert store.attachments(result.breadcrumbs[0].id) == (
        {"type": "Example.Breadcrumb.Attachment", "id": result.breadcrumbs[0].id},
    )
