"""Repeated CLI --view options apply the same ordered Context qualifications."""

import argparse
import json

import pytest

from tarav.l0._core.errors import CliError
from tarav.l0.kernel import FileRecord, TaravClass, TaravObject, TypeShip
from tarav.l1.context import ContextFolder
from tarav.l1.context.query import ContextQueryService, IdentityContextQuery, TypeResolver
from tarav.l3.context.commands import register_context_command


class First(ContextFolder):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f30000-0000-4000-8000-000000000001"),
                          name="Test.Context.First")

    @classmethod
    def accepts(cls, scope):
        return not scope.views and scope.subject is TaravObject

    @classmethod
    def for_context(cls, current):
        return cls(current.subject, lambda builder: builder.add("first", opener=FileRecord))


class Second(ContextFolder):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f30000-0000-4000-8000-000000000002"),
                          name="Test.Context.Second")

    @classmethod
    def accepts(cls, scope):
        return scope.subject is TaravObject and scope.views == (First,)

    @classmethod
    def for_context(cls, current):
        return cls(current.subject, lambda builder: builder.add("result", opener=FileRecord))


def command(arguments):
    service = ContextQueryService()
    service.register_resolver("types", TypeResolver(lambda: (TaravObject,)))
    service.register_view("first", First)
    service.register_view("second", Second)
    parser = argparse.ArgumentParser()
    register_context_command(parser.add_subparsers(), service=service)
    return parser.parse_args(["context", "--id", "Tarav.Object", *arguments])


# tarav.context 473c89a0:4c4bb8bf8f117d07
def test_repeated_views_are_ordered_and_the_listing_exposes_entry_types(capsys):
    args = command(["--view", "first", "--view", "second", "--json"])
    assert args.handler(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["selected_views"] == ["first", "second"]
    assert value["views"] == []
    assert [view["type"] for view in value["qualifications"]] == ["Test.Context.First", "Test.Context.Second"]
    assert value["entries"] == [{"name": "result", "type": "Tarav.Context.Entry", "description": None}]


def test_unsupported_order_is_an_explicit_cli_error():
    args = command(["--view", "second", "--view", "first"])
    with pytest.raises(CliError, match="Second does not support"):
        args.handler(args)


def test_available_next_views_respect_current_qualifications(capsys):
    args = command(["--view", "first", "--json"])
    assert args.handler(args) == 0
    value = json.loads(capsys.readouterr().out)
    assert value["selected_views"] == ["first"]
    assert value["views"] == ["second"]


def test_repeated_path_labels_still_enter_a_nodes_context_between_steps():
    class RepeatedPath(TaravObject):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("b1f30000-0000-4000-8000-000000000003"),
                              name="Test.Context.RepeatedPath")

        @classmethod
        def class_context(cls, builder):
            builder.add("same", opener=cls)

        def obj_context(self, builder):
            builder.add("same", opener=FileRecord)

    service = ContextQueryService()
    service.register_resolver("types", TypeResolver(lambda: (RepeatedPath,)))
    answer = service.open(IdentityContextQuery("Test.Context.RepeatedPath", path=("same", "same")))
    assert answer.location == ("same", "same")
    assert type(answer.target) is FileRecord
