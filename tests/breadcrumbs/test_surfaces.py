from __future__ import annotations

from tarav.breadcrumbs import BreadcrumbStore, submit_chatlas_context
from tarav.chatlas.references import ChatlasTurnReference


IDENTITY = "1a2b3c4d" + "0" * 56
TURN_HASH = "d" * 64
TURN_ADDRESS = "e" * 64


def _resolver(alias: str, prefix: str):
    assert alias == IDENTITY[:8]
    assert TURN_HASH.startswith(prefix)
    return {
        "type": ChatlasTurnReference.type_name,
        "locator": {
            "session_identity": IDENTITY,
            "turn_address": TURN_ADDRESS,
            "turn_hash": TURN_HASH,
        },
    }


def test_markdown_submission_ignores_fences_and_resolves_canonical_label(tmp_path):
    surface = tmp_path / "note.md"
    surface.write_text(
        "<!-- tarav.sessions\n"
        f"{IDENTITY[:8]} = codex:session @${IDENTITY}\n".replace("@$", "@")
        + "-->\n"
        "paragraph\n"
        f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]} -->\n"
        "```md\n"
        f"<!-- tarav.context {IDENTITY[:8]}:{TURN_HASH[:16]} -->\n"
        "```\n",
        encoding="utf-8",
    )
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    result = submit_chatlas_context(surface, store=store, resolver=_resolver)

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
        f'value = "# {provisional}"\n'
        f"# {provisional}\n",
        encoding="utf-8",
    )
    store = BreadcrumbStore(tmp_path / "breadcrumbs")
    result = submit_chatlas_context(surface, store=store, resolver=_resolver)

    rewritten = surface.read_text()
    assert f'value = "# {provisional}"' in rewritten
    assert f"# {result.breadcrumbs[0].label}" in rewritten
    assert store.resolve(result.breadcrumbs[0].id).ok
