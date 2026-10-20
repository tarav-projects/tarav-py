"""Import the selected current Diagram snapshot, retaining original JSON.

Run through Tarav:
    tarav run -- scripts/import_legacy_notebook.py --project PATH --source PATH

This imports explicit ship files, not Git history or unfinished Drafts.
"""

import argparse
from collections import Counter
from hashlib import sha256
import json
from pathlib import Path
import shutil
from uuid import uuid5

from tarav.l0._core.persistence import atomic_write_json
from tarav.l0.kernel import Ship
from tarav.l1.git.repository import GitRepository
from tarav.l1.lines import Block, Line
from tarav.l2.project import Project


def _type(record):
    value = record["type"]
    return value["label"] if isinstance(value, dict) else value


def _latest(record):
    return max(record["editions"], key=lambda edition: (
        edition["recorded_at"], edition["id"],
    ))


def _order(item):
    identity, record = item
    return record.get("recorded_at", _latest(record)["recorded_at"]), identity


def _label(block, value):
    if value is not None:
        block.append(Line(
            id=Ship(uuid5(block.id.uuid, "recovered-label")), text=value, scope=block,
        ))


# tarav.breadcrumb 8698b1a2f9cf
# tarav.breadcrumb eccc8d8dac34
def import_diagram(book, sources):
    """Import each latest explicit edition once; collisions require a decision."""
    notebook = book.storage
    archive = book.archive
    snapshots = []
    source_ids = set()
    recovered = set()
    for selected in sources:
        root = Path(selected).expanduser().resolve()
        namespace = json.loads((root / "namespace.json").read_text(encoding="utf-8"))
        namespace_id = Ship(namespace["id"])
        if namespace_id in source_ids:
            raise ValueError("A source namespace was selected twice")
        source_ids.add(namespace_id)
        rows = {
            path.stem: json.loads(path.read_text(encoding="utf-8"))
            for path in sorted((root / "ships").glob("*.json"))
        }
        models = {key: value for key, value in rows.items()
                  if _type(value) == "Diagram.Model.Ship"}
        blocks = {key: value for key, value in rows.items()
                  if _type(value) == "Diagram.Block.Ship"}
        lines = {key: value for key, value in rows.items()
                 if _type(value) == "Diagram.Line.Ship"}
        if not models:
            raise ValueError(f"Source has no Model snapshot: {root}")
        for identity, record in {**models, **blocks, **lines}.items():
            Ship(identity)
            _latest(record)
            if identity in recovered:
                raise ValueError(f"Conflicting source Ship: {identity}")
            recovered.add(identity)
        for identity, record in blocks.items():
            if record["model_ship"] not in models:
                raise ValueError(f"Block {identity} refers to a missing Model")
        for identity, record in lines.items():
            parent = blocks.get(record["block_ship"])
            if parent is None:
                raise ValueError(f"Line {identity} refers to a missing Block")
            if record["model_ship"] != parent["model_ship"]:
                raise ValueError(f"Line {identity} disagrees with its Block's Model")
        snapshots.append((root, namespace, models, blocks, lines))

    if not snapshots:
        raise ValueError("Select at least one Diagram source")
    import_id = str(uuid5(
        archive.id.uuid, "Diagram snapshot:" + ":".join(sorted(map(str, source_ids))),
    ))
    destination = notebook.root / "imports" / import_id
    if destination.exists():
        raise FileExistsError(f"Snapshot was already captured: {destination}")

    groups = []
    report = {"project_ship": str(book.project_ship), "archive_ship": str(archive.id),
              "import_id": import_id, "sources": [], "selections": [], "counts": {}}
    totals = Counter()
    for root, namespace, models, blocks, lines in snapshots:
        group = Block(id=Ship(uuid5(Ship(namespace["id"]).uuid, "Notebook snapshot")),
                      parent=archive)
        _label(group, f"Recovered historical snapshot: {namespace['name']}.")
        groups.append(group)
        model_objects = {}
        block_objects = {}
        for identity, record in sorted(models.items(), key=_order):
            block = Block(id=Ship(identity), parent=group)
            _label(block, _latest(record).get("data", {}).get("label"))
            group.append(block)
            model_objects[identity] = block
        for identity, record in sorted(blocks.items(), key=_order):
            parent = model_objects[record["model_ship"]]
            block = Block(id=Ship(identity), parent=parent)
            _label(block, _latest(record).get("data", {}).get("label"))
            parent.append(block)
            block_objects[identity] = block
        for identity, record in sorted(lines.items(), key=_order):
            parent = block_objects[record["block_ship"]]
            parent.append(Line(id=Ship(identity),
                               text=_latest(record)["data"]["text"], scope=parent))
        retained = f"imports/{import_id}/sources/{namespace['id']}"
        source = {"namespace": namespace, "source": str(root), "retained": retained,
                  "counts": {"models": len(models), "blocks": len(blocks),
                             "lines": len(lines)}}
        if (root / ".git").exists():
            source["git_state"] = GitRepository(root).state()
        report["sources"].append(source)
        totals.update(source["counts"])
        for identity, record in {**models, **blocks, **lines}.items():
            report["selections"].append({
                "ship": identity, "source_type": _type(record),
                "edition": _latest(record)["id"],
                "source_record": f"{retained}/ships/{identity}.json",
                "source_sha256": sha256((root / "ships" / f"{identity}.json").read_bytes()).hexdigest(),
            })
        totals["retained_other_ships"] += len(
            list((root / "ships").glob("*.json"))
        ) - len(models) - len(blocks) - len(lines)

    def flatten(block):
        yield block
        for member in block.contents:
            if isinstance(member, Block):
                yield from flatten(member)
            else:
                yield member

    incoming = [obj for group in groups for obj in flatten(group)]
    ids = [obj.id for obj in incoming]
    if len(set(ids)) != len(ids):
        raise ValueError("Recovered or derived Ships conflict within the import")
    existing = set(notebook.ids())
    if existing.intersection(ids):
        raise FileExistsError("Recovered Ship already exists; existing Records were not overwritten")

    # Retain richer legacy support, edition, and annotation data before conversion.
    for (root, *_), source in zip(snapshots, report["sources"], strict=True):
        target = notebook.root / source["retained"]
        target.mkdir(parents=True)
        shutil.copy2(root / "namespace.json", target / "namespace.json")
        shutil.copytree(root / "ships", target / "ships")
        if (root / "annotations").is_dir():
            shutil.copytree(root / "annotations", target / "annotations")
    for group in groups:
        notebook.save_tree(group)
        archive.append(group)
    notebook.save(archive)
    report["counts"] = dict(totals)
    report["counts"]["new_records"] = len(incoming)
    atomic_write_json(destination / "report.json", report)
    return report


def main():
    from tarav.l3.runtime import get_runtime

    get_runtime()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--project", type=Path, required=True)
    parser.add_argument("--source", type=Path, action="append", required=True)
    args = parser.parse_args()
    book = Project.from_path(args.project).notebook().create()
    print(json.dumps(import_diagram(book, args.source), indent=2))


if __name__ == "__main__":
    main()
