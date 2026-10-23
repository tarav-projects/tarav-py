"""A small HTTP contract fixture, not a Typesense server or relevance benchmark."""

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Event, Thread
from urllib.parse import parse_qs, urlsplit

import pytest


@pytest.fixture
def engine():
    state = {"schema": None, "documents": {}, "imports": [], "deletes": [],
             "searches": [], "reject": False, "key": "private-test-credential",
             "stall_search": False, "search_release": Event()}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, data, status=200, *, raw=False):
            self.send_response(status)
            self.end_headers()
            self.wfile.write((data if raw else json.dumps(data)).encode())

        def do_GET(self):
            path = urlsplit(self.path)
            if self.headers.get("X-TYPESENSE-API-KEY") != state["key"]:
                return self.send({"message": "wrong key"}, 401)
            if path.path == "/health":
                return self.send({"ok": True})
            if path.path.endswith("/documents/search"):
                params = parse_qs(path.query)
                state["searches"].append(params)
                if state["stall_search"]:
                    state["search_release"].wait(30)
                    return
                docs = list(state["documents"].values())
                return self.send({"found": len(docs), "search_time_ms": 2,
                                  "hits": [{"document": d} for d in docs]})
            if state["schema"] is None:
                return self.send({"message": "missing"}, 404)
            return self.send({**state["schema"], "num_documents": len(state["documents"])})

        def do_POST(self):
            if self.headers.get("X-TYPESENSE-API-KEY") != state["key"]:
                return self.send({"message": "wrong key"}, 401)
            body = self.rfile.read(int(self.headers["Content-Length"])).decode()
            if self.path == "/collections":
                state["schema"] = json.loads(body)
                return self.send(state["schema"])
            assert parse_qs(urlsplit(self.path).query)["action"] == ["upsert"]
            docs = [json.loads(line) for line in body.splitlines()]
            state["imports"].append(docs)
            if not state["reject"]:
                for doc in docs:
                    state["documents"][doc["id"]] = doc
            return self.send("\n".join(json.dumps({"success": not state["reject"]})
                                       for _ in docs), raw=True)

        def do_DELETE(self):
            params = parse_qs(urlsplit(self.path).query)
            state["deletes"].append(params)
            identity, version = params["filter_by"][0].split(" && ")
            identity, version = identity.split(":=")[1], version.split(":!=")[1]
            deleted = [key for key, doc in state["documents"].items()
                       if doc["session_identity"] == identity and doc["source_version"] != version]
            for key in deleted:
                del state["documents"][key]
            return self.send({"num_deleted": len(deleted)})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    state["url"] = f"http://127.0.0.1:{server.server_port}"
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield state
    finally:
        state["search_release"].set()
        server.shutdown()
        server.server_close()
        thread.join()
