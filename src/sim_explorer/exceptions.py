from __future__ import annotations

"""This module contains custom exceptions for the sim-explorer package."""


class CaseInitError(Exception):
    """Special error indicating that something is wrong during initialization of cases."""

    pass


class CaseUseError(Exception):
    """Special error indicating that something is wrong during usage of cases."""

    pass
