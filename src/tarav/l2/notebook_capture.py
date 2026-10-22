"""Python-first Notebook capture and mechanical evidence inspection."""

from dataclasses import dataclass
import re
from uuid import uuid4

from pydantic import Field, model_validator

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TaravType, TypeShip, entity
from tarav.l1.chatlas import references as chat_refs
from tarav.l1.grounding import GroundingWorkflow, SubjectState, SupportSet
from tarav.l1.lines import Line
from tarav.l1.notebook.evidence import NotebookLine, ReviewedBlockTitle, ReviewedLine
from tarav.l1.notebook.workflow import NOTEBOOK_WORKFLOW_SHIP
from tarav.l1.records.registry import RecordRegistry
from tarav.l1.references import Reference
from tarav.l1.review import ReviewWorkflow, VerbatimReview, review_presentation


@dataclass(frozen=True)
class EvidenceProblem:
    kind: str
    message: str


class EvidenceUnavailable(ValueError):
    pass


# tarav.breadcrumb ed97d4c5d6b1
def line_state(line):
    """Only wording, concrete Types and authoring context determine this state."""
    context = []
    for block in (*reversed(line.scope.ancestors()), line.scope):
        context.append({
            "ship": str(block.id), "type": str(entity(type(block)).id),
            "lines": [{"ship": str(member.id), "type": str(entity(type(member)).id),
                       "text": member.text}
                      for member in block.contents if isinstance(member, Line) and member.id != line.id],
        })
    return SubjectState(line.id, entity(type(line)).id, {"text": line.text, "context": context})


def requirements(line):
    subjects = (line, line.scope, *line.scope.ancestors())
    types = tuple(base for subject in subjects for base in type(subject).__mro__)
    review = any(getattr(cls, "requires_review", False) for cls in types)
    return any(getattr(cls, "requires_support", False) for cls in types) or review, review


def _plain_text(text):
    return " ".join(text.split())


class NotebookReviewFrame(VerbatimReview):
    """Approval of an added Block's Markdown wording at a named destination.

    This frame reviews the displayed location, title and ordered Lines, not
    undisplayed UUIDs or Types. State snapshots bind that wording to the captured
    authoring context; subsequent changes still make its evidence stale.
    """

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("9d40a74a-e93e-4bab-93cf-ae43fbb2b232"),
                          name="Tarav.Notebook.ReviewFrame", workflow=NOTEBOOK_WORKFLOW_SHIP)

    class RecordInterface(VerbatimReview.RecordInterface):
        block_ship: Ship
        location: str = Field(min_length=1, pattern=r"^[^\r\n]+$")

        @model_validator(mode="after")
        def complete_added_block(self):
            if self.operation != "add" or self.before:
                raise ValueError("Notebook Review.Frame currently describes added Blocks only")
            if self.after[0].subject_type != entity(ReviewedBlockTitle).id:
                raise ValueError("Review.Frame needs a reviewed BlockTitle first")
            members = [{"ship": str(s.subject_ship), "type": str(s.subject_type),
                        "text": s.payload["text"]} for s in self.after]
            for state in self.after:
                context = state.payload.get("context", [])
                if (len(context) < 2 or context[-1]["ship"] != str(self.block_ship)
                        or context[-2]["ship"] != str(self.destination)):
                    raise ValueError("Review.Frame Block must be directly inside its destination")
                expected = [m for m in members if m["ship"] != str(state.subject_ship)]
                if context[-1]["lines"] != expected:
                    raise ValueError("Review.Frame must present all Block Lines in order")
            return self

    def __init__(self, *, id, destination, block_ship, location, after, token, proposal, approval):
        TaravEntity.__init__(self, id)
        self.typed = self.records.parse_record({
            "type": entity(type(self)).name, "id": str(id), "destination": str(destination),
            "operation": "add", "before": [],
            "after": [state.records.to_record() for state in after], "token": token,
            "proposal": proposal.records.to_record(), "approval": approval.records.to_record(),
            "block_ship": str(block_ship), "location": location,
        })

    def presentation(self):
        states = self.typed.after
        return (f"**Add to:** {self.typed.location}\n\n## {states[0].payload['text']}\n\n"
                + "\n".join(f"- {state.payload['text']}" for state in states[1:]))

    def ships(self):
        return (*super().ships(), self.typed.block_ship)

    class Records(VerbatimReview.Records):
        def record_example(self):
            from tarav.l1.lines import Block

            parent = Block(id=Ship("6a51f247-3857-4205-bf48-12b44bb1648b"))
            block = Block(id=Ship("9ce303eb-06ed-4a3c-9881-c3de7aa615a5"), parent=parent)
            title = ReviewedBlockTitle(id=Ship("ba962e69-2835-436f-b5c4-3e77105b6d79"),
                                       text="Kernel.Writing", scope=block)
            block.append(title)
            return {**super().record_example(), "operation": "add", "before": [],
                    "after": [line_state(title).records.to_record()],
                    "block_ship": str(block.id), "location": "Example Project → Discussion."}


