"""``--help`` and ``--version`` must not import policyengine-us.

Importing policyengine-us takes about 20 seconds, so the names that need it
load on first access (policyengine_taxsim/core/lazy.py): ``export_household``
in the package, and ``PolicyEngineRunner`` and ``StitchedRunner`` in
``runners`` and ``cli``. Invariants tested here:

- ``--version``, ``--help`` and every subcommand's ``--help`` import neither
  policyengine-us nor policyengine-core.
- Every command binds the runners after the option checks that don't need
  its input and before it reads its input, so a run imports policyengine-us
  and keeps the process-wide state that import sets up, such as a filter
  that ignores every warning (policyengine_us/model_api.py).
- The huggingface_hub logger is at ERROR whether or not policyengine-us has
  loaded.
- cli.py runs as ``__main__`` (``python -m``, runpy, profilers) without a
  warning and in whatever namespace runpy gives it.
- Before they load, the lazy names are listed by ``dir()`` without being
  module globals; once loaded, each is its defining module's object. Unknown
  names still raise AttributeError, and an AttributeError raised while a lazy
  name's module imports reaches ``from ... import`` as an ImportError that
  keeps it as the cause.

These run in fresh interpreters where they depend on what has been imported,
because conftest.py loads the lazy names before any test in this session.
"""

import importlib
import importlib.util
import json
import logging
import subprocess
import sys

import pytest
from click.testing import CliRunner

import policyengine_taxsim
from policyengine_taxsim import runners
from policyengine_taxsim.cli import cli

# The package re-exports the ``cli`` group, which shadows the module name.
CLI_MODULE = importlib.import_module("policyengine_taxsim.cli")
ENGINE_PACKAGES = ("policyengine_us", "policyengine_core")
LAZY_NAMES = {
    "policyengine_taxsim": ["export_household"],
    "policyengine_taxsim.runners": ["PolicyEngineRunner", "StitchedRunner"],
    "policyengine_taxsim.cli": ["PolicyEngineRunner", "StitchedRunner"],
}

# Runs the installed console script's entry point, as `policyengine-taxsim
# ARGS...` does, then reports the exit code, the engine modules imported and
# the huggingface_hub logger's level.
CLI_PROBE = """
import json, logging, sys
from importlib.metadata import distribution

report, *args = sys.argv[1:]
(entry_point,) = [
    ep
    for ep in distribution("policyengine-taxsim").entry_points
    if ep.group == "console_scripts"
]
try:
    entry_point.load()(args)
    code = 0
except SystemExit as exit:
    code = exit.code
with open(report, "w") as stream:
    json.dump(
        {
            "code": code,
            "engines": sorted(
                name for name in sys.modules if name.split(".")[0] in %r
            ),
            "hf_level": logging.getLogger("huggingface_hub").level,
        },
        stream,
    )
""" % (ENGINE_PACKAGES,)

# Imports each module with lazy names and reports which of them dir() lists
# and which are already module globals, and the engine modules imported.
LAZY_PROBE = """
import importlib, json, sys

report, lazy_names = sys.argv[1], json.loads(sys.argv[2])
result = {}
for module_name, names in lazy_names.items():
    module = importlib.import_module(module_name)
    result[module_name] = {
        "listed": [name for name in names if name in dir(module)],
        "loaded": [name for name in names if name in vars(module)],
    }
result["engines"] = sorted(
    name for name in sys.modules if name.split(".")[0] in %r
)
with open(report, "w") as stream:
    json.dump(result, stream)
""" % (ENGINE_PACKAGES,)


