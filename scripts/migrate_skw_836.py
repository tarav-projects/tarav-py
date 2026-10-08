"""Migrate maintained SKW sources to the neutral annotated block schema."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

# tarav.breadcrumb 9ee2de194318b587fcdfbeb75d823a011a17076105c68522c51f07b27bf92c8b
import tarav_bypass  # noqa: F401


BLOCK = "Tarav.Skillware.Block"
GENERATION = "Tarav.Skillware.GenerationAnnotation"
LITERAL = "Tarav.Skillware.LiteralBlock"
AGENT_GENERATION = "Tarav.Skillware.AgentGenerationBlock"
SKILL_LINK = "Tarav.Skillware.SkillLink"


def migrate_block(block: dict[str, object]) -> dict[str, object]:
    result = dict(block)
    if "content" in result and "output" not in result:
        return result
    block_type = result.get("type")
    if block_type in {LITERAL, AGENT_GENERATION}:
        result["type"] = BLOCK
    elif block_type not in {BLOCK, SKILL_LINK}:
        raise ValueError(f"Unsupported SKW block Type: {block_type}")

    result["content"] = result.pop("output")
    annotations = list(result.pop("annotations", []))

    if block_type == AGENT_GENERATION:
        context = []
        for entry in result.pop("context", []):
            if (not isinstance(entry, dict) or entry.get("kind") != "reference"
                    or set(entry) != {"kind", "reference", "roles"}):
                raise ValueError("836 migrates only typed Reference context entries")
            context.append(entry["reference"])
        annotations.insert(0, {
            "type": GENERATION,
            "instructions": result.pop("prompt"),
            "context": context,
        })
        if "arguments" in result:
            raise ValueError("836 does not migrate prompt-template arguments")

    for field in ("contains", "reading_deps", "links"):
        annotations.extend(result.pop(field, []))
    if annotations:
        result["annotations"] = annotations
    return result


def migrate(path: Path) -> bool:
    data = json.loads(path.read_text(encoding="utf-8"))
    migrated = [migrate_block(block) for block in data.get("blocks", [])]
    if migrated == data.get("blocks", []):
        return False
    data["blocks"] = migrated
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    return True


def _git_json(repository: Path, revision: str, path: Path):
    relative = path.resolve().relative_to(repository.resolve()).as_posix()
    try:
        text = subprocess.check_output(
            ["git", "show", f"{revision}:{relative}"],
            cwd=repository,
            text=True,
            stderr=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError:
        return None
    return json.loads(text)


def _old_generation_hash(block, *, document_key, migration):
    from tarav.l1.skw.generation import _hash

    recipe = {key: value for key, value in block.items() if key != "output"}
    old = migration.get("documents", {}).get(document_key, {}).get(block["label"])
    if old is not None:
        recipe["id"] = old["label"]
        recipe.pop("label", None)
        recipe.pop("reading", None)
        for field in ("contains", "reading_deps", "links"):
            recipe.pop(field, None)
    return _hash({"recipe": recipe, "values": {}, "dependencies": {}})


def _old_context_hash(entries, *, source):
    from tarav.l1.references.structured import StructuredFileReference
    from tarav.l1.skw.generation import _hash

    resolved = []
    for entry in entries:
        if entry.get("kind") != "reference":
            raise ValueError("Cannot translate a non-Reference context baseline")
        reference = StructuredFileReference.records.from_record(entry["reference"])
        reference.source = source
        result = reference.resolve()
        if not result.ok:
            raise ValueError(result.message)
        content = result.target
        if isinstance(content, bytes):
            fingerprint = hashlib.sha256(content).hexdigest()
            content = content.decode("utf-8")
        else:
            fingerprint = _hash(content)
        resolved.append({
            "declaration": entry,
            "content": content,
            "fingerprint": fingerprint,
        })
    return _hash(resolved)


def translate_baselines(project: Path, *, repository: Path, revision: str) -> tuple[int, int]:
    """Translate only baselines that still match their pre-migration inputs."""

    from tarav.l1.skw.document import Document, read, write
    from tarav.l3.runtime import create_runtime

    lock_path = project / ".skw" / "lock.json"
    old_lock = _git_json(repository, revision, lock_path)
    if old_lock is None or not lock_path.is_file():
        return 0, 0
    lock = read(lock_path)
    migration_path = project / ".skw" / "block-identity-migration.json"
    migration = read(migration_path) if migration_path.is_file() else {}
    registry = create_runtime().records
    generation_count = context_count = 0

    for key, old_entry in old_lock.get("documents", {}).items():
        source = project / key
        old_source = _git_json(repository, revision, source)
        current_entry = lock.get("documents", {}).get(key)
        if old_source is None or current_entry is None or not source.is_file():
            continue
        old_blocks = {block["label"]: block for block in old_source.get("blocks", [])}
        document = Document(source, root=project, registry=registry)

        for label, old_baseline in old_entry.get("contexts", {}).items():
            old_block = old_blocks.get(label)
            if old_block is None:
                continue
            try:
                current_old_hash = _old_context_hash(
                    old_block.get("context", []), source=source
                )
            except (OSError, UnicodeError, ValueError, TypeError, KeyError):
                continue
            if current_old_hash != old_baseline:
                continue
            current_entry.setdefault("contexts", {})[label] = document._context_hash(
                document._resolved_context(label)
            )
            context_count += 1

        for label, old_baseline in old_entry.get("blocks", {}).items():
            old_block = old_blocks.get(label)
            current_baseline = current_entry.get("blocks", {}).get(label)
            if old_block is None or current_baseline is None:
                continue
            if (_old_generation_hash(old_block, document_key=key, migration=migration)
                    != old_baseline.get("input_hash")):
                continue
            fingerprint = document.generation_fingerprint(label)
            current_baseline["input_hash"] = fingerprint
            generation_path = document.annotation_path(current_baseline["generation"])
            generation = read(generation_path)
            generation["input_hash"] = fingerprint
            write(generation_path, generation)
            generation_count += 1

    write(lock_path, lock)
    return generation_count, context_count


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--baseline-ref")
    parser.add_argument("--repository", type=Path)
    args = parser.parse_args()
    changed = []
    for root in args.roots:
        for path in sorted(root.expanduser().resolve().rglob("*.skw.json")):
            if migrate(path):
                changed.append(path)
    print(f"Migrated {len(changed)} SKW documents.")
    if args.baseline_ref:
        if args.repository is None:
            parser.error("--baseline-ref requires --repository")
        projects = sorted({
            next(parent for parent in path.parents if parent.name == ".skw").parent
            for path in changed
        })
        if not projects:
            for root in args.roots:
                projects.extend(path.parent.parent for path in root.rglob(".skw/main.json"))
        for project in dict.fromkeys(projects):
            generation, context = translate_baselines(
                project.resolve(),
                repository=args.repository.expanduser().resolve(),
                revision=args.baseline_ref,
            )
            print(f"Translated {project}: {generation} generation, {context} context baselines.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
