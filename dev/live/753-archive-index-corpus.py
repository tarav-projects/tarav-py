#!/usr/bin/env python3
# $kw: --from Durable.Evidence.Audit --note [DC] the archive is a frozen copy plus the commit that produced it, so the migration can always be re-read against exactly what it consumed --note [CT] the umbrella root is not a git repository, so its state store had no history to fall back on and the copy is the only protection it has
"""Freeze the complete Index corpus before the index-2208 migration touches anything.

Conservation is the first requirement of this migration, so nothing is read for content
here — this pass only proves what exists and copies it somewhere durable.

Two classes of material, with very different risk:

**Markdown surfaces** live in per-repo Git repositories and already have full history. They
are copied anyway, together with the exact commit SHA of each repo, because the migration
will eventually rewrite them: an auditor then compares the result against a frozen source
rather than against "whatever HEAD said at the time".

**State stores** are the real exposure. `.tarav/state/index-anchor-locators` sits at the
umbrella root, which is *not* a Git repository at all, and holds the anchor-to-message
resolution substrate the whole Support.Set layer depends on. A copy is the only protection
that material has ever had.

Everything is inventoried with a sha256 so a later restore can prove it is byte-identical.
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

PROJECT = Path(__file__).resolve().parents[3]
ARCHIVE = PROJECT / "index-archive-2208"

MD_REPOS = (
    "tarav-md",
    "tarav-chatlas-md",
    "tarav-canvas-md",
    "tarav-iterante-md",
    "tarav-projects-center-md",
)
STATE_REPOS = MD_REPOS + ("tarav-py", "tarav-canvas-js", "tarav-js", "tarav-pkg-testground")
CODE_ROOTS = ("tarav-py/src", "tarav-py/tests", "tarav-py/dev")

#: Stores the migration depends on that live outside the project tree entirely. The anchory
#: depot is the anchor-to-message resolution the whole Support.Set layer reads; a corpus
#: snapshot that omitted it would archive the citations and lose what they cite.
EXTERNAL_DEPOTS = (Path.home() / "Documents" / "chatlas" / "anchory",)

ANCHOR = re.compile(r"\^[a-z]\d{8}-\d+[a-z]*")
TYPED = re.compile(r"^\s*[-*] \[[A-Z]{2}\] ")
KW = re.compile(r"\$kw:")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git_head(repo: Path) -> dict[str, str | None]:
    """The commit a copied tree came from, or an explicit null for an unversioned root."""
    if not (repo / ".git").exists():
        return {"repo": repo.name, "head": None, "note": "not a git repository"}
    def run(*args: str) -> str:
        return subprocess.run(
            ["git", "-C", str(repo), *args], capture_output=True, text=True, check=False
        ).stdout.strip()
    return {
        "repo": repo.name,
        "head": run("rev-parse", "HEAD") or None,
        "branch": run("rev-parse", "--abbrev-ref", "HEAD") or None,
        "dirty": str(bool(run("status", "--porcelain"))),
    }


def bearing_markdown() -> list[Path]:
    """Every Markdown file carrying a typed Index line or an anchor."""
    out: list[Path] = []
    for repo in MD_REPOS:
        root = PROJECT / repo
        if not root.is_dir():
            continue
        for path in root.rglob("*.md"):
            if ".git" in path.parts or "node_modules" in path.parts:
                continue
            if ARCHIVE in path.parents:
                continue
            try:
                text = path.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if ANCHOR.search(text) or TYPED.search(text):
                out.append(path)
    return sorted(out)


def bearing_code() -> list[Path]:
    """Every source file carrying an `$kw` annotation — Index lines under Natural.Placement."""
    out: list[Path] = []
    for rel in CODE_ROOTS:
        root = PROJECT / rel
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if "__pycache__" in path.parts:
                continue
            try:
                text = path.read_text("utf-8")
            except (OSError, UnicodeDecodeError):
                continue
            if KW.search(text):
                out.append(path)
    return sorted(out)


def copy_into(paths: list[Path], destination: Path) -> list[dict]:
    entries: list[dict] = []
    for path in paths:
        relative = path.relative_to(PROJECT)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
        entries.append(
            {"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)}
        )
    return entries


def copy_state() -> list[dict]:
    """Every `.tarav` store, the unversioned umbrella root first."""
    entries: list[dict] = []
    sources = [(PROJECT / ".tarav", "_root")] + [
        (PROJECT / repo / ".tarav", repo) for repo in STATE_REPOS
    ]
    for source, label in sources:
        if not source.is_dir():
            continue
        target = ARCHIVE / "state" / label
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target)
        for path in sorted(target.rglob("*")):
            if path.is_file():
                entries.append(
                    {
                        "store": label,
                        "path": path.relative_to(target).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
    return entries


def copy_external() -> list[dict]:
    """Depots outside the project tree that the corpus cites into."""
    entries: list[dict] = []
    for source in EXTERNAL_DEPOTS:
        if not source.is_dir():
            continue
        target = ARCHIVE / "external" / source.name
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".git"))
        for path in sorted(target.rglob("*")):
            if path.is_file():
                entries.append(
                    {
                        "depot": source.name,
                        "source": str(source),
                        "path": path.relative_to(target).as_posix(),
                        "bytes": path.stat().st_size,
                        "sha256": sha256(path),
                    }
                )
    return entries


def main() -> int:
    ARCHIVE.mkdir(parents=True, exist_ok=True)
    markdown = bearing_markdown()
    code = bearing_code()

    manifest = {
        "archive": "index-archive-2208",
        "purpose": "frozen pre-migration snapshot of the complete Index corpus",
        "created": datetime.now(UTC).isoformat(),
        "provenance": [git_head(PROJECT)]
        + [git_head(PROJECT / repo) for repo in STATE_REPOS if (PROJECT / repo).is_dir()]
        + [git_head(depot.parent) for depot in EXTERNAL_DEPOTS if depot.is_dir()],
        "surfaces": copy_into(markdown, ARCHIVE / "surfaces"),
        "code": copy_into(code, ARCHIVE / "code"),
        "state": copy_state(),
        "external": copy_external(),
    }
    manifest["counts"] = {
        "surfaces": len(manifest["surfaces"]),
        "code": len(manifest["code"]),
        "state_files": len(manifest["state"]),
        "external_files": len(manifest["external"]),
        "bytes": sum(
            item["bytes"]
            for group in ("surfaces", "code", "state", "external")
            for item in manifest[group]
        ),
    }
    (ARCHIVE / "MANIFEST.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n", "utf-8"
    )
    counts = manifest["counts"]
    print(f"surfaces   {counts['surfaces']:>6}")
    print(f"code       {counts['code']:>6}")
    print(f"state      {counts['state_files']:>6}")
    print(f"external   {counts['external_files']:>6}")
    print(f"bytes      {counts['bytes']:>6}")
    unversioned = [p for p in manifest["provenance"] if p.get("head") is None]
    for item in unversioned:
        print(f"UNVERSIONED SOURCE: {item['repo']} ({item.get('note', '')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
