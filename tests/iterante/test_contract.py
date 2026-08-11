"""Tests for the typed submit contract validator (iterante.contract)."""

import pytest

from agentos.iterante.contract import ContractError, validate


class TestNoPayload:
    def test_none_accepts_none(self):
        validate(None, None)  # no raise

    def test_none_accepts_empty_dict(self):
        validate(None, {})  # no raise

    def test_none_rejects_answer(self):
        with pytest.raises(ContractError, match="no payload"):
            validate(None, {"answer": "x"})

    def test_none_rejects_data(self):
        with pytest.raises(ContractError, match="no payload"):
            validate(None, {"data": {"k": 1}})


class TestTypeMarkers:
    def test_bool_match(self):
        validate({"answer": "bool"}, {"answer": True})

    def test_bool_mismatch(self):
        with pytest.raises(ContractError, match="bool"):
            validate({"answer": "bool"}, {"answer": "yes"})

    def test_str_match(self):
        validate({"answer": "str"}, {"answer": "hello"})

    def test_str_mismatch(self):
        with pytest.raises(ContractError, match="str"):
            validate({"answer": "str"}, {"answer": 3})

    def test_int_match(self):
        validate({"answer": "int"}, {"answer": 5})

    def test_int_rejects_bool(self):
        with pytest.raises(ContractError, match="int"):
            validate({"answer": "int"}, {"answer": True})

    def test_float_accepts_int_and_float(self):
        validate({"answer": "float"}, {"answer": 5})
        validate({"answer": "float"}, {"answer": 5.0})


class TestEnum:
    def test_member_accepted(self):
        validate({"answer": ["yes", "no"]}, {"answer": "yes"})

    def test_non_member_rejected(self):
        with pytest.raises(ContractError, match="one of"):
            validate({"answer": ["yes", "no"]}, {"answer": "maybe"})


class TestRequiredAndUnknown:
    def test_missing_required_field(self):
        with pytest.raises(ContractError, match="missing"):
            validate({"answer": "str"}, {})

    def test_unknown_field_rejected(self):
        with pytest.raises(ContractError, match="unexpected"):
            validate({"answer": "str"}, {"answer": "ok", "extra": 1})

    def test_non_dict_submit_for_object_schema(self):
        with pytest.raises(ContractError):
            validate({"answer": "str"}, "not a dict")


class TestNestedData:
    def test_nested_object_match(self):
        validate(
            {"data": {"name": "str", "count": "int"}},
            {"data": {"name": "x", "count": 2}},
        )

    def test_nested_object_field_mismatch(self):
        with pytest.raises(ContractError, match="count"):
            validate(
                {"data": {"name": "str", "count": "int"}},
                {"data": {"name": "x", "count": "two"}},
            )

    def test_nested_object_unknown_field(self):
        with pytest.raises(ContractError, match="unexpected"):
            validate({"data": {"name": "str"}}, {"data": {"name": "x", "y": 1}})
