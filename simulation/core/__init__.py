"""Shared parts of the simulator. Scenario files import from here and never modify it.

The public surface a scenario needs is small:

    from simulation.core import ClipBuilder

Everything else in this package (rendering, truth, checks, file writing) is driven by
simulation/generate.py, not by scenario code.
"""

from simulation.core.clip import ClipBuilder

__all__ = ["ClipBuilder"]
