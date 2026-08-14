# $kw: ^agentos-stdlib-refs-ref-path --from Agent.Navigable.Codebase --note [DF] reusable refs behavior lives beneath the Python stdlib namespace matching its CLI --supp ^c20260811-62u
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

from tarav._core.errors import CliError

_REF_PATH_FRAGMENT_RE = re.compile(r"^L(\d+)C(\d+)-L(\d+)C(\d+)$")


def build_ref_path_uri(repo_hash: str, reference: dict[str, object]) -> str:
    commit = str(reference.get("commit", "")).strip()
    path = str(reference.get("path", "")).strip()
    if not commit:
        raise CliError("reference field commit is required for ref-path output")
    if not path:
        raise CliError("reference field path is required for ref-path output")

    start = reference.get("start")
    end = reference.get("end")
    if not isinstance(start, dict) or not isinstance(end, dict):
        raise CliError("reference fields start/end must be objects for ref-path output")

    try:
        start_line = int(start["line"])
        start_column = int(start["column"])
        end_line = int(end["line"])
        end_column = int(end["column"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CliError("reference start/end line/column must be integers") from exc

    encoded_path = quote(path, safe="/-._~")
    return (
        f"git-ref://{repo_hash}/blob/{commit}/{encoded_path}"
        f"#L{start_line}C{start_column}-L{end_line}C{end_column}"
    )


def parse_ref_path_uri(ref_path: str) -> dict[str, object]:
    parsed = urlparse(ref_path)
    if parsed.scheme != "git-ref":
        raise CliError(f"invalid ref-path URI scheme: {parsed.scheme!r} (expected 'git-ref')")

    repo_hash = parsed.netloc.strip()
    if not repo_hash:
        raise CliError("invalid ref-path URI: missing repo hash")

    raw_path = parsed.path.lstrip("/")
    blob_prefix = "blob/"
    if not raw_path.startswith(blob_prefix):
        raise CliError("invalid ref-path URI: path must start with '/blob/<commit>/...'")

    blob_payload = raw_path[len(blob_prefix) :]
    if "/" not in blob_payload:
        raise CliError("invalid ref-path URI: missing blob path segment after commit")

    commit, encoded_rel_path = blob_payload.split("/", 1)
    commit = commit.strip()
    if not commit:
        raise CliError("invalid ref-path URI: missing commit segment")

    relative_path = unquote(encoded_rel_path)
    if not relative_path or relative_path.startswith("/"):
        raise CliError("invalid ref-path URI: relative blob path is required")

    fragment_match = _REF_PATH_FRAGMENT_RE.match(parsed.fragment)
    if fragment_match is None:
        raise CliError(
            "invalid ref-path URI fragment: expected format "
            "'#L<startLine>C<startColumn>-L<endLine>C<endColumn>'"
        )

    start_line = int(fragment_match.group(1))
    start_column = int(fragment_match.group(2))
    end_line = int(fragment_match.group(3))
    end_column = int(fragment_match.group(4))

    return {
        "repo_hash": repo_hash,
        "commit": commit,
        "path": relative_path,
        "start": {"line": start_line, "column": start_column},
        "end": {"line": end_line, "column": end_column},
    }
