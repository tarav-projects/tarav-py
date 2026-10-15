"""A local browser and HTTP adapter over the same Python Context explorer."""

from __future__ import annotations

import argparse
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict
from rdflib import Literal as RDFLiteral

from tarav.l0.kernel import TaravClass, TaravObject, entity
from tarav.l1._future.context import ContextViewEntry
from tarav.l1.records.registry import default_records_root
from tarav.l2._future.demo import CHAT_ID, Demo


PAGE = Path(__file__).with_name("index.html")


class Request(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")
    op: Literal["open", "view", "expand", "follow", "inspect", "back", "forward", "query"]
    id: str | None = None
    name: str | None = None
    sparql: str | None = None


def required(value, name):
    if value is None:
        raise ValueError(f"{name} is required")
    return value


# tarav.context 473c89a0:8944495a171e5499
class Application:
    """One shared explorer session, independently usable without HTTP."""

    def __init__(self, demo: Demo, root=CHAT_ID):
        self.demo = demo
        self.explorer = demo.open(root).select("out")
        self.inspected = self.explorer.subject
        self.query_text = None

    def node(self, obj):
        diagram = self.demo.diagram
        cls = entity(type(obj))
        source = self.demo.source(obj)
        return {
            "id": diagram.ref(obj).n3(), "label": diagram.label(obj),
            "type": cls.name, "type_id": diagram.ref(cls).n3(),
            "record": obj.records.to_record(),
            "source": str(source) if source else None,
            "code": (obj.target if isinstance(obj, TaravClass) and obj._target is not None
                     else type(obj)).help(),
        }

    def state(self):
        explorer, diagram = self.explorer, self.demo.diagram
        entries = [entry for entry in explorer.ls() if not isinstance(entry, ContextViewEntry)]
        nodes = {}
        edges = []
        focus = self.node(explorer.subject)
        nodes[focus["id"]] = focus
        for entry in entries:
            relation = entry.relation
            source, target = self.node(relation.subject), self.node(relation.target)
            nodes[source["id"]], nodes[target["id"]] = source, target
            edges.append({
                "id": diagram.ref(relation).n3(), "source": source["id"],
                "target": target["id"], "predicate": diagram.ref(entry.predicate).n3(),
                "label": diagram.label(entry.predicate),
            })
        root = type(explorer.view)(diagram, type(explorer.view.location)(explorer.subject))
        available = list(dict.fromkeys((*root.available_views(), *explorer.view.available_views())))
        query_text = self.query_text if self.query_text is not None else explorer.view.sparql
        query_result = None
        if query_text:
            result = explorer.query(query_text, bindings=dict(explorer.view.location.bindings))
            if result.type == "ASK":
                query_result = {"kind": "ASK", "answer": result.askAnswer}
            elif result.type == "SELECT":
                rows = [{str(key): value.n3() if value is not None else None
                         for key, value in row.asdict().items()} for row in result]
                query_result = {"kind": "SELECT", "columns": [str(var) for var in result.vars],
                                "rows": rows[:200], "total": len(rows)}
            else:
                triples = sorted(tuple(value.n3() for value in triple) for triple in result.graph)
                query_result = {"kind": result.type, "triples": triples[:200], "total": len(triples)}
        qualifications = []
        for value in explorer.view.qualifications:
            if isinstance(value, str):
                qualifications.append(value)
            else:
                qualifications.append(next(
                    (name for name, request in diagram.views.items() if request is value),
                    entity(type(value)).name,
                ))
        bindings = {
            name: diagram.ref(value).n3() if isinstance(value, TaravObject) else (
                RDFLiteral(value).n3() if type(value) in (str, int, float, bool) else value.n3()
            ) for name, value in explorer.view.bindings.items()
        }
        return {
            "focus": focus, "nodes": list(nodes.values()), "edges": edges,
            "inspected": self.node(self.inspected), "views": available,
            "qualifications": qualifications, "bindings": bindings,
            "expansions": [{"key": value.key, "label": value.label} for value in explorer.expansions()],
            "sparql": query_text, "query_result": query_result,
            "triples": diagram.triple_count, "revision": diagram.revision,
            "history": {"back": explorer._position > 0,
                        "forward": explorer._position + 1 < len(explorer._history)},
            "coverage": "Results cover the graph loaded in this explorer session.",
        }

    def dispatch(self, value):
        request = Request.model_validate(value)
        explorer = self.explorer
        if request.op in {"open", "follow"}:
            obj = self.demo.resolve(required(request.id, "id"))
            explorer.follow(obj)
            if request.op == "open":
                explorer.select("out")
            self.inspected = obj
            self.query_text = None
        elif request.op == "view":
            explorer.select(required(request.name, "name"))
            self.query_text = None
        elif request.op == "expand":
            explorer.expand(required(request.name, "name"))
        elif request.op == "inspect":
            self.inspected = self.demo.diagram.resolve(required(request.id, "id"))
        elif request.op == "back":
            explorer.back()
            self.inspected, self.query_text = explorer.subject, None
        elif request.op == "forward":
            explorer.forward()
            self.inspected, self.query_text = explorer.subject, None
        elif request.op == "query":
            text = required(request.sparql, "sparql")
            # Validate and consume first, so a bad query does not poison later state requests.
            list(explorer.query(text, bindings=dict(explorer.view.location.bindings)))
            self.query_text = text
        return self.state()


def handler_for(application):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format, *args):
            pass

        def send(self, status, body, content_type="application/json; charset=utf-8"):
            if not isinstance(body, bytes):
                body = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path in {"/", "/index.html"}:
                self.send(200, PAGE.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api":
                self.send(200, application.state())
            else:
                self.send(404, {"error": "Unknown resource"})

        def do_POST(self):
            if self.path != "/api":
                self.send(404, {"error": "Unknown resource"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= 1_000_000:
                    raise ValueError("Request body must contain at most 1 MB of JSON")
                value = json.loads(self.rfile.read(length))
                self.send(200, application.dispatch(value))
            except FileNotFoundError as exc:
                self.send(404, {"error": str(exc)})
            except (ValueError, TypeError, KeyError) as exc:
                self.send(400, {"error": str(exc)})

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Explore the opt-in RDF Diagram in a local browser.")
    parser.add_argument("--records-root", type=Path, default=None)
    parser.add_argument("--seed-demo", action="store_true", help="Create missing synthetic demo Records.")
    parser.add_argument("--root", default=str(CHAT_ID), help="Initial object ID.")
    parser.add_argument("--port", type=int, default=8737)
    args = parser.parse_args(argv)
    demo = Demo(args.records_root if args.records_root is not None else default_records_root())
    if args.seed_demo:
        demo.seed()
    application = Application(demo, args.root)
    server = HTTPServer(("127.0.0.1", args.port), handler_for(application))
    print(f"Diagram explorer: http://127.0.0.1:{server.server_port}", flush=True)
    print(f"Root ID: {args.root}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
