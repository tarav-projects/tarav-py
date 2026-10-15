"""Small synthetic conversation family for the RDF experiment, not Chatlas."""

from typing import Literal

from pydantic import ConfigDict

from tarav.l0.kernel import Ship, TypeShip

from .types import FutureEntity, ModelMember, class_projection


CONVERSATION_TYPE = TypeShip("95e2823e-56f7-4430-9be3-f2da9472dc43")
TURN_TYPE = TypeShip("f81898bd-712b-4824-981b-979f8a1020f1")
ANNOTATION_TYPE = TypeShip("87015cf3-294c-4fab-855c-64cb4d1f221f")

HAS_TURN = ModelMember(Ship("ace3e7d4-6fdc-4966-9d82-491df7b73883"), CONVERSATION_TYPE, "turns")
TITLE = ModelMember(Ship("0427e63d-eefb-4b02-a14f-1732051bb7b8"), CONVERSATION_TYPE, "title")
IN_CHAT = ModelMember(Ship("80b9c0f5-6354-46c0-bc06-f75fd732054b"), TURN_TYPE, "conversation")
AUTHOR = ModelMember(Ship("53033292-5a4a-4c7c-82f4-bacb700a4eb2"), TURN_TYPE, "author")
TEXT = ModelMember(Ship("3661ce73-44d6-4227-abf9-5bacbe369c7b"), TURN_TYPE, "text")
READ_TEXT = ModelMember(Ship("c3e22eb1-b8ed-4260-adc0-de1a3ab36036"), TURN_TYPE, "read_text")
ABOUT = ModelMember(Ship("82b205a2-2489-48da-bc81-fb630eaa39e0"), ANNOTATION_TYPE, "about")
NOTE_TEXT = ModelMember(Ship("679e9288-7849-45fe-9b68-b9104d49c372"), ANNOTATION_TYPE, "text")


# tarav.context 473c89a0:8944495a171e5499
class Conversation(FutureEntity):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, str(CONVERSATION_TYPE), "Conversation")

    class RecordInterface(FutureEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Future.Conversation"]
        title: str
        turns: list[Ship]

    def __init__(self, id: Ship, title: str, turns=()):
        super().__init__(id)
        self.title, self.turns = title, tuple(turns)

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, record_data.title, record_data.turns)

    def _to_record(self):
        return {**super()._to_record(), "title": self.title,
                "turns": [str(value) for value in self.turns]}

    class Context(FutureEntity.Context):
        def model_nodes(self):
            return (*super().model_nodes(), HAS_TURN, TITLE)


class UserTurn(FutureEntity):
    @classmethod
    def class_entity(cls):
        return class_projection(cls, str(TURN_TYPE), "UserTurn")

    class RecordInterface(FutureEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Future.UserTurn"]
        conversation: Ship
        author: str
        text: str

    def __init__(self, id: Ship, conversation: Ship, author: str, text: str):
        super().__init__(id)
        self.conversation, self.author, self.text = conversation, author, text

    def read_text(self):
        return self.text

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, record_data.conversation, record_data.author, record_data.text)

    def _to_record(self):
        return {**super()._to_record(), "conversation": str(self.conversation),
                "author": self.author, "text": self.text}

    class Context(FutureEntity.Context):
        def model_nodes(self):
            return (*super().model_nodes(), IN_CHAT, AUTHOR, TEXT, READ_TEXT)


class Annotation(FutureEntity):
    """Synthetic external note used only to exercise graph navigation."""

    @classmethod
    def class_entity(cls):
        return class_projection(cls, str(ANNOTATION_TYPE), "Annotation")

    class RecordInterface(FutureEntity.RecordInterface):
        model_config = ConfigDict(strict=True, extra="forbid")
        type: Literal["Tarav.Future.Annotation"]
        about: Ship
        text: str

    def __init__(self, id: Ship, about: Ship, text: str):
        super().__init__(id)
        self.about, self.text = about, text

    @classmethod
    def _from_record(cls, record_data):
        return cls(record_data.id, record_data.about, record_data.text)

    def _to_record(self):
        return {**super()._to_record(), "about": str(self.about), "text": self.text}

    class Context(FutureEntity.Context):
        def model_nodes(self):
            return (*super().model_nodes(), ABOUT, NOTE_TEXT)


RECORD_TYPES = (Conversation, UserTurn, Annotation, ModelMember)
