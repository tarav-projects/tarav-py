from __future__ import annotations

import argparse

from tarav.breadcrumbs import (
    BreadcrumbAnnotationWorkflow,
    BreadcrumbAuditFinding,
    BreadcrumbCommandAdapter,
    BreadcrumbIntegration,
)
from tarav.cli.cli import build_parser
from tarav.runtime import create_runtime


class _Workflow(BreadcrumbAnnotationWorkflow):
    name = "example-integration"

    def prepare(self, surface, request):
        return ()

    def attachments(self, annotation, breadcrumb_id):
        return ()

    def audit(self, context, request):
        return (BreadcrumbAuditFinding("example", "example integration audit"),)


class _Commands(BreadcrumbCommandAdapter):
    def register_submit(self, subparsers, workflow):
        parser = subparsers.add_parser(workflow.name)
        parser.set_defaults(handler=lambda _args: 0)

    def register_audit(self, subparsers, workflow):
        parser = subparsers.add_parser(workflow.name)
        parser.set_defaults(handler=lambda _args: 1)


def test_one_integration_bundle_registers_workflow_and_both_commands():
    integration = BreadcrumbIntegration(_Workflow(), _Commands())
    runtime = create_runtime(breadcrumb_integrations=(integration,))

    assert (
        runtime.breadcrumbs.annotations.resolve("example-integration")
        is integration.workflow
    )
    assert integration in runtime.breadcrumb_integrations

    parser = build_parser(runtime=runtime)
    submitted = parser.parse_args(["breadcrumbs", "submit", "example-integration"])
    audited = parser.parse_args(["breadcrumbs", "audit", "example-integration"])
    assert isinstance(submitted, argparse.Namespace)
    assert submitted.handler(submitted) == 0
    assert audited.handler(audited) == 1
