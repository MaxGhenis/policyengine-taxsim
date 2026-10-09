import importlib

import pytest


@pytest.fixture(autouse=True, scope="session")
def _load_lazy_names():
    """Load the names that import policyengine-us on first access
    (policyengine_taxsim/core/lazy.py) before any test runs, so that every
    test finds the real objects there. Otherwise the first test to run a
    command would bind whatever was patched at that moment, such as a fake
    on a runner's defining module, for every test after it, and a test that
    swaps sys.modules (patch.dict) could drop policyengine-us mid-session."""
    import policyengine_taxsim
    from policyengine_taxsim import runners

    cli = importlib.import_module("policyengine_taxsim.cli")
    cli._import_runners()
    for module, name in [
        (policyengine_taxsim, "export_household"),
        (runners, "PolicyEngineRunner"),
        (runners, "StitchedRunner"),
    ]:
        getattr(module, name)
