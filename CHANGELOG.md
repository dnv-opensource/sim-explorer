# Changelog

All notable changes to the [sim-explorer] project will be documented in this file.<br>
The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

* -/-


## [0.3.0] - 2026-02-23

### Resolved
* src/sim_explorer/__init__.py: Added `import libcosimpy.CosimLibrary` in `__init__.py` on package root level. This to make sure the libcosimc dll gets loaded only once. This resolves a runtime error observed with libcosimpy. (Although the root bug is likely in libcosimpy; should be reviewed by the libcosimpy team).

### Added
* Added a new module `codegen.py` in sub-package `utils`, defining a helper function `get_callable_function()`:
  * `get_callable_function()` executes compiled code in explicit namespaces, retrieves a named function, validates it is callable, and eventually returns the created function.
  * Refactored class `Assertion` in module `assertion.py` to use the new helper function `get_callable_function()`. That way, the code in `Assertion` no longer relies on mutating `locals()`, which is known to be unreliable and can cause hard-to-track side effects.
  * Updated the related tests in `tests/test_assertion.py`.

### Removed
* Removed qa.bat
* Removed \_\_init\_\_.py files in /tests

### Changed
* GitHub Workflows:
  * _test_future.yml: Updated Python version in test_future to 3.15.0-alpha - 3.15.0
  * _test.yml: Updated Python versions in test matrix to 3.11, 3.12, 3.13, 3.14
  * Added 'name: Checkout code' to uses of 'actions/checkout', for better readability and consistency across workflow files.
  * Added 'name: Download build artifacts' to uses of 'actions/download-artifact', for better readability and consistency across workflow files.
  * Added 'name: Publish to PyPI' to uses of 'pypa/gh-action-pypi-publish', for better readability and consistency across workflow files.
  * Added 'name: Upload build artifacts' to uses of 'actions/upload-artifact', for better readability and consistency across workflow files.
  * Changed 'uv sync --upgrade' to 'uv sync -U'
  * Ensured that actions 'upload-artifact' and 'download-artifact' uniformly specify 'dist' as (file)name for the artifact uploaded (or downloaded, respectively), for consistency across workflow files.
  * pull_request_to_main.yml and nightly_build.yml: Added 'workflow_dispatch:' in selected workflows to allow manual trigger of the workflow.
  * Removed redundant 'Set up Python' steps (no longer needed, as 'uv sync' will automatically install Python if not present).
  * Replaced 'Build source distribution and wheel' with 'Build source distribution and wheels' (plural) in workflow step names.
  * Replaced 'Run twine check' with 'Check build artifacts' in workflow step names, to better reflect the purpose of the step.
  * Updated the syntax used for the OS and Python matrix in test workflows.
  * Added `--extra test` to the workflows running tests, as the test workflows will need these additional dependencies to run the FMUs in /tests/data/..
* pyproject.toml:
  * Added required-environments to uv.tools (windows, linux)
  * Removed deprecated mypy plugin 'numpy.typing.mypy_plugin'
  * Removed deprecated pyright setting 'reportShadowedImports'
  * Removed leading carets and trailing slashes from 'exclude' paths
  * Removed trailing slashes from 'exclude' paths
  * Updated supported Python versions to 3.11, 3.12, 3.13, 3.14
  * Removed upper version constraint from required Python version, i.e. changed the "requires-python" field from ">= 3.11, < 3.15" to ">= 3.11". <br>
    Detailed background and reasoning in this good yet long post by Henry Schreiner:
    https://iscinumpy.dev/post/bound-version-constraints/#pinning-the-python-version-is-special <br>
    TLDR: Placing an upper Python version constraint on a Python package causes more harm than it provides benefits.
    The upper version constraint unnecessarily manifests incompatibility with future Python releases.
    Removing the upper version constraint ensures the package remains installable as Python evolves.
    In the majority of cases, the newer Python version will anyhow be backward-compatible. And in the rare case where your package would really not work with a newer Python version,
    users can at least find a solution manually to resolve the conflict, e.g. by pinning your package to the last version compatible with the environment they install it in.
    That way, we ensure it remains _possible_ for users to find a solution, instead of rendering it impossible forever.
  * Added scipy>=1.16 to optional dependency group 'test', as TimeTableFMU.fmu requires scipy to be installed in the calling environment.
* Sphinx Documentation:
  * Sphinx conf.py: Removed ruff rule exception on file level
  * Sphinx conf.py: Updated year in copyright statement to 2026
* VS Code Settings:
  * Recommended extensions:
    * Removed 'njqdev.vscode-python-typehint' (Python Type Hint). Not maintained since 1 year, and the functionality is now covered by GitHub Copilot.
    * Added 'ms-python.debugpy' (Python Debugger).
    * Added 'ms-python.vscode-python-envs' (Python Environments).
    * Removed deprecated IntelliCode extension and replaced it by GitHub Copilot Chat as recommended replacement.
  * Updated 'mypy-type-checker.reportingScope' to 'custom'.
* .pre-commit-config.yaml: Updated id of ruff to ruff-check
* .sourcery.yaml: Updated the lowest Python version the project supports to '3.11'
* ruff.toml: Updated target Python version to "py311"

