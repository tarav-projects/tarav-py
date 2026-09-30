"""One-time, explicit migration of maintained SKW package source Records.

Dry-run by default. This script never imports package-selected code or rewrites
generation annotations; the retained mapping supports their historical hashes.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from uuid import UUID, uuid5

from tarav.l1.skw.generation import _hash


# tarav.breadcrumb b7de631151abf5d81088f8615fc88443663402ea0c3a75a0bc29ead062094dcb
NAMESPACE = UUID("77469b44-708f-4bac-bf4d-2b2792558072")
READING_TYPES = {
    "links": "Tarav.SKW.Reading.ExpectedLink",
    "includes": "Tarav.SKW.Reading.IncludesBlock",
    "inlined": "Tarav.SKW.Reading.InlineDependency",
    "referenced": "Tarav.SKW.Reading.ReferenceDependency",
    "either": "Tarav.SKW.Reading.EitherDependency",
}


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def save(path: Path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def migrate(root: Path, *, write: bool):
    main = load(root / ".skw/main.json")
    lock = load(root / ".skw/lock.json")
    loading_path = root / main["loading"] if "loading" in main else None
    loading = load(loading_path) if loading_path else None
    documents = {}
    labels = {}
    migration = {"type": "Tarav.Skillware.BlockIdentityMigration", "schema_version": 1,
                 "documents": {}}
    for relative in main["sources"]:
        path = root / relative
        source = load(path)
        baseline = lock["documents"][relative]
        if baseline["source_hash"] != _hash(source):
            raise ValueError(f"Source was stale before migration: {path}")
        if (root / source["output"]).is_file():
            product = (root / source["output"]).read_text(encoding="utf-8")
            if baseline["product_hash"] != _hash(product):
                raise ValueError(f"Product was stale before migration: {root / source['output']}")
        if loading is not None and baseline["loading_hash"] != _hash(loading):
            raise ValueError(f"Loading declaration was stale before migration: {path}")
        seen = set()
        migration["documents"][relative] = {}
        for index, block in enumerate(source["blocks"]):
            label = block["id"]
            caption = block.get("label") if block["type"] == "Tarav.Skillware.SkillLink" else None
            if label in seen:
                raise ValueError(f"Duplicate local block label: {path} {label}")
            seen.add(label)
            ship = str(uuid5(NAMESPACE, f"{root.name}/{relative}/{label}"))
            block["id"] = ship
            block["label"] = label
            if block["type"] == "Tarav.Skillware.SkillLink":
                block["caption"] = caption
            migration["documents"][relative][label] = {"label": label, "ship": ship}
            labels[(relative, index)] = block
        documents[relative] = source
    if loading is not None:
        by_node = {}
        for node in loading["blocks"]:
            locator = node["reference"]["locator"]
            relative = (Path(".skw") / locator["path"]).as_posix()
            index = int(locator["pointer"].split("/")[-1])
            block = labels[(relative, index)]
            by_node[node["id"]] = block
        for node in loading["blocks"]:
            block = by_node[node["id"]]
            reading = block.setdefault("reading", [])
            for kind in ("includes", "links"):
                for edge in node.pop(kind, []):
                    target = by_node[edge["target"]]
                    declaration = {"type": READING_TYPES[kind], "target": target["id"],
                                   "entry": {"type": "Tarav.SKW.Reading.BlockEntry",
                                             "node": edge["target"]}}
                    if "slot" in edge:
                        declaration["slot"] = edge["slot"]
                    if "label" in edge:
                        declaration["caption"] = edge["label"]
                    reading.append(declaration)
            for requirement in node.pop("requires", []):
                reading.append({"type": READING_TYPES[requirement["delivery"]],
                                "target": by_node[requirement["target"]]["id"]})
        for source in documents.values():
            for block in source["blocks"]:
                if not block.get("reading"):
                    block.pop("reading", None)
    print(f"{root}: {sum(len(v['blocks']) for v in documents.values())} blocks; "
          f"{len(loading['blocks']) if loading else 0} loading nodes; "
          f"write={write}")
    if not write:
        return
    for relative, source in documents.items():
        save(root / relative, source)
    if loading_path is not None:
        save(loading_path, loading)
    save(root / ".skw/block-identity-migration.json", migration)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("roots", nargs="+", type=Path)
    parser.add_argument("--write", action="store_true")
    args = parser.parse_args()
    for root in args.roots:
        migrate(root.resolve(), write=args.write)


if __name__ == "__main__":
    main()
