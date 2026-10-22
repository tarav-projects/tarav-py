"""Thin CLI for inspectable proposals and explicit maintainer confirmation."""

import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.git.repository import GitError

from .mapper import ProductMapper
from .model import MappingProposal


def summary(mapping):
    data = mapping.typed
    return {"id": data.id, "commit": data.commit, "base": data.base,
            "confirmed_at": data.confirmed_at, "actor": data.actor,
            "chunks": len(data.chunks), "files": len({c.path for c in data.chunks}),
            "skipped": len(data.skipped)}


def _run(args):
    try:
        mapper = args.mapping_mapper(args.repo, args.repository_id, root=args.store)
        command = args.mapping_command
        if command == "init":
            mapper.create(target_bytes=args.target_bytes, boundary_bytes=args.boundary_bytes,
                          include=args.include, exclude=args.exclude)
            value = {"root": str(mapper.store.root), "track": mapper.track().records.to_record()}
        elif command == "propose":
            value = mapper.propose(args.commit).records.to_record()
        elif command in {"changes", "confirm"}:
            proposal = MappingProposal.records.from_record(json.loads(args.proposal.read_text()))
            if command == "changes":
                value = mapper.changes(proposal)
            else:
                result = mapper.confirm(proposal, decisions=json.loads(args.decisions.read_text()),
                                        actor=args.actor, reason=args.reason)
                value = summary(result)
        elif command == "show":
            selected = mapper.load(args.map) if args.map else mapper.latest()
            value = (selected.records.to_record() if args.json else summary(selected)) if selected else None
        elif command == "history":
            value = [summary(mapper.load(identity)) for identity in mapper.history()]
        elif command == "chunk":
            value = (mapper.chunk_history(args.id) if args.history else
                     mapper.locate(args.id, at=args.map).model_dump())
        elif command == "audit":
            selected = mapper.history() if args.all else (
                (args.map,) if args.map else mapper.history()[-1:])
            value = [mapper.audit(mapper.load(identity)) for identity in selected]
        else:
            value = mapper.product.checkpoints(args.commit, every=args.every, after=args.after)
        if args.output:
            atomic_write_json(args.output, value, ensure_ascii=False)
            print(json.dumps({"output": str(args.output.resolve())}))
        else:
            print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, GitError) as exc:
        raise CliError(str(exc)) from exc


# tarav.breadcrumb ff230ac71547
def register_product_mapping_commands(subparsers, *, mapper_factory=ProductMapper):
    parser = subparsers.add_parser("product-map", help="Maintain byte-chunk maps at selected Git commits.")
    commands = parser.add_subparsers(dest="mapping_command", required=True)
    for name, description in (
        ("init", "Create an explicit mapping stream; never modify the product."),
        ("propose", "Propose an editable map for a committed target."),
        ("changes", "Inspect changed/new/retired candidate chunks."),
        ("confirm", "Confirm a proposal with attributed continuity decisions."),
        ("show", "Show the latest or selected confirmed map."),
        ("history", "List confirmed map checkpoints."),
        ("chunk", "Locate a chunk or expand its recorded lineage."),
        ("audit", "Verify exact byte coverage of confirmed maps."),
        ("checkpoints", "Select every Nth first-parent commit and the final target."),
    ):
        cmd = commands.add_parser(name, help=description)
        cmd.add_argument("--repo", type=Path, required=True)
        cmd.add_argument("--repository-id", required=True, help="Explicit repository identity, e.g. its DOI.")
        cmd.add_argument("--store", type=Path, help="Override the workflow Record Registry partition.")
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--output", type=Path)
        if name == "init":
            cmd.add_argument("--target-bytes", type=int, default=4096)
            cmd.add_argument("--boundary-bytes", type=int, default=256)
            cmd.add_argument("--include", action="append")
            cmd.add_argument("--exclude", action="append")
        if name in {"propose", "checkpoints"}:
            cmd.add_argument("--commit", default="HEAD")
        if name == "checkpoints":
            cmd.add_argument("--every", type=int, default=10)
            cmd.add_argument("--after")
        if name in {"changes", "confirm"}:
            cmd.add_argument("--proposal", type=Path, required=True)
        if name == "confirm":
            cmd.add_argument("--decisions", type=Path, required=True)
            cmd.add_argument("--actor", required=True)
            cmd.add_argument("--reason", required=True)
        if name in {"show", "audit", "chunk"}:
            cmd.add_argument("--map")
        if name == "chunk":
            cmd.add_argument("--id", required=True)
            cmd.add_argument("--history", action="store_true")
        if name == "audit":
            cmd.add_argument("--all", action="store_true")
        cmd.set_defaults(handler=_run, mapping_mapper=mapper_factory)
