"""Read-only checks of the configured agent setup: monitor config and per-agent fitness.

An integration above `tarav.l1.agent` and the Checks/Actions workflows it reports through.

They report what the agent commands would otherwise only raise at run time, so a
stale profile, account or home surfaces as a finding instead of a crashed monitor.
"""

from __future__ import annotations

from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import LoadedRecord, TaravClass, TaravObject, TypeShip, entity
from tarav.l1.actions.pois import POIResolutionAction
from tarav.l1.checks import CheckPOI, CheckProvider, CheckResult, CheckSuite, SituationCheck
from tarav.l1.checks.chains import SituationChain

from tarav.l1.agent.config import load_agent_configs
from tarav.l1.agent.identity import AGENTS_WORKFLOW_SHIP
from tarav.l1.agent.monitor.config import load_monitor_workflow_configs
from tarav.l1.agent.profile_check import (
    CHECKPOINT_ACCOUNT_REGISTERED,
    CHECKPOINT_HOME_ALIGNED,
    CHECKPOINT_HOME_EXISTS,
)
from tarav.l1.agent.providers.registry import agent_from_config


def _type(cls, ship: str, name: str) -> TaravClass:
    return TaravClass(target=cls, id=TypeShip(ship), name=name, workflow=AGENTS_WORKFLOW_SHIP)


class MonitorConfigInvalid(CheckPOI):
    """The account monitor configuration does not load."""

    action = "Tarav.Agents.MonitorConfig.Invalid.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "473289e0-7555-4565-a109-0b2d6053a23b",
                     "Tarav.Agents.MonitorConfig.Invalid.POI")


class ProfilesInvalid(CheckPOI):
    """The configured agent profiles do not load."""

    action = "Tarav.Agents.Profiles.Invalid.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "5c8d6452-6921-44bc-83c7-d333e9edbb5b",
                     "Tarav.Agents.Profiles.Invalid.POI")


class AccountNotRegistered(CheckPOI):
    """An agent names no account, or one absent from managed account storage."""

    action = "Tarav.Agents.Fitness.AccountNotRegistered.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "181c89db-735a-43ff-8623-27f0df755105",
                     "Tarav.Agents.Fitness.AccountNotRegistered.POI")


class HomeMissing(CheckPOI):
    """An agent names no home, or a home directory that does not exist."""

    action = "Tarav.Agents.Fitness.HomeMissing.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "247953b6-7181-4d91-86d6-117ffa45057f",
                     "Tarav.Agents.Fitness.HomeMissing.POI")


class HomeMisaligned(CheckPOI):
    """An agent's home auth does not match its account in managed storage."""

    action = "Tarav.Agents.Fitness.HomeMisaligned.Action"

    @classmethod
    def class_entity(cls):
        return _type(cls, "a4fa8d3a-114f-4585-bd55-f55d81bccbe0",
                     "Tarav.Agents.Fitness.HomeMisaligned.POI")


class MonitorConfigInvalidResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "88bbfc59-4b93-4776-a3ee-617c32130e38",
                     "Tarav.Agents.MonitorConfig.Invalid.Action")


class ProfilesInvalidResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "9123d2b8-0d42-480a-ae41-c03918311215",
                     "Tarav.Agents.Profiles.Invalid.Action")


class AccountNotRegisteredResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "a6183f7f-71b3-42ab-9477-4e17aa3fc976",
                     "Tarav.Agents.Fitness.AccountNotRegistered.Action")


class HomeMissingResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "069cb7cf-6f1c-4790-b7d0-6649180bf9ce",
                     "Tarav.Agents.Fitness.HomeMissing.Action")


class HomeMisalignedResolution(POIResolutionAction):
    @classmethod
    def class_entity(cls):
        return _type(cls, "6cdea493-fa20-484b-b4f6-dc6ca9278098",
                     "Tarav.Agents.Fitness.HomeMisaligned.Action")


# tarav.breadcrumb 436c9a74799b
class MonitorConfigCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return _type(cls, "bdb6145d-82d8-4a8e-851c-c81238018d61", "Tarav.Agents.MonitorConfig.Check")

    def __init__(self, *, situation, start_path: Path):
        super().__init__(situation=situation)
        self.start_path = start_path

    def _run(self):
        try:
            load_monitor_workflow_configs(start_path=self.start_path)
        except CliError as exc:
            return CheckResult(self, status="completed", pois=[self.poi(
                MonitorConfigInvalid, message=f"Account monitor config does not load: {exc}")])
        return CheckResult(self, status="completed")


class ProfilesCheck(SituationCheck):
    @classmethod
    def class_entity(cls):
        return _type(cls, "b65141d1-91b5-4331-b6a6-7715c27f0df6", "Tarav.Agents.Profiles.Check")

    def __init__(self, *, situation, start_path: Path):
        super().__init__(situation=situation)
        self.start_path = start_path
        self.agents = None

    def _run(self):
        self.agents = None
        try:
            self.agents = load_agent_configs(start_path=self.start_path)
        except CliError as exc:
            return CheckResult(self, status="completed", pois=[self.poi(
                ProfilesInvalid, message=f"Agent profiles do not load: {exc}")])
        return CheckResult(self, status="completed")


