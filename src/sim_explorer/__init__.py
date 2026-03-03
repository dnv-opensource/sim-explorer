"""Python Package to manage Simulation Experiments."""

# NOTE: Below import of `libcosimpy.CosimLibrary` right here in the package root
#       is necessary to resolve DLL loading issues.
#
#       When `libcosimpy.CosimLibrary` is imported, the libcosimc dll is loaded and initialized.
#       However, if `libcosimpy.CosimLibrary` gets imported by separate processes,
#       such as when pytest spawns subprocesses, or when the CLI script gets called via `uv run`
#       then it can happen the libcosimc dll gets loaded by each process.
#       Unfortunately, this leads to problems.
#
#       Typical error messages you might encounter in this case are:
#           .../Lib/ctypes/__init__.py", line 468, in _load_library
#           OSError: [WinError 127] The specified procedure could not be found
#       or
#           The procedure entry point CRYPTO_calloc could not be located in the dynamic link library
#           <your-dev-path>/sim-explorer/venv/Lib/site-packages/libcosimpy/libcosimc/libssl-3-x64.dll.
#
#       By importing `libcosimpy.CosimLibrary` in the `__init__.py` file of the package root,
#       we ensure that the C++ library (libcosimc dll) is loaded only once,
#       when the package gets imported.
#       It then gets (re-)used across modules, and even across subprocesses that import the package,
#       given they are spawned after this initial import.

import libcosimpy.CosimLibrary
