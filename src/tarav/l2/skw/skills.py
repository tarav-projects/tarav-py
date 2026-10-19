"""Explicit skill-package compilation and consumer deployment."""
import shutil
from typing import Literal
from pathlib import Path

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeRegistry, TypeShip
from tarav.l0.kernel.records import entry_file
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.code import CodeWorkflow
from tarav.l1.skw.depot import SkwDepot
from tarav.l0.kernel import Ship
from tarav.l0.project import find_agentos_project_root
from tarav.l1.skw.document import DEFAULT_DEPOT, Document, project_document
from tarav.l1.skw.loading import LoadingRecord, SkillDocument, SkillReadingGraph
from tarav.l1.skw.skills import SKILL_COMPONENT_TYPES
from tarav.l1.checks import CheckProvider, CheckSuite
from tarav.l1.poi import POICollector
from tarav.l1.poi.rendering import DEFAULT_POI_RENDERER, renderers
from tarav.l1.skills import SKILL_JSON, TaravSkill
from tarav.l0._core.errors import CliError
from tarav.l1.skw.pois import SkwPOI
from .chains import SKW_CHAIN_CHECK_TYPES, SkwSkillSuite
from tarav.l1.skw.presentation import (
    add_output_mode,
    emit,
    render_loading_context,
    render_poi,
    render_skill_block,
    render_skill_listing,
    render_skill_operation,
)
from tarav.l0.kernel import LoadedRecord


#: Where a Project keeps the depots of the skills it builds.
SKILL_DEPOTS = Path(DEFAULT_DEPOT) / "skills"