_CHECKPOINT_POIS = {
    CHECKPOINT_ACCOUNT_REGISTERED: AccountNotRegistered,
    CHECKPOINT_HOME_EXISTS: HomeMissing,
    CHECKPOINT_HOME_ALIGNED: HomeMisaligned,
}


class FitnessCheck(SituationCheck):
    """The `agent profile-check` checkpoints of one configured agent, as POIs."""

    @classmethod
    def class_entity(cls):
        return _type(cls, "f925a5b9-4ca6-40a6-9b3d-bd4b703e8642", "Tarav.Agents.Fitness.Check")

    def __init__(self, *, situation, agent):
        super().__init__(situation=situation)
        self.agent = agent

    def _run(self):
        checkpoints = agent_from_config(self.agent).profile_check().checkpoints
        failed = {c.id: c for c in checkpoints if not c.passed}
        if CHECKPOINT_HOME_EXISTS in failed:
            # Alignment cannot be judged for a home that is not there.
            failed.pop(CHECKPOINT_HOME_ALIGNED, None)
        details = {"home": str(self.agent.home) if self.agent.home is not None else None}
        return CheckResult(self, status="completed", pois=[
            self.poi(_CHECKPOINT_POIS[checkpoint.id],
                     message=f"{self.situation['agent']}: {checkpoint.reason}", details=details)
            for checkpoint in failed.values()])


class MonitorConfigChain(SituationChain):
    Check = MonitorConfigCheck
    POIs = (MonitorConfigInvalid,)

    @classmethod
    def class_entity(cls):
        return _type(cls, "cbaccd96-17bb-415b-b16b-f511d6dac220", "Tarav.Agents.MonitorConfig.Chain")


class ProfilesChain(SituationChain):
    Check = ProfilesCheck
    POIs = (ProfilesInvalid,)

    @classmethod
    def class_entity(cls):
        return _type(cls, "33367678-72fe-41ae-b6c4-cabe12823ba2", "Tarav.Agents.Profiles.Chain")


class FitnessChain(SituationChain):
    Check = FitnessCheck
    POIs = (AccountNotRegistered, HomeMissing, HomeMisaligned)

    @classmethod
    def class_entity(cls):
        return _type(cls, "5091ea05-e5db-420a-b635-0b72d1129c30", "Tarav.Agents.Fitness.Chain")


# tarav.breadcrumb f23bbde3b417
class AgentSetupSuite(CheckSuite):
    """Monitor config, then profile loading, then the fitness of every loaded agent."""

    @classmethod
    def class_entity(cls):
        return _type(cls, "f7b9389a-1c2c-4db9-90d9-f86471c5ea4a", "Tarav.Agents.Setup.Suite")

    def __init__(self, setup: AgentSetup):
        self.setup = setup
        super().__init__(name="Agent setup", key=str(setup.start_path))

    def produce(self):
        yield MonitorConfigChain({"start_path": self.key}).check(start_path=self.setup.start_path)
        profiles = ProfilesChain({"start_path": self.key}).check(start_path=self.setup.start_path)
        yield profiles
        if profiles.agents is None:
            # Without loaded profiles, earlier fitness findings cannot be settled.
            self._refused += 1
            return
        for agent in profiles.agents:
            name = f"{agent.provider}/{agent.profile_id}"
            yield FitnessChain({"start_path": self.key, "agent": name}).check(agent=agent)


class AgentSetup(TaravObject, CheckProvider):
    """The agent configuration as resolved from one start path."""

    @classmethod
    def class_entity(cls):
        return _type(cls, "3327eba5-a30f-4f7e-8ded-cf1649f2ad0a", "Tarav.Agents.Setup")

    class RecordInterface(TaravObject.RecordInterface):
        start_path: str

    def __init__(self, start_path: Path | str = "."):
        super().__init__()
        self.start_path = Path(start_path).expanduser().resolve()

    class Checks(CheckProvider.Checks):
        def suite(self):
            return AgentSetupSuite(self.obj)

    def _to_record(self):
        return {"type": entity(type(self)).name, "start_path": str(self.start_path)}

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        return cls(loaded.data.start_path)

    class Records(TaravObject.Records):
        def record_example(self):
            return {"type": entity(self._owner).name, "start_path": "/example/project"}


AGENT_SETUP_POI_TYPES = (MonitorConfigInvalid, ProfilesInvalid, AccountNotRegistered,
                         HomeMissing, HomeMisaligned)
AGENT_SETUP_ACTION_TYPES = (MonitorConfigInvalidResolution, ProfilesInvalidResolution,
                            AccountNotRegisteredResolution, HomeMissingResolution,
                            HomeMisalignedResolution)
AGENT_SETUP_RECORD_TYPES = (AgentSetup, *AGENT_SETUP_POI_TYPES)

__all__ = ["AGENT_SETUP_ACTION_TYPES", "AGENT_SETUP_POI_TYPES", "AGENT_SETUP_RECORD_TYPES",
           "AccountNotRegistered", "AgentSetup", "AgentSetupSuite", "HomeMisaligned",
           "HomeMissing", "MonitorConfigInvalid", "ProfilesInvalid"]
