# Changelog

All notable changes to the [sim-explorer] project will be documented in this file.<br>
The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

## [Unreleased]

-/-


### Changed
* GitHub Workflows:
  * _test_future.yml: Updated name of test_future job to 'test315'
  * _test_future.yml: Updated Python specifier in comment to 3.15
  * _test_future.yml: Updated Python specifier in workflow name to py315
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
* pyproject.toml:
  * pyproject.toml: Added required-environments to uv.tools (windows, linux)
  * pyproject.toml: Removed deprecated mypy plugin 'numpy.typing.mypy_plugin'
  * pyproject.toml: Removed deprecated pyright setting 'reportShadowedImports'
  * pyproject.toml: Removed leading carets and trailing slashes from 'exclude' paths
  * pyproject.toml: Removed trailing slashes from 'exclude' paths
  * pyproject.toml: Updated supported Python versions to 3.11, 3.12, 3.13, 3.14
  * Removed upper version constraint from required Python version, i.e. changed the "requires-python" field from ">= 3.11, < 3.15" to ">= 3.11". <br>
    Detailed background and reasoning in this good yet long post by Henry Schreiner:
    https://iscinumpy.dev/post/bound-version-constraints/#pinning-the-python-version-is-special <br>
    TLDR: Placing an upper Python version constraint on a Python package causes more harm than it provides benefits.
    The upper version constraint unnecessarily manifests incompatibility with future Python releases.
    Removing the upper version constraint ensures the package remains installable as Python evolves.
    In the majority of cases, the newer Python version will anyhow be backward-compatible. And in the rare case where your package would really not work with a newer Python version,
    users can at least find a solution manually to resolve the conflict, e.g. by pinning your package to the last version compatible with the environment they install it in.
    That way, we ensure it remains _possible_ for users to find a solution, instead of rendering it impossible forever.
* Sphinx Documentation:
  * Sphinx conf.py: Removed ruff rule exception on file level
  * Sphinx conf.py: Updated year in copyright statement to 2026


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
[unreleased]: https://github.com/dnv-opensource/sim-explorer/compare/v0.2.1...HEAD
[0.2.1]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.2.0...v0.2.1
[0.2.0]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.1.0...v0.2.0
[0.1.0]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.0.1...v0.1.0
[0.0.1]: https://github.com/dnv-opensource/sim-explorer/releases/tag/v0.0.1
[sim-explorer]: https://github.com/dnv-opensource/sim-explorer
