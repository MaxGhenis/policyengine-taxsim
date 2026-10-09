"""Module attributes that load on first access (PEP 562).

Some public names need policyengine-us, and importing it takes about 20
seconds, so the modules that expose those names load them on first use:
importing the package, ``--help`` and ``--version`` don't import it.
"""

import importlib


def lazy_attributes(namespace, sources):
    """Return ``__getattr__`` and ``__dir__`` for the module whose globals are
    ``namespace``. ``sources`` maps each lazy name to the absolute name of the
    module that defines it. The first access imports that module and stores
    the object in ``namespace``, so later reads, including the module's own
    bare-name reads, find it there."""

    def __getattr__(name):
        if name not in sources:
            raise AttributeError(
                f"module {namespace['__name__']!r} has no attribute {name!r}"
            )
        try:
            module = importlib.import_module(sources[name])
        except AttributeError as error:
            # `from module import name` would turn this into a bare
            # "cannot import name" with no cause attached.
            raise ImportError(f"cannot load {name}: {error}") from error
        value = namespace[name] = getattr(module, name)
        return value

    def __dir__():
        return sorted({*namespace, *sources})

    return __getattr__, __dir__
