from __future__ import annotations

from agentos.chatlas.delta_scan import _emit_update_summary


def test_update_progress_summary_places_total_last_and_formats_blocks() -> None:
    messages: list[str] = []
    payload = {
        "native_scan": {
            "session_count": 6512,
            "source_artifact_count": 1102,
            "changed_session_count": 2,
            "cached_source_artifact_count": 1100,
        },
        "cache": {
            "hit_count": 6510,
            "cold_skip_count": 3797,
        },
        "raw_copy": {
            "copied_file_count": 2,
        },
        "session_index": {
            "delta_session_count": 2,
            "derived_row_count": 2,
            "upserted_row_count": 2,
        },
        "timing": {
            "elapsed_seconds": 3.936,
            "native_scan_seconds": 0.422,
            "cache_compare_seconds": 0.028,
            "raw_copy_seconds": 0.001,
            "index_seconds": 0.119,
        },
        "instances": [
            {
                "provider": "copilot-cli",
                "instance": "copilot-main",
                "home": "/Users/pereiro/.copilot",
                "stats": {
                    "native_scan": {
                        "session_count": 3797,
                        "source_artifact_count": 0,
                        "changed_session_count": 0,
                        "cached_source_artifact_count": 0,
                    },
                    "cache": {
                        "hit_count": 3797,
                        "cold_skip_count": 3797,
                    },
                    "raw_copy": {
                        "copied_file_count": 0,
                    },
                    "session_index": {
                        "delta_session_count": 0,
                        "derived_row_count": 0,
                        "upserted_row_count": 0,
                    },
                    "timing": {
                        "elapsed_seconds": 0.549,
                        "native_scan_seconds": 0.422,
                        "cache_compare_seconds": 0.028,
                        "raw_copy_seconds": 0.0,
                        "index_seconds": 0.0,
                    },
                },
            },
        ],
    }

    _emit_update_summary(messages.append, payload)

    assert len(messages) == 2
    assert messages[0].startswith("[chatlas] copilot-cli ~/.copilot\n")
    assert messages[1].startswith("[chatlas] update complete\n")
    assert "sessions   total 6,512  changed 2  cached 6,510  cold-skip 3,797" in messages[1]
    assert "artifacts  total 1,102  cached 1,100  copied 2" in messages[1]
    assert "time       total 3.936s  scan 0.422s  compare 0.028s" in messages[1]
