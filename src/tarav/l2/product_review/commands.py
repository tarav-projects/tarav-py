"""Thin CLI over explicit batch maintenance and user-backed review completion."""

import base64
import json
from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.persistence import atomic_write_json
from tarav.l1.chatlas.references import ChatlasTurnReference
from tarav.l1.product_mapping import ProductMapper
from tarav.l1.references import Reference

from .tracker import ReviewTracker


def _tracker(repository, repository_id, *, root=None, maps_root=None):
    return ReviewTracker(ProductMapper(repository, repository_id, root=maps_root), root=root)


def _run(args):
    try:
        tracker = args.review_tracker(args.repo, args.repository_id, root=args.store, maps_root=args.maps_store)
        command = args.review_command
        if command == "init":
            tracker.create()
            value = {"root": str(tracker.store.root)}
        elif command in {"inspect", "create", "revise"}:
            mapping = tracker.select_map(map_id=args.map, horizon_days=args.horizon_days)
            if command == "inspect":
                value = tracker.inspect(map_id=mapping.typed.id)
            else:
                values = dict(map_id=mapping.typed.id, chunk_ids=args.chunk,
                              actor=args.actor, reason=args.reason)
                if command == "create":
                    obj = tracker.create_batch(**values, title=args.title, purpose=args.purpose)
                    value = tracker.current(obj.typed.id).records.to_record()
                else:
                    value = tracker.revise(args.batch, **values, base=args.base,
                                           title=args.title, purpose=args.purpose).records.to_record()
        elif command == "list":
            value = [tracker.current(b.typed.id).records.to_record()
                     for b in tracker.batches(retired=args.retired)]
        elif command == "show":
            value = (tracker.revision(args.revision) if args.revision else tracker.current(args.batch)).records.to_record()
        elif command == "history":
            value = tracker.history(args.batch)
        elif command == "read":
            value = [{"chunk": item["chunk"], "encoding": "base64",
                      "content": base64.b64encode(item["content"]).decode("ascii")}
                     for item in tracker.read(args.revision)]
        elif command == "present":
            value = tracker.presentation(args.revision)
            if not args.json and not args.output:
                print(value)
                return 0
        elif command == "complete":
            presentation = ChatlasTurnReference.records.from_record(json.loads(args.presentation.read_text()))
            completion = ChatlasTurnReference.records.from_record(json.loads(args.completion.read_text()))
            outcomes = [Reference.records.from_record(item) for item in json.loads(args.outcomes.read_text())] if args.outcomes else []
            value = tracker.complete(args.revision, presentation=presentation, completion=completion,
                                     outcomes=outcomes).records.to_record()
        else:
            value = tracker.retire(args.batch, actor=args.actor, reason=args.reason).records.to_record()
        if args.output:
            atomic_write_json(args.output, value, ensure_ascii=False)
            print(json.dumps({"output": str(args.output.resolve())}))
        else:
            print(json.dumps(value, indent=2, ensure_ascii=False))
        return 0
    except (OSError, ValueError, RuntimeError, LookupError) as exc:
        raise CliError(str(exc)) from exc


def register_product_review_commands(subparsers, *, tracker_factory=_tracker):
    parser = subparsers.add_parser("product-review", help="Maintain batches and record completed product reviews.")
    commands = parser.add_subparsers(dest="review_command", required=True)
    for name, description in (
        ("init", "Explicitly initialize review storage."),
        ("inspect", "Report selected-map completeness and per-batch review currency."),
        ("create", "Create a meaningful batch from selected chunk IDs."),
        ("revise", "Maintain batch membership at another map; retain its ID and history."),
        ("list", "List current batch revisions."),
        ("show", "Show an exact or current batch revision."),
        ("history", "Show a batch's revisions and completed reviews."),
        ("read", "Read pinned committed chunk bytes as base64."),
        ("present", "Present a whole-batch review-completion frame and token."),
        ("complete", "Record an actual User completion token with exact chat evidence."),
        ("retire", "Retire a batch while preserving its history."),
    ):
        cmd = commands.add_parser(name, help=description)
        cmd.add_argument("--repo", type=Path, required=True)
        cmd.add_argument("--repository-id", required=True)
        cmd.add_argument("--maps-store", type=Path)
        cmd.add_argument("--store", type=Path)
        cmd.add_argument("--json", action="store_true")
        cmd.add_argument("--output", type=Path)
        if name in {"inspect", "create", "revise"}:
            cmd.add_argument("--map")
            cmd.add_argument("--horizon-days", type=int)
        if name in {"create", "revise"}:
            cmd.add_argument("--chunk", action="append", required=True)
            cmd.add_argument("--title", required=name == "create")
            cmd.add_argument("--purpose", required=name == "create")
        if name in {"create", "revise", "retire"}:
            cmd.add_argument("--actor", required=True)
            cmd.add_argument("--reason", required=True)
        if name in {"revise", "history", "retire"}:
            cmd.add_argument("--batch", required=True)
        if name == "revise":
            cmd.add_argument("--base", required=True)
        if name == "show":
            group = cmd.add_mutually_exclusive_group(required=True)
            group.add_argument("--batch")
            group.add_argument("--revision")
        if name in {"read", "present", "complete"}:
            cmd.add_argument("--revision", required=True)
        if name == "complete":
            cmd.add_argument("--presentation", type=Path, required=True)
            cmd.add_argument("--completion", type=Path, required=True)
            cmd.add_argument("--outcomes", type=Path)
        if name == "list":
            cmd.add_argument("--retired", action="store_true")
        cmd.set_defaults(handler=_run, review_tracker=tracker_factory)