# tarav.breadcrumb 46ea29390613
class SkwSkill(SkwDepot, TaravSkill, CheckProvider):
    """A deployable Skill built by one typed depot of its Project: the SKW kind of TaravSkill.

    The depot lives at `<project>/.tarav/skillware/skills/<name>/`; the skill
    folder it builds keeps only the product and its `.tarav/skill.json`. The
    depot names that folder (`product`, relative to the Project) and the
    skill (`skill_id`); a skill is not a Project and always belongs to the one
    holding its depot.

    The entry record owns deployment selection; source context stays developer-only.
    Dependency purposes are independent of document context roles. Build and
    check never accept context baselines or regenerate agent-authored content.
    """

    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('1b456d93-9d24-40df-a4a6-f1d0470ec949'),
            name='Tarav.Skillware.SkillPackage',
        )

    class RecordInterface(SkwDepot.RecordInterface):
        type: Literal['Tarav.Skillware.SkillPackage']
        schema_version: int
        skill_id: str
        product: str
        entrypoint: str
        sources: list[str]
        files: list[str]
        dependencies: list[dict[str, object]] = []
        loading: str | None = None

    # tarav.breadcrumb 70b9905101ea
    def __init__(self, *, skill_id=None, product=None, entrypoint='SKILL.md', sources=(),
                 files=None, dependencies=(), loading=None, depot=None):
        """A skill built in code; its `depot` may stay unknown until it is placed."""
        super().__init__()
        self.schema_version = 1
        self.declared_skill_id = skill_id
        self.product = product
        self.entrypoint_file = entrypoint
        self.sources = list(sources)
        self.files = list(files) if files is not None else [entrypoint]
        self.dependencies = [dict(d) for d in dependencies]
        self.loading_file = loading
        if depot is not None:
            self.source = Path(depot) / 'main.json'

    @classmethod
    def _from_record(cls, loaded: LoadedRecord):
        skill = cls(skill_id=loaded.data.skill_id, product=loaded.data.product,
                    entrypoint=loaded.data.entrypoint, sources=loaded.data.sources,
                    files=loaded.data.files, dependencies=loaded.data.dependencies,
                    loading=loaded.data.loading)
        skill.schema_version = loaded.data.schema_version
        return skill

    def _to_record(self):
        record = {'type': entity(type(self)).name, 'schema_version': self.schema_version,
                  'skill_id': self.declared_skill_id, 'product': self.product,
                  'entrypoint': self.entrypoint_file, 'sources': list(self.sources),
                  'files': list(self.files),
                  'dependencies': [dict(d) for d in self.dependencies]}
        if self.loading_file is not None:
            record['loading'] = self.loading_file
        return record

    class Records(SkwDepot.Records):
        def record_example(self):
            return self._owner(skill_id="6f1c2d3e-4b5a-4c6d-8e7f-901a2b3c4d5e",
                               product="skills/example")._to_record()


    @property
    def project(self):
        """The Project whose Skillware holds this depot."""
        depots = self.depot.parent
        project = depots.parent.parent.parent
        if project / SKILL_DEPOTS != depots:
            raise ValueError(f"A skill depot lives in <project>/{SKILL_DEPOTS}/, not {self.depot}")
        return project

    @property
    def root(self):
        """The skill folder the depot builds."""
        return _relative(self.project, self.product, "The product escapes its Project")

    @property
    def skill_id(self):
        """The skill this depot builds, as the depot names it."""
        return Ship(self.declared_skill_id)

    # tarav.breadcrumb e92c586be979
    @property
    def owner(self):
        """How a POI names this skill: by UUID, wherever its folder lies."""
        return {"skill": str(self.skill_id)}

    @property
    def entrypoint(self):
        """The file a harness loads, as the manifest names it."""
        return self.path(self.entrypoint_file)

    def _validate(self):
        """Check what the manifest's types do not; needs the skill's location."""
        if self.schema_version != 1:
            raise ValueError("Expected skill package schema 1")
        for key, values, resolve in (("sources", self.sources, self.depot_path),
                                     ("files", self.files, self.path)):
            if len(values) != len(set(values)):
                raise ValueError(f"{key} must contain unique relative paths")
            for value in values:
                resolve(value)
        if self.entrypoint_file not in self.files:
            raise ValueError("Entrypoint must be a deployed file")
        for value in self.files:
            if self.path(value).is_relative_to(self.depot):
                raise ValueError("Build surfaces cannot be deployed")
        for dependency in self.dependencies:
            purposes = dependency["purposes"]
            if (not isinstance(purposes, list) or not purposes
                    or len(set(purposes)) != len(purposes)
                    or set(purposes) - {"developer", "consumer"}):
                raise ValueError("Expected developer/consumer dependency purposes")
            if dependency["kind"] not in {"skill", "file"}:
                raise ValueError("Unknown dependency kind")
            if "consumer" in purposes and dependency["kind"] != "skill":
                raise ValueError("External consumer dependencies must be skills")
            if Path(dependency["path"]).is_absolute():
                raise ValueError("Dependency paths must be relative")

    def path(self, value):
        """A product path: a deployed file, a dependency, a context target."""
        return _relative(self.root, value, "Package path escapes root")

    def depot_path(self, value):
        """A path inside the depot: a source or the loading record."""
        return _relative(self.depot, value, "Depot path escapes the depot")

    def documents(self):
        self._validate()
        cls = SkillDocument if self.loading_file is not None else Document
        documents = [cls(self.depot_path(p), root=self.root, depot=self.depot)
                     for p in self.sources]
        if self.loading_file is not None:
            loading = SkillReadingGraph(self, documents)
            for document in documents:
                document.loading = loading
        return documents

    def _navigation_document(self, source):
        """Select one declared source, relative to .skw/src."""
        relative = Path(source)
        base = self.depot / 'src'
        if relative.is_absolute() or not (base / relative).resolve().is_relative_to(base):
            raise ValueError('--source must be relative to the depot\'s src directory')
        document = Document(base / relative, root=self.root, depot=self.depot)
        if document.key not in self.sources:
            raise ValueError('Document is not declared in skill')
        return document

    def ls(self, *, source=None, offset=0, limit=20):
        """List source paths or block IDs without loading context targets."""
        if offset < 0 or limit < 1:
            raise ValueError('offset must be nonnegative and limit positive')
        self._validate()
        if source is None:
            base = self.depot / 'src'
            items = [{'source': str(self.depot_path(p).relative_to(base)),
                      'path': str(self.depot_path(p))} for p in self.sources]
        else:
            document = self._navigation_document(source)
            items = [{'block': b.label, 'id': str(b.id), 'type': entity(type(b)).name}
                     for b in document.blocks.values()]
        end = offset + limit
        return {'total': len(items), 'items': items[offset:end],
                'next_offset': end if end < len(items) else None}

    def read_block(self, *, source, block):
        """Read one retained block; references remain unexpanded."""
        document = self._navigation_document(source)
        try:
            selected = document.block(block)
        except (KeyError, ValueError) as exc:
            raise ValueError(f'Unknown block: {block}') from exc
        return {'source': str(document.source), 'output': str(document.target),
                'block': selected.records.to_record()}

    def loading(self):
        # tarav.breadcrumb 59cbf4641ece
        return SkillReadingGraph(self, self.documents())

    # tarav.breadcrumb 2ceb31c9cf70
    # tarav.breadcrumb a751a7e31ab0
    # tarav.breadcrumb 923a65026ef7
    class Checks(CheckProvider.Checks):
        def suite(self) -> CheckSuite:
            return SkwSkillSuite(self.obj)

    # tarav.breadcrumb b0bae46a0414
    def evaluate(self):
        """The POIs of this package's suite, the same suite a Project runs."""
        collector = POICollector()
        for poi in SkwSkillSuite(self).run().pois():
            collector.emit(poi)
        return collector

    def report(self, **selection):
        return self.evaluate().report(**selection)

    def check(self):
        """The POIs of this package as it is on disk."""
        return tuple(self.evaluate().pois)

    def build(self):
        documents = self.documents()
        products = documents
        if len({d.target for d in products}) != len(products):
            raise ValueError("Duplicate outputs cannot be compiled")
        for document in documents:
            if isinstance(document, SkillDocument):
                document.text()
        for document in products:
            document.compile()
        return self.check()

    def deploy(self, destination):
        """Copy consumer files to a fresh directory; never overwrite a deployment.

        Other skills remain declared external requirements, not recursively
        copied. The receipt exposes them to deployment tooling.
        """
        destination = Path(destination).resolve()
        if destination.is_relative_to(self.root):
            raise ValueError("Deploy outside the source package")
        if destination.exists():
            raise ValueError("Deployment destination must not exist")
        findings = self.check()
        # the marker travels with every copy: a deployed copy is the same skill
        files = [(value, self.path(value).read_bytes())
                 for value in (*self.files, SKILL_JSON.as_posix())]
        destination.mkdir(parents=True)
        for value, payload in files:
            target = destination / value
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            shutil.copymode(self.path(value), target)
        return {"destination": str(destination), "files": [value for value, _ in files],
                "dependencies": [d for d in self.dependencies
                                 if "consumer" in d["purposes"]], "findings": findings}