def run_probe(tmp_path, probe, *args):
    report = tmp_path / "report.json"
    process = subprocess.run(
        [sys.executable, "-c", probe, str(report), *args],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert report.exists(), process.stderr
    return json.loads(report.read_text()), process


def test_engine_packages_are_installed_under_these_names():
    # Guards the probes: a renamed module would make "not imported" vacuous.
    for name in ENGINE_PACKAGES:
        assert importlib.util.find_spec(name) is not None, name


@pytest.mark.parametrize(
    "args",
    [["--version"], ["--help"]] + [[name, "--help"] for name in sorted(cli.commands)],
    ids=" ".join,
)
def test_help_and_version_skip_policyengine_us(tmp_path, args):
    result, process = run_probe(tmp_path, CLI_PROBE, *args)
    assert result["code"] == 0, process.stderr
    assert process.stdout.strip(), process.stderr
    assert result["engines"] == []
    assert result["hf_level"] == logging.ERROR


def test_a_command_run_imports_policyengine_us(tmp_path):
    # sample-data never runs PolicyEngine, but it imports the runners first
    # so it keeps the process-wide state policyengine-us sets up.
    data = tmp_path / "input.csv"
    data.write_text("taxsimid,year\n1,2023\n")
    result, process = run_probe(tmp_path, CLI_PROBE, "sample-data", str(data))
    assert result["code"] == 0, process.stderr
    assert "File contains 1 records" in process.stdout
    assert "policyengine_us" in result["engines"]
    # policyengine-us imports huggingface_hub, which must not reset the level.
    assert result["hf_level"] == logging.ERROR


def test_python_m_runs_the_cli_without_a_warning():
    # The package imports cli.py before `python -m` runs it as __main__.
    process = subprocess.run(
        [sys.executable, "-m", "policyengine_taxsim.cli", "--version"],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert process.returncode == 0, process.stderr
    assert "policyengine-taxsim:" in process.stdout
    assert "found in sys.modules" not in process.stderr


def test_runpy_runs_a_command_in_its_own_namespace(tmp_path):
    # runpy.run_module and profilers (python -m cProfile -m ...) run cli.py as
    # __main__ in a namespace that isn't sys.modules["__main__"].
    data = tmp_path / "input.csv"
    data.write_text("taxsimid,year\n1,2023\n")
    process = subprocess.run(
        [
            sys.executable,
            "-c",
            "import runpy; "
            "runpy.run_module('policyengine_taxsim.cli', run_name='__main__')",
            "sample-data",
            str(data),
        ],
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert process.returncode == 0, process.stderr
    assert "File contains 1 records" in process.stdout


# One entry per command: how to call it, and what reads its input.
COMMANDS = {
    "<stdin>": ([], "pd.read_csv"),
    "policyengine": (["policyengine", "INPUT"], "read_input"),
    "taxsim": (["taxsim", "INPUT"], "read_input"),
    "compare": (["compare", "INPUT"], "read_input"),
    "sample-data": (["sample-data", "INPUT"], "read_input"),
}


def test_every_command_is_covered():
    assert set(COMMANDS) == {"<stdin>", *cli.commands}


@pytest.mark.parametrize("command", COMMANDS)
def test_command_binds_runners_before_reading_input(command, tmp_path, monkeypatch):
    data = tmp_path / "input.csv"
    data.write_text("taxsimid,year\n1,2023\n")
    args, reader = COMMANDS[command]
    args = [str(data) if arg == "INPUT" else arg for arg in args]
    calls = []

    def stop_reading(*_args, **_kwargs):
        calls.append("read")
        raise RuntimeError("stop before running")

    monkeypatch.setattr(CLI_MODULE, "_import_runners", lambda: calls.append("bind"))
    if reader == "pd.read_csv":
        monkeypatch.setattr(CLI_MODULE.pd, "read_csv", stop_reading)
    else:
        monkeypatch.setattr(CLI_MODULE, reader, stop_reading)

    CliRunner().invoke(cli, args, input="taxsimid,year\n1,2023\n")
    assert calls == ["bind", "read"]


# Sidecar paths the --provenance option's own check lets through (a file that
# doesn't exist yet, or an earlier provenance record) but the command refuses
# because the run reads or writes them.
REFUSED_SIDECARS = {
    "policyengine": ["policyengine", "INPUT", "-o", "OUTPUT", "--provenance", "OUTPUT"],
    "taxsim": ["taxsim", "INPUT", "-o", "OUTPUT", "--provenance", "OUTPUT"],
    "compare": ["compare", "RECORD", "--provenance", "RECORD"],
}


@pytest.mark.parametrize("command", REFUSED_SIDECARS)
def test_a_refused_sidecar_path_fails_before_binding_runners(
    command, tmp_path, monkeypatch
):
    paths = {
        "INPUT": tmp_path / "input.csv",
        "OUTPUT": tmp_path / "output.csv",
        "RECORD": tmp_path / "record.json",
    }
    paths["INPUT"].write_text("taxsimid,year\n1,2023\n")
    paths["RECORD"].write_text('{"schemaVersion": 1}\n')
    args = [str(paths.get(arg, arg)) for arg in REFUSED_SIDECARS[command]]
    calls = []
    monkeypatch.setattr(CLI_MODULE, "_import_runners", lambda: calls.append("bind"))

    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 2, result.output
    assert "is the run's input or output file" in result.output
    assert calls == []


def test_lazy_names_are_listed_before_they_load(tmp_path):
    result, process = run_probe(tmp_path, LAZY_PROBE, json.dumps(LAZY_NAMES))
    assert result.pop("engines") == [], process.stderr
    assert result == {
        module: {"listed": names, "loaded": []} for module, names in LAZY_NAMES.items()
    }


def test_lazy_names_are_the_defining_modules_objects():
    from policyengine_taxsim.core.output_mapper import export_household
    from policyengine_taxsim.runners.policyengine_runner import PolicyEngineRunner
    from policyengine_taxsim.runners.stitched_runner import StitchedRunner

    assert policyengine_taxsim.export_household is export_household
    for module in (runners, CLI_MODULE):
        assert module.PolicyEngineRunner is PolicyEngineRunner
        assert module.StitchedRunner is StitchedRunner


@pytest.mark.parametrize("module", [policyengine_taxsim, runners, CLI_MODULE])
def test_unknown_names_still_raise_attribute_error(module):
    with pytest.raises(AttributeError, match="no_such_name"):
        module.no_such_name
    assert not hasattr(module, "no_such_name")


@pytest.fixture
def lazy_package(tmp_path, monkeypatch):
    """A package whose ``value`` and ``failing`` load lazily from submodules;
    importing ``failing``'s module raises AttributeError."""
    package = tmp_path / "lazy_package"
    package.mkdir()
    (package / "__init__.py").write_text(
        "from policyengine_taxsim.core.lazy import lazy_attributes\n"
        "__getattr__, __dir__ = lazy_attributes(\n"
        "    globals(),\n"
        "    {'value': 'lazy_package._value', 'failing': 'lazy_package._failing'},\n"
        ")\n"
    )
    (package / "_value.py").write_text("value = object()\n")
    (package / "_failing.py").write_text(
        "raise AttributeError('module numpy has no attribute float_')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield importlib.import_module("lazy_package")
    for name in [name for name in sys.modules if name.startswith("lazy_package")]:
        del sys.modules[name]


def test_a_lazy_name_loads_once_into_the_module(lazy_package):
    assert "value" in dir(lazy_package)
    assert "value" not in vars(lazy_package)
    value = lazy_package.value
    assert value is sys.modules["lazy_package._value"].value
    assert vars(lazy_package)["value"] is value


def test_an_attribute_error_while_loading_keeps_its_cause(lazy_package):
    with pytest.raises(ImportError, match="cannot load failing") as raised:
        from lazy_package import failing  # noqa: F401
    assert isinstance(raised.value.__cause__, AttributeError)
    assert "float_" in str(raised.value.__cause__)
