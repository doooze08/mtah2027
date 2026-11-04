"""Scenario families. One file per family; each file only calls simulation.core.

A family file defines two names and nothing else is required:

    FAMILY = "long_ball_header_duel"            # identifier from the spec
    SUBTYPES = {"HD01": build_hd01, ...}        # subtype id -> script function

A script function has the signature build(b: ClipBuilder, rng: numpy.random.Generator) and
stages the story on `b`. Families are discovered by file name, so adding a family never means
editing a shared registry (and parallel worktrees do not collide here).
"""

import importlib
import pkgutil


def all_subtypes():
    """{subtype_id: (family, build_function)} for every family file in this package."""
    found = {}
    for module_info in pkgutil.iter_modules(__path__):
        if module_info.name.startswith("_"):
            continue
        module = importlib.import_module("{}.{}".format(__name__, module_info.name))
        for subtype, build in module.SUBTYPES.items():
            if subtype in found:
                raise ValueError("subtype {} defined twice".format(subtype))
            found[subtype] = (module.FAMILY, build)
    return found
