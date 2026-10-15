"""Stored and live synthetic conversations using ordinary Record Registry IO."""

from pathlib import Path

from tarav.l0.kernel import Ship, TaravObject, TypeRegistry, entity
from tarav.l1._future import _FutureWorkflow, future
from tarav.l1._future.context import Along, Where
from tarav.l1._future.conversations import (
    ABOUT, AUTHOR, HAS_TURN, IN_CHAT, NOTE_TEXT, RECORD_TYPES, TEXT, TITLE,
    Annotation, Conversation, UserTurn,
)
from tarav.l1._future.graph import Diagram
from tarav.l1.records.registry import RecordRegistry


CHAT_ID = Ship("776cd033-b741-4bc2-8207-193ca827d9f2")
ALICE_ID = Ship("cbd9004e-b66d-4a56-a8fb-6c97285e2b3d")
BOB_ID = Ship("6994609d-df68-4f5b-9f97-cb05de58782f")
LIVE_ID = Ship("7133b0ec-a395-4d5d-b1c4-233c12dc8eaa")
NOTE_ID = Ship("e5271642-6268-4137-8c3d-44436a1f1acd")


# tarav.context 473c89a0:8944495a171e5499
class Demo:
    """One local host. Root selects the normal Registry location explicitly."""

    def __init__(self, root: Path):
        self.records = TypeRegistry(TaravObject, RECORD_TYPES)
        self.store = RecordRegistry(root, self.records).for_workflow(_FutureWorkflow)
        self.diagram = Diagram()
        self._objects = {}
        self._sources = {}
        self._live_loaded = False
        self.diagram.register(Conversation, self._conversation)
        self.diagram.register(UserTurn, self._turn)
        self.diagram.register(Annotation, self._annotation)
        self.diagram.register_view("messages", Along(HAS_TURN))
        self.diagram.register_view("by-alice", Where(AUTHOR, "alice"))
        self.diagram.register_view("by-bob", Where(AUTHOR, "bob"))

    def seed(self):
        """Explicitly create only missing synthetic Records; never rewrite one."""
        self.store.create()
        examples = (
            Conversation(CHAT_ID, "Synthetic conversation", (ALICE_ID, BOB_ID)),
            UserTurn(ALICE_ID, CHAT_ID, "alice", "How can we explore this graph?"),
            UserTurn(BOB_ID, CHAT_ID, "bob", "Start with a named view or write SPARQL."),
            Annotation(NOTE_ID, ALICE_ID, "Synthetic external annotation for the demo."),
        )
        names = set(self.store.names())
        for obj in examples:
            if str(obj.id) not in names:
                self.store.insert(str(obj.id), obj)
        return self

    def resolve(self, identifier):
        try:
            return self.diagram.resolve(identifier)
        except KeyError:
            pass
        if isinstance(identifier, str) and identifier.startswith("urn:uuid:"):
            identifier = identifier.removeprefix("urn:uuid:")
        identity = Ship(str(identifier))
        if identity not in self._objects:
            obj = self.store.load(str(identity))
            if not hasattr(obj, "id") or obj.id != identity:
                raise ValueError("Record key and object identity disagree")
            self._objects[identity] = obj
            self._sources[identity] = self.store.path(str(identity))
        return self._objects[identity]

    def open(self, identifier=CHAT_ID):
        return future(self.resolve(str(identifier))).context(diagram=self.diagram)

    def source(self, obj):
        return self._sources.get(getattr(obj, "id", None))

    def _conversation(self, obj, diagram):
        diagram.relate(obj, TITLE, obj.title)
        diagram.expand(entity(type(obj)))
        for identity in obj.turns:
            turn = self.resolve(str(identity))
            diagram.relate(obj, HAS_TURN, turn)
            diagram.expand(turn)
        if not self._live_loaded:
            diagram.offer(obj, "runtime-turn", "Load runtime-only turn", self._load_live)
        if str(NOTE_ID) in self.store.names() and NOTE_ID not in self._objects:
            diagram.offer(obj, "annotation", "Load external annotation", self._load_note)

    def _turn(self, obj, diagram):
        diagram.relate(obj, IN_CHAT, self.resolve(str(obj.conversation)))
        diagram.relate(obj, AUTHOR, obj.author)
        diagram.relate(obj, TEXT, obj.text)

    def _annotation(self, obj, diagram):
        diagram.relate(obj, ABOUT, self.resolve(str(obj.about)))
        diagram.relate(obj, NOTE_TEXT, obj.text)

    def _load_live(self, diagram):
        turn = UserTurn(LIVE_ID, CHAT_ID, "alice", "This turn exists only in this process.")
        self._objects[LIVE_ID] = turn
        diagram.relate(self.resolve(str(CHAT_ID)), HAS_TURN, turn)
        diagram.expand(turn)
        self._live_loaded = True

    def _load_note(self, diagram):
        diagram.expand(self.resolve(str(NOTE_ID)))
