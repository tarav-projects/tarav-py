"""Explicit skill-package compilation and consumer deployment."""
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tarav.l0.kernel import TaravClass, entity
from tarav.l0.kernel import TaravObject, TypeRegistry, TypeShip
from tarav.l0.kernel.records import entry_file
from tarav.l0.kernel.workflows import TaravWorkflow
from tarav.l1.skw.identity import SKW_SKILLS_WORKFLOW_SHIP
from tarav.l1.skw.depot import SkwDepot
from tarav.l1.skw.document import Document, project_document, project_root, read
from .publication import ModelPublication, ModelPublicationRecord, PublicationLockRecord
from tarav.l1.skw.loading import LoadingModel, LoadingRecord, SkillDocument
from tarav.l1.skw.skills import SKILL_COMPONENT_TYPES
from tarav.l1.blessings import BlessingAssessmentRecord, BlessingRecord, BlessingStore
from tarav.l1.checks import CheckProvider, run_checks
from tarav.l0._core.errors import CliError
from .pois import CLASSES, DiagramAssessment, SkwAnalysisCheck, collect
from .reading_checks import READING_CHECK_TYPES, reading_checks
from tarav.l1.skw.presentation import (
    add_output_mode,
    emit,
    render_blessing_record,
    render_loading_context,
    render_poi,
    render_skill_block,
    render_skill_listing,
    render_skill_operation,
)


