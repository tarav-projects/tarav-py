"""Explicit skill-package compilation and consumer deployment."""
import json
import re
import shutil
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tarav.harness import FileRecord, TypeShip
from tarav.harness.workflows import Workflow
from tarav.skillware.document import Document, project_document, project_root, read
from .publication import ModelPublication, ModelPublicationRecord, PublicationLockRecord
from .loading import LoadingModel, LoadingRecord, SkillDocument


class SkillPackageRecord(FileRecord):
    type_name = "Tarav.Skillware.SkillPackage"
    type_ship = TypeShip("1b456d93-9d24-40df-a4a6-f1d0470ec949")


class SkillsWorkflow(Workflow):
    name = "skw.skills"
    record_types = (SkillPackageRecord, ModelPublicationRecord, PublicationLockRecord, LoadingRecord)


class SkillPackage:
    """A manifest owns deployment selection; source context stays developer-only.

    Dependency purposes are independent of document context roles. Build and
    check never accept context baselines or regenerate agent-authored content.
    """

    def __init__(self, root):
        self.root = Path(root).resolve()
        self.data = read(self.root / ".skw" / "skill.json")
        if (self.data.get("type") != SkillPackageRecord.type_name
                or self.data.get("schema_version") != 1):
            raise ValueError("Expected skill package schema 1")
        for key in ("sources", "files"):
            values = self.data[key]
            if not isinstance(values, list) or len(values) != len(set(values)):
                raise ValueError(f"{key} must contain unique relative paths")
            for value in values:
                self.path(value)
        if self.data["entrypoint"] not in self.data["files"]:
            raise ValueError("Entrypoint must be a deployed file")
        for value in self.data["files"]:
            if self.path(value).is_relative_to(self.root / ".skw"):
                raise ValueError("Build surfaces cannot be deployed")
        for dependency in self.data.get("dependencies", []):
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

    def loading(self):
        if 'loading' not in self.data:
            raise ValueError('Package has no declared loading model')
        return LoadingModel(self, self.documents())

    def publications(self):
        return [ModelPublication(self.path(p), root=self.root)
                for p in self.data.get('publications', [])]

    def check(self):
        findings = []
        def report(kind, path, detail=""):
            findings.append({"kind": kind, "path": str(path), "detail": detail})
        outputs = set()
        try:
            documents = {d.source: d for d in self.documents()}
            if 'loading' in self.data:
                findings.extend(self.loading().analyze()['findings'])
        except (OSError, ValueError, KeyError, TypeError) as exc:
            report('invalid-loading-model', self.root, str(exc))
            return findings
        for source in self.data.get('publications', []):
            try:
                publication = ModelPublication(self.path(source), root=self.root)
                if publication.target in outputs:
                    report('duplicate-output', publication.target)
                outputs.add(publication.target)
                if publication.target not in {self.path(p) for p in self.data['files']}:
                    report('output-not-deployed', publication.target)
                findings.extend({**f, 'path': source} for f in publication.check())
            except (OSError, ValueError, KeyError, TypeError) as exc:
                report('invalid-publication', source, str(exc))
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
        publications = self.publications()
        products = [*publications, *documents]
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


def skill_document(source, *, project=None):
    document = project_document(source, project=project)
    if (document.root / '.skw/skill.json').exists():
        package = SkillPackage(document.root)
        if 'loading' in package.data:
            matches = [d for d in package.documents() if d.source == document.source]
            if len(matches) != 1:
                raise ValueError('Document is not declared in skill package')
            return matches[0]
    return document


def register_commands(subparsers):
    parser = subparsers.add_parser("skills", help="Build and deploy skill packages")
    commands = parser.add_subparsers(dest="skills_action", required=True)
    for action in ("check", "build", "deploy", "context"):
        command = commands.add_parser(action)
        command.add_argument("--project")
        if action == "deploy":
            command.add_argument("--destination", required=True)
        if action == 'context':
            command.add_argument('--block', required=True)
            command.add_argument('--limit', type=int, default=5)
        command.set_defaults(handler=_command)


def _command(args):
    package = SkillPackage(project_root(args.project))
    if args.skills_action == 'context':
        if args.limit < 1:
            raise ValueError('limit must be positive')
        print(json.dumps(package.loading().inspect(args.block, limit=args.limit), indent=2))
        return 0
    result = (package.deploy(args.destination) if args.skills_action == "deploy"
              else getattr(package, args.skills_action)())
    print(json.dumps(result, indent=2))
    findings = result.get("findings", []) if isinstance(result, dict) else result
    return 1 if findings else 0
