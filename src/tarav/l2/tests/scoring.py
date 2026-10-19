"""Disposable chat-to-Lines scenario for exercising pairwise scoring."""

from __future__ import annotations

__test__ = False

from dataclasses import dataclass
from uuid import UUID, uuid5

from tarav.l0.kernel import Ship, TaravClass, TaravEntity, TypeShip, WorkflowShip, entity
from tarav.l1.assertions import Assertable
from tarav.l1.lines import Block, Line
from tarav.l2.scoring import Assertion, PairwiseRankingCase, Tribunal
from .workflow import TestsWorkflow
from tarav.l0.kernel import LoadedRecord


SCORING_TESTS_WORKFLOW_SHIP = WorkflowShip("3a99b56b-7162-4ffd-bb88-e2fe6065fd9e")
_SCENARIO_NAMESPACE = UUID("c4f0fd84-1f53-48ae-bbd5-dc73403909e1")


def _ship(label: str) -> Ship:
    return Ship(uuid5(_SCENARIO_NAMESPACE, label))


class ScoringTestsWorkflow(TestsWorkflow):
    """Own synthetic scoring subjects and their concrete assessment method."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("a81f7f4a-5e7c-4cea-9497-bc83e81877fc"),
            name="Tarav.Workflow.Tests.Scoring", workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SCORING_TESTS_WORKFLOW_SHIP

    @property
    def workflow(self):
        return TestsWorkflow()

    constitution = "Exercise scoring on disposable, explicitly synthetic evidence."


class ScoringTestChat(TaravEntity):
    """An authored synthetic sequence of User turns, not a Chatlas capture."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("811db5bb-84d0-45a9-abd6-5ff7a1bbf48d"),
            name="Tarav.Tests.Scoring.Chat", workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    class RecordInterface(TaravEntity.RecordInterface):
        turns: list[dict[str, str]]

    def __init__(self, *, id: Ship, turns: list[dict[str, str]]):
        super().__init__(id)
        if len({turn["id"] for turn in turns}) != len(turns):
            raise ValueError("Synthetic User turn IDs must be unique")
        self.turns = tuple({"id": turn["id"], "text": turn["text"]} for turn in turns)

    def _to_record(self):
        return {**super()._to_record(), "turns": list(self.turns)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(id=loaded.data.id, turns=loaded.data.turns)

    class Records(TaravEntity.Records):
        def record_example(self):
            cls = self._owner
            return cls(id=_ship("example-chat"), turns=[{"id": "u01", "text": "The car is red."}]).records.to_record()



class ScoringTestLine(Line, Assertable):
    """A scoped candidate extraction with its declared User-turn citations."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("ec13cb03-5304-4cc2-9be4-886f8d40c13e"),
            name="Tarav.Tests.Scoring.Line", workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    class RecordInterface(Line.RecordInterface):
        chat_ship: Ship
        turn_ids: list[str]

    def __init__(self, *, id: Ship, text: str, scope: Block,
                 chat_ship: Ship, turn_ids: tuple[str, ...]):
        if not isinstance(scope, Block):
            raise TypeError("Scoring test Line scope must be a Block")
        if not turn_ids or len(set(turn_ids)) != len(turn_ids):
            raise ValueError("A candidate Line needs distinct cited User turns")
        super().__init__(id=id, text=text, scope=scope)
        self.chat_ship = chat_ship
        self.turn_ids = tuple(turn_ids)

    @property
    def assertions(self):
        return {"support": LineSupportAssertion({
            "type": "Tarav.Tests.Scoring.Line.Reference",
            "chat_id": str(self.chat_ship), "line_id": str(self.id),
            "scope_id": str(self.scope_ship), "text": self.text,
            "turn_ids": list(self.turn_ids),
        })}

    def _to_record(self):
        return {**super()._to_record(), "chat_ship": str(self.chat_ship),
                "turn_ids": list(self.turn_ids)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        obj = super()._from_record(loaded)
        obj.chat_ship = loaded.data.chat_ship
        obj.turn_ids = tuple(loaded.data.turn_ids)
        return obj

    class Records(Line.Records):
        def record_example(self):
            cls = self._owner
            return {
                **Line.records.record_example(), "type": entity(cls).name,
                "chat_ship": str(_ship("example-chat")), "turn_ids": ["u01"],
            }



class LineSupportCase(PairwiseRankingCase):
    """Closed Line, scope, citations, and local transcript evidence."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("a9325f62-ea71-4cec-853f-5b13e219a786"),
            name="Tarav.Tests.Scoring.LineSupportCase",
            workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    class RecordInterface(PairwiseRankingCase.RecordInterface):
        line_id: str
        chat_id: str
        turn_ids: list[str]

    class Records(PairwiseRankingCase.Records):
        def record_example(self):
            cls = self._owner
            chat_id, line_id = str(_ship("example-chat")), str(_ship("example-line"))
            assertion = LineSupportAssertion({
                "type": "Tarav.Tests.Scoring.Line.Reference",
                "chat_id": chat_id, "line_id": line_id,
                "scope_id": str(_ship("example-block")), "text": "A sample Line.",
                "turn_ids": ["u01"],
            })
            return cls(
                assertion_ref=assertion.reference(),
                tribunal_type_id=str(entity(LineSupportTribunal).id),
                question="How strongly is this Line supported?",
                presentation="A synthetic Line and its User turn.",
                line_id=line_id, chat_id=chat_id, turn_ids=["u01"],
            ).records.to_record()



class LineSupportAssertion(Assertion):
    """Claim that one scoped Line is supported by its cited User turns."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("a3d9291e-2f09-44c2-a298-802ae7d4a854"),
            name="Tarav.Tests.Scoring.LineSupport.Assertion",
            workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def assessment_case_types(cls):
        return (LineSupportCase,)

    def _build_assessment_case(self, case_type, *, line: ScoringTestLine,
                               chat: ScoringTestChat):
        if not isinstance(line, ScoringTestLine) or not isinstance(chat, ScoringTestChat):
            raise TypeError("Line support needs a test Line and chat")
        if self.subject_ref != line.assertions["support"].subject_ref or line.chat_ship != chat.id:
            raise ValueError("Line and chat do not match the Assertion subject")
        turns = {turn["id"]: turn["text"] for turn in chat.turns}
        if any(turn_id not in turns for turn_id in line.turn_ids):
            raise ValueError("Line cites a missing User turn")
        block = line.scope
        if line.id not in block.line_ships:
            raise ValueError("Line is not a member of its declared scope Block")
        evidence = "\n".join(f"{turn_id}: {turns[turn_id]}" for turn_id in line.turn_ids)
        return case_type(
            assertion_ref=self.reference(),
            tribunal_type_id=str(entity(LineSupportTribunal).id),
            question="How strongly do the User turns support this scoped Line?",
            presentation=(f"Block scope: {block.topic}\nCandidate Line: {line.text}\n"
                          f"Cited User turns: {', '.join(line.turn_ids)}\n"
                          f"Relevant User turns:\n{evidence}"),
            line_id=str(line.id), chat_id=str(chat.id), turn_ids=list(line.turn_ids),
        )


class LineSupportTribunal(Tribunal):
    """Compare support strength, not factual importance or writing style."""

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls, id=TypeShip("ca5b0952-3c69-459e-a844-97f5cf20ea25"),
            name="Tarav.Tests.Scoring.LineSupportTribunal",
            workflow=SCORING_TESTS_WORKFLOW_SHIP,
        )

    @classmethod
    def _tribunal_id(cls):
        return Ship("1d98ad85-7e96-4569-83f5-2e53085c9aa2")

    def comparison_question(self):
        return "Which scoped Line is more faithfully supported by the supplied User turns?"

    def instructions(self):
        return ("Compare evidence support, including corrections and contradictions. "
                "Do not prefer a Line merely because its topic is more important. "
                "Abstain if the packets do not permit a comparison.")


@dataclass(frozen=True)
class LineSupportScenario:
    chat: ScoringTestChat
    blocks: tuple[Block, ...]
    lines: tuple[ScoringTestLine, ...]

    def case(self, line: ScoringTestLine) -> LineSupportCase:
        if line not in self.lines:
            raise ValueError("Line is outside this scenario")
        return line.assertions["support"].assessment_case(
            LineSupportCase, line=line, chat=self.chat,
        )


# Each topic has two synthetic User turns and five candidate extractions.
# Some candidates deliberately overclaim or contradict a correction.
_TOPICS = (
    ("Project marker", "The project marker lives in .tarav/project.json. It stores the project ID.",
     "The marker does not store my machine-local environment path.",
     ("The marker lives in .tarav/project.json.", "The marker stores the project ID.",
      "The environment path is not machine-local marker data.", "The marker stores my home directory.",
      "The marker is named project.yaml.")),
    ("Environment", "The project environment is normally .tarav/env. We install Tarav there.",
     "An explicit harness setting may select a different environment.",
     ("The default environment is .tarav/env.", "Tarav is installed in the project environment.",
      "A harness setting can select another environment.", "Every project must use system Python.",
      "The environment is always .venv.")),
    ("Workflow ownership", "A Type has one containing workflow in its class entity.",
     "That parent is one organization path, not the only meaningful view.",
     ("A Type's class entity declares one workflow owner.", "Workflow ownership is an organization path.",
      "Other views may group the same Type differently.", "Every Type has several workflow parents.",
      "Workflow ownership is the only semantic path.")),
    ("Archive", "Archive records artifacts without interpreting their internal meaning.",
     "A missing artifact can leave useful location history behind.",
     ("Archive records artifacts.", "Archive does not interpret artifact contents.",
      "Location history may survive an unavailable artifact.", "Archive resolves every missing artifact.",
      "Archive deletes all records when an artifact is missing.")),
    ("Context", "Context is a navigable view over subjects and entries.",
     "Opening an entry does not move the explorer cursor.",
     ("Context exposes navigable entries.", "A Context view is rooted at a subject.",
      "Opening an entry does not navigate.", "Opening always changes the cursor.",
      "Context entries must be files.")),
    ("Checks", "Checks run independently and can produce POIs.",
     "A passing check does not prove every semantic claim is correct.",
     ("Checks can produce POIs.", "Checks can run independently.",
      "A passing check has bounded coverage.", "Passing checks prove semantic truth.",
      "Checks cannot run without a linter.")),
    ("POIs", "A POI is a point of interest, not necessarily a failure.",
     "A notification POI can report a successful automatic observation.",
     ("A POI need not indicate failure.", "POI means point of interest.",
      "Notification POIs can report an observation.", "Every POI blocks mutation.",
      "Notification POIs are always errors.")),
    ("Blessings", "A blessing is an attributed decision about a situation.",
     "A blessing does not prevent the POI from being raised again.",
     ("Blessings are attributed decisions.", "Blessings concern a situation.",
      "A POI may still be raised after blessing.", "Blessings erase POIs.",
      "Blessings are anonymous.")),
    ("Lines", "A Line is one typed natural-language contribution within a Block.",
     "A Block supplies the Line's context and may inherit context from a parent Block.",
     ("A Line has one authoring Block.", "A Line expresses a natural-language contribution.",
      "A child Block inherits its parent's context.", "A Line has no interpretive context.",
      "Adding a Line to a Block changes its scope automatically.")),
    ("Scoring", "A scoring Assertion can build a typed closed case for a tribunal.",
     "The tribunal compares cases; a ranking score is derived from retained judgments.",
     ("An Assertion can build a typed case.", "A tribunal compares admitted cases.",
      "Ranking scores derive from judgments.", "The case itself is the judgment.",
      "Every scoring method must use a tribunal.")),
)


def build_line_support_scenario() -> LineSupportScenario:
    """Build a stable 20-turn, 10-Block, 50-Line synthetic corpus."""
    turns: list[dict[str, str]] = []
    blocks: list[Block] = []
    lines: list[ScoringTestLine] = []
    chat_id = _ship("chat")
    for topic_index, (topic, first, second, candidates) in enumerate(_TOPICS, start=1):
        first_id, second_id = f"u{2 * topic_index - 1:02}", f"u{2 * topic_index:02}"
        turns.extend(({"id": first_id, "text": first}, {"id": second_id, "text": second}))
        block = Block(id=_ship(f"block:{topic_index}"), topic=topic)
        blocks.append(block)
        for candidate_index, candidate in enumerate(candidates, start=1):
            line = ScoringTestLine(
                id=_ship(f"line:{topic_index}:{candidate_index}"), text=candidate,
                scope=block, chat_ship=chat_id, turn_ids=(first_id, second_id),
            )
            block.append(line)
            lines.append(line)
    return LineSupportScenario(
        chat=ScoringTestChat(id=chat_id, turns=turns),
        blocks=tuple(blocks), lines=tuple(lines),
    )


__all__ = [
    "SCORING_TESTS_WORKFLOW_SHIP", "ScoringTestsWorkflow", "ScoringTestChat",
    "ScoringTestLine", "LineSupportAssertion", "LineSupportCase",
    "LineSupportTribunal", "LineSupportScenario", "build_line_support_scenario",
]
