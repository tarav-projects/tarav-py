# $kw: ^agentos-stdlib-utils-tmp-folder --from Agent.Navigable.Codebase --note [DF] reusable utils behavior lives beneath the Python stdlib namespace matching its CLI --supp ^c20260811-62u
from __future__ import annotations

from pathlib import Path

from tarav.l0._core.errors import CliError
from tarav.l0._core.ids import generate_uuid4_hex
from tarav.l0._core.project import project_agentos_dir, require_agentos_project_root


def allocate_project_tmp_folder(
    *,
    create: bool,
    start_path: Path | str = ".",
    project: Path | str | None = None,
    max_attempts: int = 32,
) -> Path:
    project_root = require_agentos_project_root(
        start_path,
        project=project,
        include_init_hint=True,
    )
    tmp_root = project_agentos_dir(project_root) / "tmp"

    folder_path: Path | None = None
    for _ in range(max_attempts):
        candidate = (tmp_root / f"tmp-{generate_uuid4_hex()}").resolve()
        if create:
            try:
                candidate.mkdir(parents=True, exist_ok=False)
                folder_path = candidate
                break
            except FileExistsError:
                continue
        elif not candidate.exists():
            folder_path = candidate
            break

    if folder_path is None:
        raise CliError(f"unable to allocate unique tmp-folder path under: {tmp_root}")

    return folder_path