SKILLS_RECORD_TYPES = (
    SkwDepot,
    SkwSkill,
    LoadingRecord,
    *SKILL_COMPONENT_TYPES,
    *SkwPOI.__subclasses__(),  # its atomic cases
    *SKW_CHAIN_CHECK_TYPES,
)


class SkwSkillsWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('013c95b7-57db-485a-ac88-590d05af475a'),
            name='Tarav.Workflow.SKW.Skills',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SKW_SKILLS_WORKFLOW_SHIP
    constitution = "Compile and inspect deployable SKW skills and their loading context."

    # tarav.breadcrumb c03940fca432
    @property
    def workflow(self):
        return CodeWorkflow()


def _relative(base, value, escape):
    if (not isinstance(value, str) or not value or Path(value).is_absolute()
            or ".." in Path(value).parts or Path(value).as_posix() != value
            or value == "."):
        raise ValueError("Expected package-relative path")
    target = (base / value).resolve()
    if not target.is_relative_to(base):
        raise ValueError(escape)
    return target


def project_skills(project) -> tuple[Path, ...]:
    """The skill depots a Project holds; load each with `load_depot`."""
    return tuple(sorted(main.parent for main in (Path(project) / SKILL_DEPOTS).glob("*/main.json")))


def load_depot(depot, *, registry: TypeRegistry[TaravObject]) -> SkwSkill:
    """Load one skill depot through registered Record dispatch."""
    loaded = registry.load(Path(depot))
    if not isinstance(loaded, SkwSkill):
        raise ValueError(f"Expected a registered SkwSkill depot, got {type(loaded).__name__}")
    return loaded


# tarav.breadcrumb f257a5d837fc
def load_skill(folder, *, registry: TypeRegistry[TaravObject]) -> SkwSkill:
    """The skill a folder holds, built by the depot of the Project above it."""
    folder = Path(folder).expanduser().resolve()
    project = find_agentos_project_root(folder)
    if project is None:
        raise ValueError(f"A skill belongs to a Project; no .tarav/project.json at or above {folder}")
    product = folder.relative_to(project).as_posix()
    for depot in project_skills(project):
        skill = load_depot(depot, registry=registry)
        if skill.product == product:
            return skill
    raise ValueError(f"No depot in {project / SKILL_DEPOTS} builds {product}")


