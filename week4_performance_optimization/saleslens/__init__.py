"""SalesLens: a retail transaction analytics application used for Week 4.

The package deliberately exposes two engines with the same public API:

* :mod:`saleslens.baseline` - the original, straightforward implementation.
* :mod:`saleslens.optimized` - the profile-guided optimized implementation.

Both engines return the same canonical result dictionary, which makes
correctness parity directly testable.
"""

from .data_generator import generate_dataset

__version__ = "1.0.0"

__all__ = ["__version__", "generate_dataset"]
