"""Cumulative Context qualification through direct requests and typed steps."""

import pytest

from tarav.l0.kernel import TaravClass, TaravObject, TypeShip
from tarav.l1.context import (
    ContextEntry, ContextExplorer, ContextFolder, ContextList, ContextView, ContextViewEntry,
    ContextViewRequest, UnsupportedContextView, explore,
)


class Item(TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000001"),
                          name="Test.ContextViews.Item")

    def __init__(self, name, author):
        super().__init__()
        self.name, self.author = name, author


class Collection(TaravObject):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000002"),
                          name="Test.ContextViews.Collection")

    def __init__(self):
        super().__init__()
        self.items = (Item("a", "alice"), Item("b", "bob"), Item("c", "alice"))
        self.view_openings = 0

    def obj_context(self, builder):
        builder.add_view("items", views=(ItemsView,))
        builder.add("direct", opener=lambda: self.items[0])


class ItemsView(ContextFolder):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000003"),
                          name="Test.ContextViews.Items")

    @classmethod
    def accepts(cls, scope):
        return not scope.views and isinstance(scope.subject, Collection)

    @classmethod
    def for_context(cls, current):
        subject = current.subject
        subject.view_openings += 1

        def populate(builder):
            for item in subject.items:
                builder.add(item.name, opener=lambda item=item: item)
            builder.add_view("by-alice", views=(ByAuthor("alice"),))
            builder.add("group", opener=lambda: ContextFolder(subject, lambda nested:
                nested.add("a", opener=lambda: subject.items[0])))

        return cls(subject, populate)


class ByAuthor(ContextViewRequest):
    @classmethod
    def class_entity(cls):
        return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000004"),
                          name="Test.ContextViews.ByAuthor")

    class RecordInterface(ContextViewRequest.RecordInterface):
        author: str

    def __init__(self, author):
        super().__init__()
        self.author = author

    def _to_record(self):
        return {**super()._to_record(), "author": self.author}

    def apply(self, current):

        def populate(builder):
            for entry in current.ls():
                if isinstance(entry, ContextViewEntry):
                    continue
                value = entry.open()
                if isinstance(value, Item) and value.author == self.author:
                    builder.add_entry(entry)

        return ContextFolder(current.subject, populate)

    def accepts(self, scope):
        return bool(scope.views) and scope.views[0] is ItemsView and not any(
            isinstance(view, ByAuthor) and view.author == self.author for view in scope.views
        )


# tarav.context 473c89a0:3cae519d8e79ad5b
def test_ordered_class_and_parameterized_views_keep_subject_and_all_qualifications():
    subject = Collection()
    request = ByAuthor("alice")
    view = explore(subject, views=(ItemsView, request))
    assert isinstance(view, ContextView)
    assert view.subject is subject
    assert view.context_scope.subject is subject
    assert view.context_scope.views == (ItemsView, request)
    assert [entry.name for entry in view.ls()] == ["a", "c"]
    assert view.open("a") is subject.items[0]


# tarav.context 473c89a0:9b167562b00b0279
def test_listing_is_lazy_and_direct_and_entry_paths_share_qualification_semantics():
    subject = Collection()
    root = explore(subject)
    step = root.get("items")
    assert isinstance(step, ContextViewEntry)
    assert subject.view_openings == 0
    by_path = step.open().open("by-alice")
    by_request = explore(subject, views=(ItemsView, ByAuthor("alice")))
    assert [entry.name for entry in by_path.ls()] == ["a", "c"]
    assert [entry.name for entry in by_request.ls()] == ["a", "c"]
    assert by_path.context_scope.views[0] is ItemsView
    assert by_path.context_scope.views[1].records.to_record() == {
        "type": "Test.ContextViews.ByAuthor", "author": "alice"
    }
    assert root.open("direct") is by_path.open("a")
    assert root.pwd() == "/"
    assert root.context_scope.views == ()


def test_generic_grouping_preserves_active_scope_and_bound_entries_are_independent():
    subject = Collection()
    view = explore(subject, views=(ItemsView,))
    grouped = view.open("group")
    assert grouped.context_scope.views == (ItemsView,)
    assert grouped.open("a") is subject.items[0]
    first, second = explore(subject), explore(subject)
    held = first.get("items")
    first.follow(held)
    assert first.context_scope.views == (ItemsView,)
    assert second.context_scope.views == ()
    assert first.back().context_scope.views == ()
    assert first.forward().context_scope.views == (ItemsView,)


def test_refinements_preserve_earlier_constraints_even_when_the_result_is_empty():
    subject = Collection()
    alice, bob = ByAuthor("alice"), ByAuthor("bob")
    first = explore(subject, views=(ItemsView, alice))
    second = first.refine(views=(bob,))
    assert second.context_scope.views == (ItemsView, alice, bob)
    assert second.ls() == ()
    assert [entry.name for entry in first.ls()] == ["a", "c"]


def test_unsupported_combinations_are_not_dropped_or_reinterpreted():
    subject = Collection()
    with pytest.raises(UnsupportedContextView, match="ByAuthor does not support"):
        explore(subject, views=(ByAuthor("alice"),))
    with pytest.raises(UnsupportedContextView, match="ItemsView does not support"):
        explore(subject, views=(ItemsView, ItemsView))


