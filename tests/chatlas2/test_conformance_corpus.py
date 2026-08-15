from __future__ import annotations

from pathlib import Path

from tarav.chatlas2.corpus import check_corpus, load_script_spec, verify_corpus


CORPUS = Path(__file__).parent / "conformance"


def test_committed_corpus_is_complete_and_hermetic() -> None:
    assert verify_corpus(CORPUS) == {
        "artifact_count": 21,
        "capture_count": 21,
        "status": "ok",
    }
    specifications = sorted((CORPUS / "specifications").glob("*.json"))
    assert len([load_script_spec(path) for path in specifications]) == 5

    result = check_corpus(CORPUS)

    assert result["status"] == "ok"
    assert result["capture_count"] == 21
    assert result["passed_count"] == 10
    assert result["unsupported_count"] == 11
    assert result["failed_count"] == 0
