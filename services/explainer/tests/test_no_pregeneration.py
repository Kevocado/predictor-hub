"""No background pre-generation: a summary is made when a reader asks for one.

The scheduler used to walk 72 hours across five sports on a three-hour timer.
That was the main consumer of the daily cap, and it kept spending on `f1` and
`nba` after the redesign stopped serving them. On demand it should be a fraction
of that — and the cap is then revisited from real numbers rather than a guess.
"""
import inspect

import pytest

from explainer import app as app_mod


def test_the_scheduler_module_is_gone():
    with pytest.raises(ModuleNotFoundError):
        import explainer.scheduler  # noqa: F401


def test_the_app_starts_no_pregeneration_task():
    source = inspect.getsource(app_mod)
    assert "run_forever" not in source and "pregenerate" not in source, (
        "the scheduler is still wired into the lifespan"
    )


def test_nothing_imports_the_scheduler():
    # Deleting the module is not the same as deleting the idea: a second caller
    # would reintroduce the spend without reintroducing the file.
    #
    # Parsed with `ast` rather than grepped for the word, because the obvious
    # substring guard is wrong in a way that pushes you into hiding: the comment
    # in app.py explaining that the scheduler is gone mentions "scheduler", and
    # a substring check reports that as a live reference. Rewording honest
    # documentation to satisfy a check is how a check stops being read. An
    # import is an `ast.Import` or `ast.ImportFrom` node, and that is the whole
    # of what "still uses it" means for a deleted module.
    import ast
    import pathlib

    import explainer

    offenders = []
    for path in pathlib.Path(explainer.__path__[0]).glob("*.py"):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [node.module or ""]
            else:
                continue
            if any("scheduler" in n for n in names):
                offenders.append(f"{path.name}:{node.lineno}")
    assert not offenders, f"still imports the scheduler: {offenders}"