@pytest.mark.parametrize("views", ["items", ItemsView, (object,), (object(),)])
def test_invalid_selectors_are_rejected_at_the_boundary(views):
    with pytest.raises(TypeError):
        explore(Collection(), views=views)


def test_a_new_subject_has_a_fresh_scope_and_explorer_keeps_the_incoming_route():
    subject = Collection()
    root = explore(subject)
    root.follow(root.get("items"))
    assert root.context_scope.views == (ItemsView,)
    root.follow(root.get("a"))
    assert root.subject is subject.items[0]
    assert root.context_scope.views == ()
    root.back()
    assert root.subject is subject
    assert root.context_scope.views == (ItemsView,)


def test_view_scope_is_frozen_and_factories_cannot_silently_change_subject():
    from dataclasses import FrozenInstanceError

    subject = Collection()
    with pytest.raises(FrozenInstanceError):
        explore(subject).context_scope.views = (ItemsView,)

    class ChangesSubject(ContextViewRequest):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000005"),
                              name="Test.ContextViews.ChangesSubject")

        def apply(self, current):
            return ContextFolder(current.subject.items[0], lambda builder: None)

        def accepts(self, scope):
            return True

    with pytest.raises(UnsupportedContextView, match="change its subject"):
        explore(subject, views=(ChangesSubject(),))


def test_default_exploration_and_plain_entries_remain_valid():
    subject = Collection()
    assert isinstance(explore(subject), ContextExplorer)
    assert isinstance(explore(subject).get("direct"), ContextEntry)
    assert explore(subject).open("direct") is subject.items[0]
    with pytest.raises(TypeError):
        explore(subject, type=ItemsView)


def test_namespace_and_runtime_registry_offer_supported_steps_without_opening_them(tmp_path):
    from tarav.l3.runtime import create_runtime, get_runtime, set_runtime

    old = get_runtime()
    runtime = create_runtime(archive_root=tmp_path / "archive")
    runtime.contexts.register_view("all-items", ItemsView)
    runtime.contexts.register_view("alice-filter", ByAuthor("alice"))
    set_runtime(runtime)
    try:
        subject = Collection()
        root = subject.context()
        assert [entry.name for entry in root.ls()] == ["class", "items", "direct", "all-items"]
        assert subject.view_openings == 0
        items = root.open("all-items")
        assert isinstance(items.get("alice-filter"), ContextViewEntry)
        assert [entry.name for entry in items.open("alice-filter").ls()] == ["a", "c"]
        by_path = root.open("all-items").open("by-alice")
        by_request = subject.context(views=(ItemsView, ByAuthor("alice")))
        assert [entry.name for entry in by_path.ls()] == ["a", "c"]
        assert [entry.name for entry in by_request.ls()] == ["a", "c"]
        assert not runtime.contexts.archive_root.exists()
    finally:
        set_runtime(old)


def test_a_registered_view_must_advertise_explicit_compatibility():
    class Unspecified(ContextFolder):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000006"),
                              name="Test.ContextViews.Unspecified")

        @classmethod
        def for_context(cls, current):
            raise AssertionError("The factory must not run without accepting its input")

    with pytest.raises(UnsupportedContextView):
        explore(Collection(), views=(Unspecified,))


def test_listing_omits_unsupported_next_steps_without_running_factories():
    subject = Collection()

    def populate(builder):
        builder.add_view("wrong-order", views=(ByAuthor("alice"), ItemsView))
        builder.add_view("supported-chain", views=(ItemsView, ByAuthor("alice")))

    root = ContextFolder(subject, populate)
    assert [entry.name for entry in root.ls()] == ["supported-chain"]
    assert subject.view_openings == 0
    result = root.open("supported-chain")
    assert [entry.name for entry in result.ls()] == ["a", "c"]


def test_reusing_a_relationship_in_a_new_view_does_not_import_an_old_explorer_route():
    subject = Collection()
    original = explore(subject).get("direct")
    view = ContextFolder(subject, lambda builder: builder.add_entry(original))
    copied = view.get("direct")
    assert original.explorer is not None
    assert copied.explorer is None
    assert copied.open() is original.open()


def test_registered_steps_use_positions_inside_list_views(tmp_path):
    from tarav.l3.runtime import create_runtime, get_runtime, set_runtime

    class Positional(Collection):
        @classmethod
        def class_entity(cls):
            return TaravClass(target=cls, id=TypeShip("b1f10000-0000-4000-8000-000000000007"),
                              name="Test.ContextViews.Positional")

        def obj_context(self, builder):
            builder.add("list", opener=lambda: ContextList(self, lambda nested:
                nested.add(0, opener=lambda: self.items[0])))

    old = get_runtime()
    runtime = create_runtime(archive_root=tmp_path / "archive")
    runtime.contexts.register_view("all-items", ItemsView)
    set_runtime(runtime)
    try:
        view = Positional().context().open("list")
        assert [entry.placement for entry in view.ls()] == [0, 1]
        assert isinstance(view.get(1), ContextViewEntry)
        assert view.get(1).description == "all-items"
        assert view.open(1).context_scope.views == (ItemsView,)
    finally:
        set_runtime(old)
