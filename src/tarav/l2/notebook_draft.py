"""Bounded reviewed capture, staged outside the live Notebook."""
from copy import deepcopy
from uuid import uuid4

from tarav.l0.kernel import Ship, TaravClass, TaravType, TypeShip, entity
from tarav.l1.grounding import SupportMember
from tarav.l1.lines import Block, Line
from tarav.l1.notebook.evidence import NotebookLine, ReviewedLine
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l1.review import review_presentation
from tarav.l2.notebook_capture import line_state


def _context(block):
    return {"type": str(entity(type(block)).id),
            "parent": str(block.parent_ship) if block.parent_ship else None,
            "lines": [{"ship": str(line.id), "type": str(entity(type(line)).id), "text": line.text}
                      for line in block.contents if isinstance(line, Line)]}


# tarav.breadcrumb cc03df4a23bb
class NotebookDraft(TaravType):
    """An add/amend recipe, its original context, and an exact review presentation.

    Plans are temporary transport. This object owns no persistent partition and
    does not claim atomic writes or provide a general history/draft framework.
    """
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("a87e50f5-cc28-4865-90ac-032748f6b51c"),
                          name="Tarav.Notebook.Draft", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, notebook, block):
        self.notebook = notebook
        self.block = notebook.storage.load(block.id)
        self._initial_contexts = {str(obj.id): _context(obj)
                                  for obj in (*self.block.walk(), *self.block.ancestors())
                                  if isinstance(obj, Block)}
        self._initial_states = {str(obj.id): line_state(obj) for obj in self.block.walk()
                                if isinstance(obj, Line)}
        self._baseline, self._operations, self._edited = {}, [], []
        self._token, self._presentation = None, None

    def _find(self, identity):
        identity = Ship(str(getattr(identity, "id", identity)))
        return next((obj for obj in self.block.walk() if obj.id == identity), None)

    def _parent(self, block):
        target = self.block if block is None else self._find(block)
        if not isinstance(target, Block):
            raise ValueError("Draft target must be a Block inside its destination")
        for ancestor in (target, *target.ancestors()):
            key = str(ancestor.id)
            if key in self._initial_contexts:
                self._baseline[key] = self._initial_contexts[key]
        return target

    def _replay(self, operation):
        kind, record = operation["kind"], operation["record"]
        if kind not in ("add-block", "add-line", "amend-line"):
            raise ValueError("Unknown Notebook draft operation")
        obj = self.notebook.storage.store.records.from_record(record)
        if kind == "add-block":
            if not isinstance(obj, Block) or obj.content_ships:
                raise ValueError("Add Block requires an empty Block record")
            parent = self._parent(obj.parent_ship)
            obj.bind_parent(parent)
        else:
            if not isinstance(obj, NotebookLine):
                raise TypeError("Draft Lines must support Notebook evidence")
            parent = self._parent(obj.scope_ship)
            obj.bind_scope(parent)
        if kind == "amend-line":
            old = self._find(obj.id)
            if not isinstance(old, Line) or old.scope_ship != parent.id:
                raise ValueError("Amendment must retain an existing Line's Ship and scope")
            if type(obj) is not type(old):
                raise TypeError("Amendments must retain the stored Line Type")
            if isinstance(old, NotebookLine):
                obj.support_ships, obj.review_ships = list(old.support_ships), list(old.review_ships)
            parent.bind_contents(obj if member.id == obj.id else member for member in parent.contents)
        else:
            if self._find(obj.id) is not None or self.notebook.storage.store.path(str(obj.id)).exists():
                raise FileExistsError(f"New draft Ship already exists: {obj.id}")
            parent.append(obj)
        self._operations.append(deepcopy(operation))
        if isinstance(obj, Line) and str(obj.id) not in self._edited:
            self._edited.append(str(obj.id))
        return obj

    def add_block(self, *, parent=None, block_type=Block, id=None, **fields):
        parent = self._parent(parent)
        block = block_type(id=id or Ship(uuid4()), parent=parent, **fields)
        return self._replay({"kind": "add-block", "record": block.records.to_record()})

    def add(self, text, *, block=None, reviewed=True, id=None):
        parent = self._parent(block)
        line = (ReviewedLine if reviewed else NotebookLine)(id=id or Ship(uuid4()), text=text, scope=parent)
        return self._replay({"kind": "add-line", "record": line.records.to_record()})

    def amend(self, line, text):
        old = self._find(line)
        if not isinstance(old, Line):
            raise ValueError("Amendment target is outside this draft")
        if not isinstance(old, NotebookLine):
            raise TypeError("Plain Lines need a separate supported capture; this workflow does not migrate Types")
        record = old.records.to_record()
        record.update(text=text)
        return self._replay({"kind": "amend-line", "record": record})

    def _states(self):
        if not self._edited:
            raise ValueError("A capture proposal needs at least one Line")
        before = [self._initial_states[key] for key in self._edited if key in self._initial_states]
        after = [line_state(self._find(key)) for key in self._edited]
        return before, after

    def _render(self, token):
        before, after = self._states()
        lines = []
        for op in self._operations:
            record = op["record"]
            if op["kind"] == "add-block":
                lines.append(f"Append Block: {record['id']} ({record['type']}) to {record['parent_ship']}")
        for state in before:
            lines.append(f"Before Type: {state.typed.subject_ship} {state.typed.subject_type}")
        for key in self._edited:
            line = self._find(key)
            lines.append(f"After Type: {line.id} {entity(type(line)).name}")
        lines.append(review_presentation(self.block.id, "modify" if before else "add",
                                         before=[state.typed for state in before],
                                         after=[state.typed for state in after]))
        return "\n".join(lines) + f"\n\n::approve {token}"

    def propose(self, token):
        if not isinstance(token, str) or not token or any(char.isspace() for char in token):
            raise ValueError("Review token must be a nonempty opaque word")
        rendered = self._render(token)
        if token == self._token and self._presentation != rendered:
            raise ValueError("Changed proposal requires a new token")
        self._token, self._presentation = token, rendered
        return rendered

    def export(self):
        """JSON-safe temporary plan; preserve it before presenting the token."""
        before, _ = self._states()
        return deepcopy({"version": 1, "destination": str(self.block.id),
                         "operations": self._operations, "baseline": self._baseline,
                         "before": [state.records.to_record() for state in before],
                         "token": self._token, "presentation": self._presentation})

    @classmethod
    def restore(cls, notebook, plan):
        fields = {"version", "destination", "operations", "baseline", "before", "token", "presentation"}
        if not isinstance(plan, dict) or set(plan) != fields or plan["version"] != 1:
            raise ValueError("Invalid Notebook draft plan")
        current = notebook.storage.load(notebook.id)
        target = next((obj for obj in current.walk()
                       if isinstance(obj, Block) and str(obj.id) == plan["destination"]), None)
        if target is None:
            raise ValueError("Draft destination is outside this Notebook")
        draft = cls(current, target)
        for operation in plan["operations"]:
            draft._replay(operation)
        before, _ = draft._states()
        if (draft._baseline != plan["baseline"] or
                [state.records.to_record() for state in before] != plan["before"]):
            raise ValueError("Draft source or semantic context changed; prepare a fresh proposal")
        if plan["token"] is not None and draft.propose(plan["token"]) != plan["presentation"]:
            raise ValueError("Draft presentation changed; prepare a fresh proposal")
        return draft

    def land(self, *, proposal, approval, producer, support=None):
        """Apply an explicitly approved proposal; support validity remains a check."""
        if self._token is None or self._render(self._token) != self._presentation:
            raise ValueError("Present the exact current proposal before landing")
        fresh = self.restore(self.notebook, self.export())
        before, after = fresh._states()
        capture = fresh.notebook._owner(fresh.block).evidence
        operation = "modify" if before else "add"
        problems = capture.review_turn_problems(
            proposal=proposal.records.to_record(), approval=approval.records.to_record(),
            token=self._token, presentation=review_presentation(
                fresh.block.id, operation, before=[state.typed for state in before],
                after=[state.typed for state in after]))
        if problems:
            raise ValueError("Review cannot land: " + "; ".join(problem.message for problem in problems))
        text = "\n".join(message["text"] for message in proposal.resolve().target["messages"])
        if " ".join(fresh._presentation.split()) not in " ".join(text.split()):
            raise ValueError("Proposal must present the complete Block placement and Type changes")
        support = {str(key): tuple(members) for key, members in (support or {}).items()}
        if set(support) - set(fresh._edited):
            raise ValueError("Support names a Line outside this proposal")
        if any(not isinstance(member, SupportMember) for members in support.values() for member in members):
            raise TypeError("Support must contain typed SupportMember objects")
        # All preflight checks above are read-only. IO failures below may require reconciliation.
        capture.create()
        original_commit = capture.checkpoint()
        before = [capture.pin(state, commit=original_commit) for state in before]
        capture.notebook.save_tree(fresh.block)
        lines = [fresh._find(key) for key in fresh._edited]
        for line in lines:
            members = support.get(str(line.id), ())
            if not members:
                capture.attach_support(line, (), producer=producer)
            for member in members:
                capture.attach_support(line, (member,), producer=producer)
        review = capture.record_review(lines, destination=fresh.block,
                                        operation=operation, before=before,
                                        token=self._token, proposal=proposal, approval=approval)
        return capture.complete_review(review)
