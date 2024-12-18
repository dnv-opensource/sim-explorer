# Changelog

All notable changes to the [sim-explorer] project will be documented in this file.<br>
The changelog format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).

-/-

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
[unreleased]: https://github.com/dnv-innersource/sim-explorer/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/dnv-innersource/sim-explorer/releases/tag/v0.0.1...v0.1.0
[0.0.1]: https://github.com/dnv-innersource/sim-explorer/releases/tag/v0.0.1
[sim-explorer]: https://github.com/dnv-innersource/sim-explorer
