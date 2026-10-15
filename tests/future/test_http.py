"""Exercise actual HTTP parsing and serialization without requiring a TCP bind."""

import io
import importlib.util
import json
import shutil
import subprocess
from html.parser import HTMLParser

import pytest

HAS_RDF = importlib.util.find_spec("rdflib") is not None
pytestmark = pytest.mark.skipif(not HAS_RDF, reason="Install tarav[future] for RDF checks")
if HAS_RDF:
    from tarav.l1._future.conversations import HAS_TURN
    from tarav.l2._future.demo import ALICE_ID, CHAT_ID, LIVE_ID, Demo
    from tarav.l3._future.server import Application, PAGE, handler_for


class Connection:
    def __init__(self, data):
        self.input = io.BytesIO(data)
        self.output = bytearray()

    def makefile(self, mode, *args):
        return self.input

    def sendall(self, value):
        self.output.extend(value)


def request(app, method="GET", path="/api", value=None):
    body = json.dumps(value).encode() if value is not None else b""
    connection = Connection(
        f"{method} {path} HTTP/1.0\r\nContent-Length: {len(body)}\r\n\r\n".encode() + body,
    )
    handler_for(app)(connection, ("127.0.0.1", 1234), None)
    head, payload = bytes(connection.output).split(b"\r\n\r\n", 1)
    return int(head.split()[1]), payload


# tarav.context 473c89a0:8944495a171e5499
def test_http_open_query_expand_and_inspect_share_one_graph(tmp_path):
    app = Application(Demo(tmp_path).seed())
    status, body = request(app)
    assert status == 200
    assert json.loads(body)["focus"]["record"]["id"] == str(CHAT_ID)
    query = f"SELECT ?message WHERE {{ ?focus <urn:uuid:{HAS_TURN.id}> ?message }}"
    status, body = request(app, "POST", value={"op": "query", "sparql": query})
    assert status == 200
    assert json.loads(body)["query_result"]["total"] == 2
    status, body = request(app, "POST", value={"op": "expand", "name": "runtime-turn"})
    state = json.loads(body)
    assert status == 200
    assert state["query_result"]["total"] == 3
    assert any(str(LIVE_ID) in row["message"] for row in state["query_result"]["rows"])
    status, body = request(app, "POST", value={"op": "inspect", "id": str(ALICE_ID)})
    assert status == 200
    assert json.loads(body)["inspected"]["record"]["text"] == "How can we explore this graph?"
    assert app.explorer.subject.id == CHAT_ID


def test_http_predicate_and_relation_inspection_and_history(tmp_path):
    app = Application(Demo(tmp_path).seed())
    state = app.dispatch({"op": "view", "name": "messages"})
    edge = state["edges"][0]
    status, body = request(app, "POST", value={"op": "inspect", "id": edge["predicate"]})
    assert status == 200
    assert json.loads(body)["inspected"]["record"]["path"] == "turns"
    status, body = request(app, "POST", value={"op": "inspect", "id": edge["id"]})
    assert status == 200
    assert json.loads(body)["inspected"]["type"] == "Tarav.Future.Relation"
    status, body = request(app, "POST", value={"op": "follow", "id": edge["target"]})
    assert status == 200
    assert json.loads(body)["focus"]["type"] == "Tarav.Future.UserTurn"
    status, body = request(app, "POST", value={"op": "back"})
    assert status == 200
    assert json.loads(body)["focus"]["record"]["id"] == str(CHAT_ID)


def test_query_and_view_parameters_remain_inspectable(tmp_path):
    app = Application(Demo(tmp_path).seed())
    app.dispatch({"op": "view", "name": "messages"})
    state = app.dispatch({"op": "view", "name": "by-alice"})
    assert state["qualifications"] == ["messages", "by-alice"]
    assert state["bindings"]["filter1"] == '"alice"'
    assert state["query_result"]["total"] == 1


def test_http_rejects_bad_input_and_serves_the_actual_ui(tmp_path):
    app = Application(Demo(tmp_path).seed())
    for value in ({"op": "unknown"}, {"op": "query", "sparql": "not SPARQL"},
                  {"op": "open", "id": "not-an-id"}):
        status, body = request(app, "POST", value=value)
        assert status == 400
        assert "error" in json.loads(body)
    status, body = request(app, path="/")
    assert status == 200
    assert body == PAGE.read_bytes()
    assert b"Root ID" in body and b"SPARQL" in body


def test_unknown_well_formed_root_id_returns_a_readable_http_error(tmp_path):
    app = Application(Demo(tmp_path).seed())
    status, body = request(app, "POST", value={
        "op": "open", "id": "16464918-1167-4b23-b1d6-ad721155ccf9",
    })
    assert status == 404
    assert "error" in json.loads(body)
    assert app.explorer.subject.id == CHAT_ID


@pytest.mark.skipif(shutil.which("node") is None, reason="Node is optional UI syntax-check tooling")
def test_actual_ui_javascript_parses(tmp_path):
    class Scripts(HTMLParser):
        active = False
        source = ""
        def handle_starttag(self, tag, attrs):
            self.active = tag == "script"
        def handle_endtag(self, tag):
            if tag == "script":
                self.active = False
        def handle_data(self, data):
            if self.active:
                self.source += data
    parser = Scripts()
    parser.feed(PAGE.read_text())
    target = tmp_path / "ui.mjs"
    target.write_text(parser.source)
    result = subprocess.run(["node", "--check", str(target)], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
