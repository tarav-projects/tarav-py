from __future__ import annotations

from pathlib import Path

from agentos.index.linter import build_linter_config, run_linter


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _clean_index(root: Path) -> tuple[Path, Path]:
    index_dir = root / "design"
    appendix_dir = root / "appendix"
    _write(
        root / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+1]\n",
    )
    _write(
        index_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    _write(
        appendix_dir / "Example.Concept-appendix.md",
        "****\n## Example.Concept/Example.Detail\n\n- depth\n****\n",
    )
    return index_dir, appendix_dir


def _clean_depot(root: Path, *, include_appendix: bool = True) -> Path:
    depot_dir = root / "depot"
    design_dir = depot_dir / "design"
    _write(
        depot_dir / "000-INDEX.md",
        "# Agentos Index\n\n## design\n\n- `design/100-design.md` — Example.Concept[+1]\n",
    )
    _write(
        design_dir / "100-design.md",
        "****\n## Example.Concept\n\n- compact definition\n****\n",
    )
    if include_appendix:
        _write(
            depot_dir / "appendix" / "Example.Concept-appendix.md",
            "****\n## Example.Concept/Appendix\n\n- depth\n****\n",
        )
    return depot_dir


def _run(
    *,
    depot_paths: tuple[str, ...] = (),
    index_paths: tuple[str, ...] = (),
    appendix_paths: tuple[str, ...] = (),
    coverage: tuple[str, ...] = (),
    scope_paths: tuple[str, ...] = (),
    anchors: tuple[str, ...] = (),
    warn_unlinked: bool = False,
    include: tuple[str, ...] = (),
    exclude: tuple[str, ...] = (),
):
    config, raw_depot_paths, raw_index_paths, raw_appendix_paths = build_linter_config(
        depot_paths=depot_paths,
        index_paths=index_paths,
        appendix_paths=appendix_paths,
        coverage=coverage,
        scope_paths=scope_paths,
        anchors=anchors,
        warn_unlinked=warn_unlinked,
    )
    return run_linter(
        config,
        raw_depot_paths,
        raw_index_paths,
        raw_appendix_paths,
        include=include,
        exclude=exclude,
    )