# tarav.breadcrumb 6d845a3dd724
def skill_document(source, *, project=None, depot=DEFAULT_DEPOT,
                   registry: TypeRegistry[TaravObject]):
    """A document of a Project's depot; a skill depot's documents build its skill folder."""
    document = project_document(source, project=project, depot=depot, registry=registry)
    depot_path = document.depot
    try:
        entry_file(depot_path)
    except FileNotFoundError:
        return document
    package = registry.load(depot_path)
    if isinstance(package, SkwSkill):
        matches = [d for d in package.documents() if d.source == document.source]
        if len(matches) != 1:
            raise ValueError('Document is not declared in skill package')
        return matches[0]
    return document


def _skill_folder(value):
    if value is not None:
        return Path(value).expanduser().resolve()
    start = Path.cwd().resolve()
    for candidate in (start, *start.parents):
        if (candidate / SKILL_JSON).is_file():
            return candidate
    raise ValueError(f"No .tarav/skill.json at or above {start}; supply --skill")


def register_commands(subparsers, *, registry: TypeRegistry[TaravObject]):
    parser = subparsers.add_parser("skills", help="Build and deploy skill packages")
    commands = parser.add_subparsers(dest="skills_action", required=True)
    for action in ("check", "build", "deploy", "context", "poi", "ls", "read"):
        command = commands.add_parser(action)
        command.add_argument("--skill", help="The skill folder; default: the nearest one "
                             "with a .tarav/skill.json at or above the current directory.")
        if action == 'ls':
            command.add_argument('--source')
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=20)
        if action == 'read':
            command.add_argument('--source', required=True)
            command.add_argument('--block', required=True)
        if action in ('check', 'build', 'deploy'):
            command.add_argument('--offset', type=int, default=0)
            command.add_argument('--limit', type=int, default=20)
            command.add_argument('--class-name')
        if action in ('check', 'build', 'deploy', 'poi'):
            command.add_argument('--renderer',
                                 choices=tuple(item.name for item in renderers()),
                                 default=DEFAULT_POI_RENDERER)
            command.add_argument('--level', choices=('line', 'record'),
                                 default='record' if action == 'poi' else 'line')
        if action == 'poi':
            command.add_argument('--id', required=True, help='Full finding ID or unique prefix')
            command.add_argument('--index', type=int, help='Emission index when an ID repeats')
        if action == "deploy":
            command.add_argument("--destination", required=True)
        if action == 'context':
            command.add_argument('--block', required=True)
            command.add_argument('--limit', type=int, default=5)
        add_output_mode(command)
        command.set_defaults(handler=_command, skw_registry=registry)


def _command(args):
    try:
        folder = _skill_folder(args.skill)
        package = load_skill(folder, registry=args.skw_registry)
    except (OSError, ValueError, TypeError) as exc:
        raise CliError(f'Cannot load skill: {exc}') from exc
    if args.skills_action == 'ls':
        result = package.ls(source=args.source, offset=args.offset, limit=args.limit)
        emit(args, result, render_skill_listing)
        return 0
    if args.skills_action == 'read':
        result = package.read_block(source=args.source, block=args.block)
        emit(args, result, render_skill_block)
        return 0
    if args.skills_action == 'context':
        if args.limit < 1:
            raise ValueError('limit must be positive')
        result = package.loading().inspect(args.block, limit=args.limit)
        emit(args, result, render_loading_context)
        return 0
    if args.skills_action == 'poi':
        collector = package.evaluate()
        poi = collector.get(args.id, index=args.index)
        result = poi.records.to_record()
        if args.index is not None:
            result['index'] = args.index
        emit(args, result, lambda value: render_poi(
            value, renderer_name=args.renderer, level=args.level))
        return 0
    result = (package.deploy(args.destination) if args.skills_action == "deploy"
              else getattr(package, args.skills_action)())
    findings = result.get("findings", []) if isinstance(result, dict) else result
    collector = package.evaluate()
    # a skill package is not a Project: its POIs are only shown here. They get
    # actions when the Project that holds the package runs its status.
    report = collector.report(offset=args.offset, limit=args.limit,
                              class_name=args.class_name)
    if isinstance(result, dict):
        result['findings'] = report
    else:
        result = report
    emit(
        args,
        result,
        lambda value: render_skill_operation(
            args.skills_action, value, renderer_name=args.renderer, level=args.level),
    )
    # Blessing does not turn the detector result into a pass. Callers decide
    # which findings matter to their workflow independently of presentation.
    return 1 if findings else 0
