"""Wiki ownership and its agent entrypoint."""

from tarav.l0.kernel import TaravClass, TaravWorkflow, TypeShip, WorkflowShip

WIKI_WORKFLOW_SHIP = WorkflowShip("9f226798-f201-431b-bc2e-a77a2e48bc53")


class WikiWorkflow(TaravWorkflow):
    constitution = (
        "Organize Markdown notes and capture supported discussion into a Wiki."
    )

    @classmethod
    def class_entity(cls):
        return TaravClass(
            target=cls,
            id=TypeShip("b05694d2-808e-4464-ab0c-3e575d79d4ea"),
            name="Tarav.Workflow.Wiki",
            workflow=WIKI_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return WIKI_WORKFLOW_SHIP

    @classmethod
    def help(cls):
        return {
            **super().help(),
            "capture": {
                "skill": "tarav-hugentics",
                "invocation": "tarav-hugentics --capture --wiki",
                "instructions": "references/wiki-capture.md",
            },
        }
