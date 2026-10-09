import warnings

from .core.input_mapper import generate_household
from .core.lazy import lazy_attributes
from .cli import cli

__all__ = ["generate_household", "export_household", "cli"]

__version__ = "3.1.1"

# export_household imports policyengine-us, so it loads on first access.
__getattr__, __dir__ = lazy_attributes(
    globals(), {"export_household": "policyengine_taxsim.core.output_mapper"}
)

# `python -m policyengine_taxsim.cli` imports this package, and with it the
# cli module, before running cli.py as __main__, so runpy warns that the
# module is already loaded. Running cli.py a second time is harmless.
warnings.filterwarnings(
    "ignore",
    message=r"'policyengine_taxsim\.cli' found in sys\.modules",
    category=RuntimeWarning,
)
