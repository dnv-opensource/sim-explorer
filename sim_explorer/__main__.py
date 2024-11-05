import argparse
import importlib.metadata

from sim_explorer.case import Case, Cases


def cli_main():
    """Provide a Command Line Interface for sim-explorer.

    `see Python tutorial for working with argparse <https://docs.python.org/3/howto/argparse.html>`_
    """
    __version__ = importlib.metadata.version("sim_explorer")
    parser = argparse.ArgumentParser(prog="sim_explorer")
    parser.add_argument("-V", "--version", action="version", version=__version__)
    parser.add_argument("cases", type=str, help="The sim-explorer specification file.")
    parser.add_argument("--info", action="store_true", help="Display the structure of the defined cases.")
    parser.add_argument("--run", type=str, help="Run a single case.")
    parser.add_argument("--Run", type=str, help="Run a case and all its sub-cases.")
    args = parser.parse_args()
    cases = Cases(args.cases)
    print("ARGS", args)
    if not isinstance(cases, Cases):
        print(f"Instantiation of {args.cases} not successfull")
    if args.info is not None:
        print(cases.info())
    elif args.run is not None:
        case = cases.case_by_name(args.run)
        if not isinstance(case, Case):
            print(f"Case {args.case} not found in {args.cases}")
        case.run()
    elif args.Run is not None:
        case = cases.case_by_name(args.Run)
        if not isinstance(case, Case):
            print(f"Case {args.case} not found in {args.cases}")
        for c in case.iter():
            c.run()


if __name__ == "__main__":
    cli_main()