### Tests
* tests/data/BouncingBall3D: Updated `BouncingBall3D.fmu` and related tests.
* tests/data/MobileCrane: Updated `MobileCrane.fmu` and related tests.
* tests/data/Oscillator: Updated `HarmonicOscillator.fmu`
* Renamed folder `tests/data/SimpleTable` to `tests/data/TimeTable`
* Replaced `SimpleTable.fmu` with `TimeTableFMU.fmu` (in folder `tests/data/TimeTable`)
* tests/conftest.py:
  * Changed scope of top level fixtures from "package" to "session", because "session" scoped fixtures gets called before "package" scoped fixtures
* Repaired all failing tests

### Dependencies
* Updated to docutils>=0.22.4
* Updated to furo>=2025.12
* Updated to jupyter>=1.1.1
* Updated to libcosimpy>=0.0.5
* Updated to mypy>=1.19.1
* Updated to myst-parser>=5.0
* Updated to numpy>=2.3  (removed split version specifiers)
* Updated to plotly>=6.5
* Updated to pre-commit>=4.5
* Updated to pydantic>=2.12
* Updated to pyright>=1.1.408
* Updated to pytest-cov>=7.0
* Updated to pytest>=9.0
* Updated to ruff>=0.15.1
* Updated to sourcery>=1.43.0
* Updated to sphinx>=9.0
* Updated to sphinx-argparse-cli>=1.20.1
* Updated to sphinx-autodoc-typehints>=3.6
* Updated to sphinxcontrib-mermaid>=2.0
* Updated to sympy>=1.14.0
* .pre-commit-config.yaml:
  * Updated rev of pre-commit-hooks to v6.0.0
  * Updated rev of ruff-pre-commit to v0.15.1
* GitHub Workflows:
  * Updated 'checkout' action to v5
  * Updated 'download-artifact' action to v5
  * Updated 'setup-uv' action to v7
  * Updated 'upload-artifact' action to v5


## [0.2.1] - 2025-02-05

### Added
* Added CITATION.cff file
* Added mypy and pyright as static type checkers

### Changed
* Simplified set/get_variable_value interface, so that the special OSP set_initial call is not in general needed.
* Renamed `SimulatorInterface` to `SystemInterface`
* Modularized `SystemInterface`, and abstracted it away from the specific simulator: <br>
  `SystemInterface` managing only the specifications, `SystemInterfaceOSP` also being able to run simulations.
* Updated code base to be in sync with latest changes in python_project_template
* tests/test_oscillator_fmu.py : Skip test `test_run_osp_system_structure()` on Linux. The HarmonicOscillator.fmu throws an error on Linux (not though on Windows).

### Solved
* Updated `make_osp_system_structure()` to correctly handle bool
* Added missing type hints
* Resolved issues raised by ruff, mypy and pyright
* Sphinx documentation: resolved warnings raised in build process

### Dependencies
* Updated to ruff>=0.9.2  (from ruff>=0.6.3)
* Updated to pyright>=1.1.392  (from pyright>=1.1.378)
* Updated to sourcery>=1.31  (from sourcery>=1.22)
* Updated to numpy>=1.26  (from numpy>=1.26,<2.0)
* Updated to matplotlib>=3.10  (from matplotlib>=3.9.1)
* Updated to pytest-cov>=6.0  (from pytest-cov>=5.0)
* Updated to Sphinx>=8.1  (from Sphinx>=8.0)
* Updated to sphinx-argparse-cli>=1.19  (from sphinx-argparse-cli>=1.17)
* Updated to sphinx-autodoc-typehints>=3.0  (from sphinx-autodoc-typehints>=2.2)
* Updated to pre-commit>=4.0  (from pre-commit>=3.8)
* Updated to mypy>=1.14  (from mypy>=1.11.1)
* Updated to setup-uv@v5  (from setup-uv@v2)


## [0.2.0] - 2024-12-18
New Assertions release:

* Added support for assertions in each of the cases to have some kind of evaluation being run after every simulation.
* Display features to show the results of the assertions in a developer friendly format.

## [0.1.0] - 2024-11-08

### Changed
* Changed from `pip`/`tox` to `uv` as package manager
* README.rst : Completely rewrote section "Development Setup", introducing `uv` as package manager.
* Changed publishing workflow to use OpenID Connect (Trusted Publisher Management) when publishing to PyPI

### GitHub workflows
* (all workflows): Adapted to use `uv` as package manager
* _test_future.yml : updated Python version to 3.13.0-alpha - 3.13.0
* _test_future.yml : updated name of test job to 'test313'

### Dependencies
* updated to component-model>=0.1.0  (from component-model>=0.0.1)


## [0.0.1] - 2023-02-21

* Initial release

### Added

* added this

### Changed

* changed that

### Dependencies

* updated to some_package_on_pypi>=0.1.0

### Fixed

* fixed issue #12345

### Deprecated

* following features will soon be removed and have been marked as deprecated:
    * function x in module z

### Removed

* following features have been removed:
    * function y in module z


<!-- Markdown link & img dfn's -->
[unreleased]: https://github.com/dnv-opensource/sim-explorer/compare/v0.3.0...HEAD
[0.3.0]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.2.1...v0.3.0
[0.2.1]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.2.0...v0.2.1
[0.2.0]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.0.1...v0.1.0
[0.0.1]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.0.1
[sim-explorer]: https://github.com/dnv-opensource/sim-explorer
