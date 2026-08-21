from __future__ import annotations

import json

from tarav.index.capture import capture_surface_lines
from tarav.index.record import IndexStore
from tarav.index_model.identity import index_line_anchor_triplet_hash


def _surfaces(root):
    depot = root / "skills" / "d"
    design = depot / "design"
    design.mkdir(parents=True)
    (depot / "000-INDEX.md").write_text("# test Index\n", encoding="utf-8")
    (design / "100-design.md").write_text(
        "****\n\n## Native.Line\n\n- [CT] markdown hosted ^c20260821-80u\n\n****\n",
        encoding="utf-8",
    )
    code = root / "src" / "product.py"
    code.parent.mkdir()
    code.write_text(
        "# $kw: Product/Check --note [DC] code hosted ^c20260821-81u\n"
        "def check():\n    pass\n",
        encoding="utf-8",
    )
    skw = root / ".skw"
    skw.mkdir()
    (skw / "skw.json").write_text(
        json.dumps(
            {
                "code_surfaces": [
                    {
                        "language": "python",
                        "include": ["src/**/*.py"],
                        "allow_points": ["file", "class", "function"],
                    }
                ]
            }
        ),
        encoding="utf-8",
    )


def _resolver(statements):
    def resolve(label):
        return {
            "record": {
                "attachment": {
                    "triplet_hash": index_line_anchor_triplet_hash(statements[label], label)
                },
                "relationships": {
                    "support": {
                        "members": [
                            {"session": "session", "message_address": f"message-{label}"}
                        ]
                    }
                },
            },
            "members": [{"standing": "MATCHED", "side": "user"}],
        }

    return resolve


def test_capture_previews_and_lands_markdown_and_skw_lines_through_one_model(
    geo, project_root
):
    _surfaces(project_root)
    resolver = _resolver(
        {
            "^c20260821-80u": "[CT] markdown hosted",
            "^c20260821-81u": "[DC] code hosted",
        }
    )

    preview = capture_surface_lines(geo, land=False, dossier_resolver=resolver)
    assert preview.clean
    assert preview.planned == ("^c20260821-80u", "^c20260821-81u")
    assert preview.created == ()
    assert IndexStore(geo).count() == 0

    landed = capture_surface_lines(geo, land=True, dossier_resolver=resolver)
    assert landed.clean
    assert landed.created == ("^c20260821-80u", "^c20260821-81u")
    records = {record.line.label: record for record in IndexStore(geo).all()}
    assert records["^c20260821-80u"].scope.address == "d/design#Native.Line"
    assert records["^c20260821-81u"].scope.address == "@src/product.py/Product/Check"

    repeated = capture_surface_lines(geo, land=True, dossier_resolver=resolver)
    assert repeated.created == ()
    assert repeated.existing == ("^c20260821-80u", "^c20260821-81u")


def test_capture_refuses_a_dossier_for_a_different_line(geo, project_root):
    _surfaces(project_root)
    resolver = _resolver(
        {
            "^c20260821-80u": "[CT] different wording",
            "^c20260821-81u": "[DC] code hosted",
        }
    )

    report = capture_surface_lines(geo, land=True, dossier_resolver=resolver)
    assert [issue.label for issue in report.unresolved] == ["^c20260821-80u"]
    assert "triplet" in report.unresolved[0].reason
    assert IndexStore(geo).all() == []