# tarav.breadcrumb 23612b68dfdc
# tarav.breadcrumb 650516c5392b
class NotebookCapture(TaravType):
    """Evidence is appended in its Workflow partition; Notebook objects retain links."""

    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("77c91fab-b947-47d7-8c5a-648147886f64"),
                          name="Tarav.Notebook.Capture", workflow=NOTEBOOK_WORKFLOW_SHIP)

    def __init__(self, notebook, *, evidence_root=None, authorized_sources=()):
        self.notebook = notebook
        self.records = notebook.store.records
        registry = RecordRegistry(root=evidence_root, records=self.records)
        self.supports = registry.for_workflow(GroundingWorkflow)
        self.reviews = registry.for_workflow(ReviewWorkflow)
        self.authorized_sources = tuple(authorized_sources)
        self._resolved = {}

    def create(self):
        """Explicit provisioning only; reads and attachment never create storage."""
        self.supports.create()
        self.reviews.create()
        return self

    def capture(self, block, text, *, members=(), producer=None, reviewed=False, id=None):
        cls = ReviewedLine if reviewed else NotebookLine
        line = cls(id=id or Ship(uuid4()), text=text, scope=block)
        if self.notebook.store.path(str(line.id)).exists():
            raise FileExistsError(f"Capture creates new Lines; {line.id} already exists")
        block.append(line)
        self.notebook.save_tree(block)
        if members or producer is not None:
            self.attach_support(line, members, producer=producer)
        return line

    def _current(self, line):
        if not isinstance(line, NotebookLine):
            raise TypeError("Capture attachment requires a NotebookLine; no implicit Type migration")
        current = self.notebook.load(line.id)
        if line_state(current).typed.digest != line_state(line).typed.digest:
            raise ValueError("Save the intended Line and context before attaching evidence")

    def attach_support(self, line, members=(), *, producer=None):
        self._current(line)
        support = SupportSet(id=Ship(uuid4()), subject=line_state(line),
                             members=members, producer=producer)
        self.supports.insert(str(support.id), support)
        line.support_ships.append(support.id)
        self.notebook.save(line)
        return support

    def record_review(self, lines, *, destination, proposal, approval, token,
                      operation="review", before=(), frame_location=None):
        """Retain even failed review evidence; completion is a separate checked result."""
        lines = tuple(lines)
        for line in lines:
            self._current(line)
        if frame_location is not None:
            if operation != "add" or before or not lines:
                raise ValueError("Review.Frame requires an added Block")
            review = NotebookReviewFrame(
                id=Ship(uuid4()), destination=destination.id, block_ship=lines[0].scope_ship,
                location=frame_location, after=[line_state(line) for line in lines],
                proposal=proposal, approval=approval, token=token,
            )
        else:
            review = VerbatimReview(
                id=Ship(uuid4()), destination=destination.id, operation=operation,
                before=before, after=[line_state(line) for line in lines],
                proposal=proposal, approval=approval, token=token,
            )
        for state in (*review.typed.before, *review.typed.after):
            if str(destination.id) not in [item["ship"] for item in state.payload["context"]]:
                raise ValueError("Review targets must be within the declared destination context")
        self.reviews.insert(str(review.id), review)
        for line in lines:
            line.review_ships.append(review.id)
            self.notebook.save(line)
        return review

    def propose_review(self, lines, *, destination, token, operation="review", before=()):
        """Present real candidate states without fabricating future chat evidence."""
        return review_presentation(
            destination.id, operation, before=[state.typed for state in before],
            after=[line_state(line).typed for line in lines],
        ) + f"\n\n::approve {token}"

    def complete_review(self, review):
        self._resolved.clear()
        problems = self.review_problems(review)
        if problems:
            raise ValueError("Review is not complete: " + "; ".join(p.message for p in problems))
        # Do not return a success for a previously reviewed state that is no longer current.
        for state in review.typed.after:
            current = self.notebook.load(state.subject_ship)
            if line_state(current).typed.digest != state.digest:
                raise ValueError("Review is not complete: target state changed")
        if review.typed.operation == "remove":
            destination = self.notebook.load(review.typed.destination)
            remaining = {obj.id for obj in destination.walk()}
            if any(state.subject_ship in remaining for state in review.typed.before):
                raise ValueError("Review is not complete: removed targets are still present")
        return review

    def support_records(self, line):
        return tuple(self.supports.load(str(ship)) for ship in getattr(line, "support_ships", ()))

    def review_records(self, line):
        return tuple(self.reviews.load(str(ship)) for ship in getattr(line, "review_ships", ()))

    def _reference(self, record, *, role=None, authorize=False):
        if hasattr(record, "model_dump"):
            record = record.model_dump(mode="json", exclude_unset=True, by_alias=True)
        key = repr(record)
        if key not in self._resolved:
            try:
                reference = self.records.from_record(record)
            except (ValueError, TypeError, LookupError, RuntimeError) as exc:
                raise ValueError(f"Invalid evidence Reference: {exc}") from exc
            if not isinstance(reference, Reference):
                raise TypeError("Evidence requires a registered Reference Type")
            try:
                model = None
                if isinstance(reference, chat_refs.ChatlasTurnReference):
                    model = chat_refs.provide_normal_model(identity_hash=reference.locator["session_identity"])
                    standing = chat_refs.resolve_chat_turn_ref(model["turns"], reference.address())["standing"]
                    if standing == "AMENDED":
                        raise ValueError("Chatlas evidence changed at the referenced address")
                    if standing != "MATCHED":
                        raise EvidenceUnavailable("Chatlas evidence is missing")
                resolved = reference.resolve()
            except (OSError, LookupError, RuntimeError) as exc:
                raise EvidenceUnavailable(str(exc)) from exc
            if not resolved.ok:
                if resolved.status == "mismatch":
                    raise ValueError(resolved.message)
                raise EvidenceUnavailable(resolved.message)
            if isinstance(reference, chat_refs.ChatlasTurnReference):
                target = resolved.target
                position = next(i for i, turn in enumerate(model["turns"])
                                if turn["turn_address"] == reference.locator["turn_address"])
                self._resolved[key] = (reference, target, position)
            else:
                self._resolved[key] = (reference, resolved.target, None)
        reference, target, position = self._resolved[key]
        if isinstance(reference, chat_refs.ChatlasTurnReference):
            if role is not None and target["turn"]["side"] != role:
                raise ValueError(f"Evidence must be a {role} turn")
        elif role is not None or (authorize and type(reference) not in self.authorized_sources):
            raise ValueError("This evidence source Type has not been explicitly authorized")
        return reference, target, position

    def support_problems(self, support):
        if not isinstance(support, SupportSet):
            return (EvidenceProblem("Invalid", "Support link does not name a SupportSet"),)
        problems = []
        if not support.typed.members:
            problems.append(EvidenceProblem("Missing", "SupportSet has no substantive members"))
        if support.typed.producer is None:
            problems.append(EvidenceProblem("Invalid", "Conversational support has no producer turn"))
        try:
            producer = (self._reference(support.typed.producer, role="agent")
                        if support.typed.producer is not None else None)
            for member in support.typed.members:
                source = self._reference(member.source, authorize=True)
                if isinstance(source[0], chat_refs.ChatlasTurnReference):
                    if source[1]["turn"]["side"] != "user":
                        raise ValueError("Substantive support must be a User turn")
                    if (producer is not None and source[0].locator["session_identity"] ==
                            producer[0].locator["session_identity"] and source[2] >= producer[2]):
                        raise ValueError("Support must precede its producing Agent turn")
                for neighbor in member.neighborhood:
                    self._reference(neighbor)
        except EvidenceUnavailable as exc:
            problems.append(EvidenceProblem("Unavailable", str(exc)))
        except (ValueError, TypeError, KeyError) as exc:
            problems.append(EvidenceProblem("Invalid", str(exc)))
        return tuple(problems)

    def review_problems(self, review):
        if not isinstance(review, VerbatimReview):
            return (EvidenceProblem("Invalid", "Review link does not name a VerbatimReview"),)
        try:
            proposal, p, pi = self._reference(review.typed.proposal, role="agent")
            approval, a, ai = self._reference(review.typed.approval, role="user")
            if proposal.locator["session_identity"] != approval.locator["session_identity"] or pi >= ai:
                raise ValueError("Approval must follow its proposal in the same session")
            ptext = "\n".join(message["text"] for message in p["messages"])
            atext = "\n".join(message["text"] for message in a["messages"])
            if review.typed.token not in ptext or re.search(
                    rf"(?m)^\s*::approve\s+{re.escape(review.typed.token)}\s*$", atext) is None:
                raise ValueError("The User must explicitly approve the presented token")
            if _plain_text(review.presentation()) not in _plain_text(ptext):
                raise ValueError("Proposal must present destination, operation and bounded before/after wording")
        except EvidenceUnavailable as exc:
            return (EvidenceProblem("Unavailable", str(exc)),)
        except (ValueError, TypeError, KeyError) as exc:
            return (EvidenceProblem("Invalid", str(exc)),)
        return ()

    def inspect(self, line):
        """Recompute mechanical compliance; never mutate claims or produce semantic scores."""
        self._resolved.clear()
        current = line_state(line).typed
        needs_support, needs_review = requirements(line)
        result = {"state": current.model_dump(mode="json"), "support": (), "review": ()}
        for axis, required, store, ids, target, assess in (
            ("support", needs_support, self.supports, getattr(line, "support_ships", ()),
             lambda obj: [obj.typed.subject], self.support_problems),
            ("review", needs_review, self.reviews, getattr(line, "review_ships", ()),
             lambda obj: obj.typed.after, self.review_problems),
        ):
            if not required and not ids:
                continue
            candidates, errors, historical = [], [], False
            for ship in ids:
                try:
                    record = store.load(str(ship))
                    states = target(record)
                    if any(state.subject_ship == line.id and state.digest == current.digest for state in states):
                        candidates.append(record)
                    else:
                        historical = True
                except (OSError, LookupError, RuntimeError) as exc:
                    errors.append(EvidenceProblem("Unavailable", str(exc)))
                except (ValueError, TypeError, AttributeError) as exc:
                    errors.append(EvidenceProblem("Invalid", str(exc)))
            if candidates:
                checks = [assess(record) for record in candidates]
                result[axis] = () if any(not problems for problems in checks) else tuple(
                    p for problems in checks for p in problems)
            elif errors:
                result[axis] = tuple(errors)
            else:
                result[axis] = (EvidenceProblem("Stale" if historical else "Missing",
                                              f"No {axis} evidence for this Line/context state"),)
        return result
