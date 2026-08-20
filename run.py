from __future__ import annotations

import os
import pathlib
import site
import sys

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "src"


def _dependencies_available() -> bool:
    try:
        import apscheduler  # noqa: F401
        import numpy  # noqa: F401
        import pandas  # noqa: F401
        return True
    except ImportError:
        return False


def _local_site_packages() -> list[pathlib.Path]:
    return [
        *sorted((ROOT / ".venv" / "lib").glob("python*/site-packages")),
        ROOT / ".venv" / "Lib" / "site-packages",
    ]


def _local_venv_python() -> pathlib.Path | None:
    candidates = [
        ROOT / ".venv" / "bin" / "python",
        ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _launched_via_run_script() -> bool:
    if not sys.argv:
        return False

    try:
        return pathlib.Path(sys.argv[0]).resolve() == (ROOT / "run.py")
    except OSError:
        return pathlib.Path(sys.argv[0]).name == "run.py"


def _bootstrap_local_venv() -> None:
    if _dependencies_available():
        return

    for candidate in _local_site_packages():
        if candidate.exists() and str(candidate) not in sys.path:
            site.addsitedir(str(candidate))
            if _dependencies_available():
                return

    venv_python = _local_venv_python()
    if venv_python is None or not _launched_via_run_script():
        return

    try:
        already_using_venv = pathlib.Path(sys.executable).resolve() == venv_python.resolve()
    except OSError:
        already_using_venv = pathlib.Path(sys.executable).name == venv_python.name

    if not already_using_venv:
        os.execv(str(venv_python), [str(venv_python), __file__, *sys.argv[1:]])


def _should_start_scheduler() -> bool:
    if __name__ != "__main__":
        return True
    return os.getenv("WERKZEUG_RUN_MAIN") == "true"


_bootstrap_local_venv()

if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from finance_app.app import create_app


app = create_app(start_scheduler=_should_start_scheduler())

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5001, debug=True)
