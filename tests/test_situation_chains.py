"""A Situation Chain groups the Types of one situation's links and binds them."""

from __future__ import annotations

import pytest

from tarav.l0.kernel import TaravClass, TypeShip, entity
from tarav.l1.checks import CheckPOI, CheckResult, CHECKS_WORKFLOW_SHIP, SituationCheck
from tarav.l1.checks.chains import SituationChain
from tarav.l1.poi import fingerprint


class LampOn(CheckPOI):
    """A lamp was found on."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("d138efb2-623c-41d9-9b59-fef203c56235"),
                          name="Tarav.Test.Chains.LampOn", workflow=CHECKS_WORKFLOW_SHIP)


class Unrelated(CheckPOI):
    """A POI of no lamp chain."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("03d1130b-da58-496d-bf8e-2bdcca6321ff"),
                          name="Tarav.Test.Chains.Unrelated", workflow=CHECKS_WORKFLOW_SHIP)


class LampCheck(SituationCheck):
    """Is the lamp on? Its caller gives the lamp and the level it read."""

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("b120cb78-7a96-4174-b7d1-9ff45bb9542e"),
                          name="Tarav.Test.Chains.LampCheck", workflow=CHECKS_WORKFLOW_SHIP)

    def __init__(self, *, situation, raises=LampOn) -> None:
        super().__init__(situation=situation)
        self.raises = raises

    def _run(self) -> CheckResult:
        if not self.situation["level"]:
            return CheckResult(self, status="completed")
        poi = self.poi(self.raises, message=f"{self.situation['lamp']} is on")
        return CheckResult(self, status="completed", pois=(poi,))


class LampChain(SituationChain):
    """A lamp, read at one level."""

    Check = LampCheck
    POIs = (LampOn,)

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(target=cls, id=TypeShip("adb767b3-bd07-4e13-874b-91531497ba4e"),
                          name="Tarav.Test.Chains.Lamp", workflow=CHECKS_WORKFLOW_SHIP)


HALL = {"lamp": "hall", "level": 3}


def test_defining_a_chain_binds_its_links_to_it():
    assert LampCheck.chain is LampChain and LampOn.chain is LampChain
    assert Unrelated.chain is None


def test_an_instance_is_one_situation_and_takes_its_identity_from_it():
    chain = LampChain(HALL)
    assert chain.identity == fingerprint([str(entity(LampChain).id), HALL])
    assert chain.identity == LampChain(dict(HALL)).identity
    assert chain.identity != LampChain({**HALL, "level": 2}).identity


def test_the_check_of_an_instance_raises_the_chains_poi_about_its_situation():
    chain = LampChain(HALL)
    (poi,) = chain.check().run().pois()
    assert type(poi) is LampOn and poi.situation == HALL
    assert poi.identity == fingerprint([str(entity(LampOn).id), HALL])
    assert chain.check().identity == fingerprint([str(entity(LampCheck).id), HALL])
    assert list(LampChain({**HALL, "level": 0}).check().run().pois()) == []


def test_a_chains_check_raises_only_the_chains_pois():
    with pytest.raises(TypeError, match="Tarav.Test.Chains.Unrelated is not a POI of Tarav.Test.Chains.Lamp"):
        LampChain.Check(situation=HALL, raises=Unrelated).run()


def test_a_link_belongs_to_one_chain():
    with pytest.raises(TypeError, match="Tarav.Test.Chains.LampCheck already belongs to Tarav.Test.Chains.Lamp"):
        class Another(SituationChain):
            Check = LampCheck
            POIs = (LampOn,)

            @classmethod
            def class_entity(cls) -> TaravClass:
                return TaravClass(target=cls, id=TypeShip("5d7cd32f-3c12-4cad-848e-9b36c50e870f"),
                                  name="Tarav.Test.Chains.Another", workflow=CHECKS_WORKFLOW_SHIP)
