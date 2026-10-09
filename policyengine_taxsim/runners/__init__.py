"""Tax calculation runners package"""

from ..core.lazy import lazy_attributes
from .base_runner import BaseTaxRunner
from .taxsim_runner import TaxsimRunner

__all__ = ["BaseTaxRunner", "PolicyEngineRunner", "StitchedRunner", "TaxsimRunner"]

# These two import policyengine-us, so they load on first access. cli.py
# imports TaxsimRunner, which runs this file, every time the CLI starts.
__getattr__, __dir__ = lazy_attributes(
    globals(),
    {
        "PolicyEngineRunner": "policyengine_taxsim.runners.policyengine_runner",
        "StitchedRunner": "policyengine_taxsim.runners.stitched_runner",
    },
)
