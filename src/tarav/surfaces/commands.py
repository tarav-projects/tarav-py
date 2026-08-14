# $kw: ^native-surface-cli --from Normalization.Pipeline --from Floor.Model --note [DC] named-option CLI exposes native normal models without downstream adaptation ^c20260812-0u
"""CLI inspection of native surface normal models."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

from tarav._core.errors import CliError

from .markdown import normalize_markdown
from .python import normalize_python


_EXTENSION_LANGUAGES = {
    ".md": "markdown",
    ".markdown": "markdown",
    ".py": "python",
    ".pyi": "python",
}
_NORMALIZERS = {
    "markdown": normalize_markdown,
    "python": normalize_python,
}


def _resolve_language(path: Path, explicit: str | None) -> str:
    if explicit is not None:
        return explicit
    language = _EXTENSION_LANGUAGES.get(path.suffix.lower())
    if language is None:
        suffix = path.suffix or "<none>"
        raise CliError(
            f"cannot infer surface language from extension `{suffix}`; "
            "provide --language"
        )
    return language


def _render_text(language: str, path: Path, model: object) -> str:
    payload = asdict(model)
    rows = [f"file: {path}", f"language: {language}"]
    for field in ("comments", "directives", "headings", "fences", "diagnostics"):
        if field in payload:
            rows.append(f"{field}: {len(payload[field])}")
    return "\n".join(rows)


def _cmd_normalize(args: argparse.Namespace) -> int:
    path = Path(args.file)
    if not path.is_file():
        raise CliError(f"surface file not found: {path}")
    language = _resolve_language(path, args.language)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise CliError(f"cannot read surface file {path}: {exc}") from exc
    model = _NORMALIZERS[language](text)
    if args.json:
        print(
            json.dumps(
                {
                    "schema": "agentos.surface-normal-model.v1",
                    "file": str(path),
                    "language": language,
                    "model": asdict(model),
                },
                indent=2,
                ensure_ascii=False,
            )
        )
    else:
        print(_render_text(language, path, model))
    return 0


def register_surface_commands(subparsers: argparse._SubParsersAction) -> None:
    parser = subparsers.add_parser(
        "surfaces",
        help="Inspect native source normal models.",
    )
    commands = parser.add_subparsers(dest="surfaces_command", required=True)
    normalize = commands.add_parser(
        "normalize",
        help="Normalize one source file into its native model.",
    )
    normalize.add_argument("--file", required=True, help="Source file to normalize.")
    normalize.add_argument(
        "--language",
        choices=tuple(sorted(_NORMALIZERS)),
        help="Host language; inferred from --file when omitted.",
    )
    normalize.add_argument(
        "--json",
        action="store_true",
        help="Print the complete normal model as JSON.",
    )
    normalize.set_defaults(handler=_cmd_normalize)


__all__ = ["register_surface_commands"]
