"""No module may be shadowed by a stray file beside the package.

`services/explainer/contract.py` existed as a byte-identical, **unimported**
copy of `services/explainer/explainer/contract.py`. It was invisible in review
because nothing imported it: the code says `from .contract import …`, and a
relative import resolves inside the package. A duplicate that is never read is
the cheapest kind of file to add and the most expensive kind to maintain — the
next person edits the copy, the copy looks right, and the real module is what
ships.

The general rule, asserted rather than left to a reviewer's eye: a service
directory holds its package, its tests, its Dockerfile and its config. A `.py`
file at that level is either a mistake or a shadow, because the package directory
is where a module belongs. And where the level *is* on `sys.path` (it is, when
pytest runs from the service root), a same-named file there is not merely
redundant — it is importable, so `import contract` resolves to the copy and the
divergence becomes invisible in the worst way.
"""
from __future__ import annotations

import pathlib

import pytest

SERVICE = pathlib.Path(__file__).resolve().parent.parent          # services/explainer
PACKAGE = SERVICE / "explainer"

#: The only top-level names allowed to end in .py, and why. `conftest.py` lives in
#: tests/ rather than here, so nothing needs allowing today — the list is here so
#: that a future addition is a deliberate edit with a reason attached, rather
#: than a file that appears and is never questioned again.
ALLOWED_TOP_LEVEL = {}


def test_the_service_directory_holds_no_python_modules():
    strays = sorted(p.name for p in SERVICE.glob("*.py") if p.name not in ALLOWED_TOP_LEVEL)
    assert not strays, (
        f"{strays} sit directly in {SERVICE.name}/, beside the package rather than "
        f"inside it. Either it belongs in {PACKAGE.name}/ (and its test in "
        f"tests/), or it shadows that module: the service root is on sys.path "
        f"when pytest runs here, so `import {strays[0][:-3]}` resolves to the "
        f"stray and the divergence is invisible."
    )


def test_no_module_name_exists_twice_in_this_service():
    """The specific failure, kept as its own test so the message names the file.

    Byte-identical is the easy case. Two files that merely share a name are worse
    — they can drift, and the drift is the whole problem.
    """
    top_level = {p.stem for p in SERVICE.glob("*.py")}
    in_package = {p.stem for p in PACKAGE.glob("*.py") if p.stem != "__init__"}
    both = sorted(top_level & in_package)
    assert not both, (
        f"{both} exist both directly in {SERVICE.name}/ and inside "
        f"{PACKAGE.name}/. Two files, one module name, and only one of them is "
        f"imported."
    )


def test_the_imported_module_is_the_one_in_the_package():
    """Which copy actually loads — checked, not assumed.

    If this ever fails, `from .contract import …` is resolving somewhere
    unexpected and every other test in the suite is reading the other file.
    """
    import explainer.contract as contract

    assert pathlib.Path(contract.__file__).resolve().parent == PACKAGE.resolve(), (
        f"explainer.contract loaded from {contract.__file__}, which is not the package"
    )


def test_the_package_is_importable_without_the_stray_file_hiding_a_typo():
    """A missing module should be a ModuleNotFoundError naming a real path.

    With a same-named file on sys.path, a typo like `from .contrct import …`
    still fails — but `import contract` elsewhere quietly succeeds against the
    copy, and the two disagree for as long as both exist.
    """
    with pytest.raises(ModuleNotFoundError):
        importlib_import("explainer.definitely_not_a_module")


def importlib_import(name: str):
    __import__(name)
