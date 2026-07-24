"""Fiscal exposure of the US federal tax base to AI.

Employment exposure is not fiscal exposure. This package joins occupation-level
AI exposure measures to household microdata in order to ask how much of the tax
base, as opposed to how much of the workforce, sits in highly exposed occupations.
"""

__version__ = "0.1.0"

from fiscal_exposure.config import Config, load_config
from fiscal_exposure.provenance import Manifest, file_digest

__all__ = ["Config", "load_config", "Manifest", "file_digest", "__version__"]
