#!/usr/bin/env python
"""sim-explorer command line interface."""

import argparse
import importlib.metadata
import logging
import sys
from pathlib import Path

from sim_explorer.case import Case, Cases
from sim_explorer.cli.display_results import group_assertion_results, log_assertion_results
from sim_explorer.utils.logging import configure_logging

# Remove current directory from Python search path.
# Only through this trick it is possible that the current CLI file 'sim_explorer.py'
# carries the same name as the package 'sim_explorer' we import from in the next lines.
# If we did NOT remove the current directory from the Python search path,
# Python would start searching for the imported names within the current file (sim_explorer.py)
# instead of the package 'sim_explorer' (and the import statements fail).
sys.path = [path for path in sys.path if Path(path) != Path(__file__).parent]

logger = logging.getLogger(__name__)


def _argparser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="sim-explorer",
        usage="%(prog)s cases [options [args]]",
        epilog="_________________sim-explorer___________________",
        prefix_chars="-",
        add_help=True,
        description=("sim-explorer cases --info"),
    )

    _ = parser.add_argument(
        "cases",
        metavar="cases",
        type=str,
        help="The sim-explorer specification file.",
    )

    _ = parser.add_argument(
        "--info",
        action="store_true",
        help="Display the structure of the defined cases.",
        default=False,
        required=False,
    )

    run = parser.add_mutually_exclusive_group(required=False)

    _ = run.add_argument(
        "--run",
        metavar="run",
        action="store",
        type=str,
        help="Run a single case.",
        default=None,
    )

    _ = run.add_argument(
        "--Run",
        metavar="Run",
        action="store",
        type=str,
        help="Run a case and all its sub-cases.",
        default=None,
    )

    console_verbosity = parser.add_mutually_exclusive_group(required=False)

    _ = console_verbosity.add_argument(
        "-q",
        "--quiet",
        action="store_true",
        help=("console output will be quiet."),
        default=False,
    )

    _ = console_verbosity.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help=("console output will be verbose."),
        default=False,
    )

    _ = parser.add_argument(
        "--log",
        action="store",
        type=str,
        help="name of log file. If specified, this will activate logging to file.",
        default=None,
        required=False,
    )

    _ = parser.add_argument(
        "--log-level",
        action="store",
        type=str,
        help="log level applied to logging to file.",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        default="WARNING",
        required=False,
    )

    __version__ = importlib.metadata.version("sim-explorer")
    _ = parser.add_argument(
        "-V",
        "--version",
        action="version",
        version=__version__,
    )

    return parser


def main() -> None:
    """Entry point for console script as configured in pyproject.toml.

    Runs the command line interface and parses arguments and options entered on the console.
    """
    parser = _argparser()
    args = parser.parse_args()

    # Configure Logging
    # ..to console
    log_level_console: str = "WARNING"
    if any([args.quiet, args.verbose]):
        log_level_console = "ERROR" if args.quiet else log_level_console
        log_level_console = "INFO" if args.verbose else log_level_console
    # ..to file
    log_file: Path | None = Path(args.log) if args.log else None
    log_level_file: str = args.log_level
    configure_logging(log_level_console, log_file, log_level_file)

    cases_path: Path = Path(args.cases)
    # Check whether sim-explorer cases file exists
    if not cases_path.is_file():
        logger.error(f"sim-explorer.py: File {cases_path} not found.")
        return
    logger.info(f"ARGS: {args}")

    try:
        cases = Cases(args.cases)
    except Exception:
        logger.exception(f"Instantiation of {args.cases} not successfull")
        return

    log_msg_stub: str = f"Start sim-explorer.py with following arguments:\n\t cases: \t{cases}\n"

    case: Case | None = None

    if args.info is not None and args.info:
        # TODO @EisDNV: Consider to use logging instead of printing. ClaasRostock, 2025-01-26.
        print(cases.info())  # noqa: T201

    elif args.run is not None:
        case = cases.case_by_name(args.run)

        if case is None:
            logger.error(f"Case {args.run} not found in {args.cases}")
            return

        logger.info(f"{log_msg_stub}\t option: run \t\t\t{args.run}\n")
        # Invoke API
        cases.run_case(case, run_subs=False, run_assertions=True)

        # Display assertion results
        assertion_results = list(cases.assertion.report())
        grouped_results = group_assertion_results(assertion_results)
        log_assertion_results(grouped_results)

    elif args.Run is not None:
        case = cases.case_by_name(args.Run)
        if case is None:
            logger.error(f"Case {args.Run} not found in {args.cases}")
            return
        logger.info(f"{log_msg_stub}\t --Run \t\t\t{args.Run}\n")
        # Invoke API
        cases.run_case(case, run_subs=True, run_assertions=True)

        # Display assertion results
        assertion_results = list(cases.assertion.report())
        grouped_results = group_assertion_results(assertion_results)
        log_assertion_results(grouped_results)


if __name__ == "__main__":
    main()