class SkwSkill(SkwDepot, CheckProvider):
    """A deployable Skill retained in one typed `.skw` depot.

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

    @property
    def data(self):
        """Validated Skill manifest, after Harness has attached its source."""

        self._validate()
        if self._record is None:
            raise RuntimeError("Skill package has no loaded Record")
        return self._record

    def _validate(self):
        if self._record is None:
            raise RuntimeError("Skill package has no loaded Record")
        data = self._record
        if data.get("schema_version") != 1:
            raise ValueError("Expected skill package schema 1")
        for key in ("sources", "files"):
            values = data[key]
            if not isinstance(values, list) or len(values) != len(set(values)):
                raise ValueError(f"{key} must contain unique relative paths")
            for value in values:
                self.path(value)
        if data["entrypoint"] not in data["files"]:
            raise ValueError("Entrypoint must be a deployed file")
        for value in data["files"]:
            if self.path(value).is_relative_to(self.depot):
                raise ValueError("Build surfaces cannot be deployed")
        for dependency in data.get("dependencies", []):
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
        if (not isinstance(value, str) or not value or Path(value).is_absolute()
                or ".." in Path(value).parts or Path(value).as_posix() != value
                or value == "."):
            raise ValueError("Expected package-relative path")
        target = (self.root / value).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Package path escapes root")
        return target

    def documents(self):
        cls = SkillDocument if 'loading' in self.data else Document
        documents = [cls(self.path(p), root=self.root) for p in self.data['sources']]
        if 'loading' in self.data:
            loading = LoadingModel(self, documents)
            for document in documents:
                document.loading = loading
        return documents

    def _navigation_document(self, source):
        """Select one declared source, relative to .skw/src."""
        document = project_document(source, project=self.root)
        if document.key not in self.data['sources']:
            raise ValueError('Document is not declared in skill')
        return document

    def ls(self, *, source=None, offset=0, limit=20):
        """List source paths or block IDs without loading context targets."""
        if offset < 0 or limit < 1:
            raise ValueError('offset must be nonnegative and limit positive')
        if source is None:
            base = self.depot / 'src'
            items = [{'source': str(self.path(p).relative_to(base)),
                      'path': str(self.path(p))} for p in self.data['sources']]
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
                'block': selected.to_record()}

    def loading(self):
        # tarav.breadcrumb 59cbf4641ecead3861c7589cc4925175b947f7cbb3c2df4adbb1eabef3901e5e
        return LoadingModel(self, self.documents())

    @property
    def blessings(self):
        return BlessingStore(self.root / '.skw/blessings')

    # tarav.breadcrumb 2ceb31c9cf7073c74811cdb0fa857cc9cf09d51c80b4c776c5785c49bd3e1691
    @property
    def checks(self):
        return reading_checks(self.loading())

    def evaluate(self):
        findings = self._check_without_reading()
        collector = collect(self, findings)
        if not any(finding['kind'] == 'invalid-loading-model' for finding in findings):
            for result in run_checks(self.checks):
                for poi in result.pois():
                    collector.emit(poi)
        return collector

    def report(self, **selection):
        return self.evaluate().report(store=self.blessings, **selection)

    def publications(self):
        return [ModelPublication(self.path(p), root=self.root)
                for p in self.data.get('publications', [])]

    def check(self):
        findings = self._check_without_reading()
        if self._record is not None and not any(
            finding['kind'] == 'invalid-loading-model' for finding in findings
        ):
            for result in run_checks(self.checks):
                findings.extend(poi.evidence['finding'] for poi in result.pois())
        return findings

    def _check_without_reading(self):
        findings = []
        def report(kind, path, detail=""):
            findings.append({"kind": kind, "path": str(path), "detail": detail})
        outputs = set()
        try:
            documents = {d.source: d for d in self.documents()}
            self.loading()
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report('invalid-loading-model', self.root, str(exc))
            return findings
        for source in self.data.get('publications', []):
            report('model-publication-disconnected', source,
                   'Models publication is disconnected pending redesign.')
        for source in self.data["sources"]:
            try:
                document = documents[self.path(source)]
                if isinstance(document, SkillDocument):
                    document.text()
                if document.target in outputs:
                    report("duplicate-output", document.target)
                outputs.add(document.target)
                if document.target not in {self.path(p) for p in self.data["files"]}:
                    report("output-not-deployed", document.target)
                for finding in document.lint():
                    findings.append({**finding, "path": source})
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report("invalid-source", source, str(exc))
        for value in self.data["files"]:
            if not self.path(value).is_file():
                report("missing-consumer-file", value)
            elif value.endswith(".md"):
                # Output conformance only: never contributes loading edges.
                for link in re.findall(r"\]\(([^\s)]+)\)", self.path(value).read_text()):
                    parts = urlsplit(link.strip("<>"))
                    if parts.scheme or parts.netloc or not parts.path:
                        continue
                    target = (self.path(value).parent / unquote(parts.path)).resolve()
                    if target.is_relative_to(self.root):
                        if target not in {self.path(p) for p in self.data["files"]}:
                            report("unbundled-link", value, link)
                    else:
                        owners = [(self.root / d["path"]).resolve()
                                  for d in self.data.get("dependencies", [])
                                  if d["kind"] == "skill" and "consumer" in d["purposes"]]
                        if not any(target.is_relative_to(owner) for owner in owners):
                            report("undeclared-consumer-link", value, link)
                    if not target.is_file():
                        report("missing-link-target", value, link)
        for dependency in self.data.get("dependencies", []):
            target = (self.root / dependency["path"]).resolve()
            if dependency["kind"] == "skill":
                target /= "SKILL.md"
            if not target.is_file():
                report("missing-dependency", target, ",".join(dependency["purposes"]))
        return findings

    def build(self):
        documents = self.documents()
        # Model publications are not automatically executed during package builds.
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
        files = [(value, self.path(value).read_bytes()) for value in self.data["files"]]
        destination.mkdir(parents=True)
        for value, payload in files:
            target = destination / value
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            shutil.copymode(self.path(value), target)
        return {"destination": str(destination), "files": self.data["files"],
                "dependencies": [d for d in self.data.get("dependencies", [])
                                 if "consumer" in d["purposes"]], "findings": findings}


SKILLS_RECORD_TYPES = (
    SkwDepot,
    SkwSkill,
    ModelPublicationRecord,
    PublicationLockRecord,
    LoadingRecord,
    *SKILL_COMPONENT_TYPES,
    BlessingRecord,
    BlessingAssessmentRecord,
    *CLASSES.values(),
    *READING_CHECK_TYPES,
    SkwAnalysisCheck,
    DiagramAssessment,
)


class SkillsWorkflow(TaravWorkflow):
    @classmethod
    def class_entity(cls) -> TaravClass:
        return TaravClass(
            target=cls,
            id=TypeShip('013c95b7-57db-485a-ac88-590d05af475a'),
            name='Tarav.Workflow.SKWSkills',
            workflow=SKW_SKILLS_WORKFLOW_SHIP,
        )

    @classmethod
    def _workflow_id(cls):
        return SKW_SKILLS_WORKFLOW_SHIP
    workflow_name = "skw.skills"
    constitution = "Compile and inspect deployable SKW skills and their loading context."


def load_skill(root, *, registry: TypeRegistry[TaravObject]) -> SkwSkill:
    """Load a Skill depot through registered Record dispatch."""

    depot = registry.load(Path(root) / ".skw")
    if not isinstance(depot, SkwSkill):
        raise ValueError(f"Expected a registered SkwSkill depot, got {type(depot).__name__}")
    return depot


def skill_document(source, *, project=None, registry: TypeRegistry[TaravObject]):
    document = project_document(source, project=project, registry=registry)
    depot = document.root / '.skw'
    try:
        entry_file(depot)
    except FileNotFoundError:
        return document
    package = registry.load(depot)
    if isinstance(package, SkwSkill) and 'loading' in package.data:
        matches = [d for d in package.documents() if d.source == document.source]
        if len(matches) != 1:
            raise ValueError('Document is not declared in skill package')
        return matches[0]
    return document


def register_commands(subparsers, *, registry: TypeRegistry[TaravObject]):
    parser = subparsers.add_parser("skills", help="Build and deploy skill packages")
    commands = parser.add_subparsers(dest="skills_action", required=True)
    for action in ("check", "build", "deploy", "context", "poi", "bless", "assess-blessing", "ls", "read"):
        command = commands.add_parser(action)
        command.add_argument("--project")
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
            command.add_argument(
                '--blessing-status', choices=['unblessed', 'blessed']
            )
        if action in ('poi', 'bless'):
            command.add_argument('--id', required=True, help='Full finding ID or unique prefix')
            command.add_argument('--index', type=int, help='Emission index when an ID repeats')
        if action in ('bless', 'assess-blessing'):
            command.add_argument('--actor-file', required=True, help='JSON typed actor reference')
            command.add_argument('--rationale-file', required=True, help='Authored rationale text')
            command.add_argument('--support-file', help='JSON array of typed evidence references')
        if action == 'assess-blessing':
            command.add_argument('--blessing-id', required=True)
            command.add_argument('--assertion', required=True)
            command.add_argument('--score', type=float, required=True)
        if action == "deploy":
            command.add_argument("--destination", required=True)
        if action == 'context':
            command.add_argument('--block', required=True)
            command.add_argument('--limit', type=int, default=5)
        add_output_mode(command)
        command.set_defaults(handler=_command, skw_registry=registry)


def _command(args):
    try:
        root = project_root(args.project)
    except ValueError as exc:
        raise CliError(str(exc)) from exc
    try:
        entry_file(root / '.skw')
    except FileNotFoundError as exc:
        raise CliError(
            f'Found {root / ".skw"}, but it has no typed entry record. '
            'A legacy skw.json is not a skill declaration. '
            'Use --project <skill-directory> to select a skill with a typed '
            '.skw/main.json.'
        ) from exc
    try:
        package = load_skill(root, registry=args.skw_registry)
    except (OSError, ValueError, TypeError) as exc:
        raise CliError(f'Cannot load skill at {root}: {exc}') from exc
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
    if args.skills_action in ('bless', 'assess-blessing'):
        options = {'actor': read(Path(args.actor_file)),
                   'rationale': Path(args.rationale_file).read_text(),
                   'support': read(Path(args.support_file)) if args.support_file else []}
        if args.skills_action == 'bless':
            result = package.blessings.bless(
                package.evaluate().get(args.id, index=args.index), **options
            )
        else:
            result = package.blessings.assess(args.blessing_id, assertion=args.assertion,
                                             score=args.score, **options)
        emit(args, result, render_blessing_record)
        return 0
    if args.skills_action == 'poi':
        finding = package.evaluate().get(args.id, index=args.index)
        result = finding.as_dict(detail=True)
        if args.index is not None:
            result['index'] = args.index
        if package.blessings.accepts(finding):
            result['blessing'] = package.blessings.standing(finding)
            result['blessing_records'] = [
                record for record in package.blessings.snapshot()['records']
                if record['id'] in result['blessing']['records']
                or record.get('blessing') in result['blessing']['records']
            ]
        emit(args, result, render_poi)
        return 0
    result = (package.deploy(args.destination) if args.skills_action == "deploy"
              else getattr(package, args.skills_action)())
    findings = result.get("findings", []) if isinstance(result, dict) else result
    report = package.evaluate().report(
        store=package.blessings, offset=args.offset, limit=args.limit,
        class_name=args.class_name, blessing=args.blessing_status)
    if isinstance(result, dict):
        result['findings'] = report
    else:
        result = report
    emit(
        args,
        result,
        lambda value: render_skill_operation(args.skills_action, value),
    )
    # Blessing does not turn the detector result into a pass. Callers decide
    # which findings matter to their workflow independently of presentation.
    return 1 if findings or report['store_findings'] else 0
