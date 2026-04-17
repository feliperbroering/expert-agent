"""Packaged Robot Framework end-to-end test suites for `expert test`.

The `.robot` suites live in `./suites/` and are discoverable at runtime via
`importlib.resources`, so private agent repositories that install
`expert-agent[test]` inherit the suites automatically without having to vendor
or git-submodule them.
"""

from __future__ import annotations

from importlib import resources
from pathlib import Path


def suites_dir() -> Path:
    """Return the directory on disk that contains the shipped `.robot` suites.

    Resolves to the installed wheel location when the package is installed, or
    to the source tree when running from a development checkout.
    """
    with resources.as_file(resources.files(__name__).joinpath("suites")) as p:
        return Path(p)


__all__ = ["suites_dir"]
