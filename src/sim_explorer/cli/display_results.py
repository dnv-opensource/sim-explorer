from typing import List

from rich.console import Console
from rich.panel import Panel

from sim_explorer.models import AssertionResult

console = Console()


def reconstruct_assertion_name(result: AssertionResult) -> str:
    """
    Reconstruct the assertion name from the key and expression.

    :param result: Assertion result.
    :return: Reconstructed assertion name.
    """
    time = result.time if result.time is not None else ""
    return f"{result.key}@{result.temporal.name}{time}({result.expression})"


def log_assertion_results(results: dict[str, list[AssertionResult]]):
    """
    Log test scenarios and results in a visually appealing bullet-point list format.

    :param scenarios: Dictionary where keys are scenario names and values are lists of test results.
                      Each test result is a tuple (test_name, status, details).
                      Status is True for pass, False for fail.
    """
    total_passed = 0
    total_failed = 0

    console.print()

    # Print results for each assertion executed in each of the cases ran
    for case_name, assertions in results.items():
        # Show case name first
        console.print(f"[bold magenta]• {case_name}[/bold magenta]")
        for assertion in assertions:
            if assertion.result:
                total_passed += 1
            else:
                total_failed += 1

            # Print assertion status, details and error message if failed
            status_icon = "✅" if assertion.result else "❌"
            status_color = "green" if assertion.result else "red"
            assertion_name = reconstruct_assertion_name(assertion)

            # Need to add some padding to show that the assertion belongs to a case
            console.print(f"   [{status_color}]{status_icon}[/] [cyan]{assertion_name}[/cyan]: {assertion.description}")

            if not assertion.result:
                console.print("      [red]⚠️ Error:[/] [dim]Assertion has failed[/dim]")

        console.print()  # Add spacing between scenarios

    if total_failed == 0 and total_passed == 0:
        return

    # Summary at the end
    passed_tests = f"[green]✅ {total_passed} tests passed[/green] 😎" if total_passed > 0 else ""
    failed_tests = f"[red]❌ {total_failed} tests failed[/red] 😭" if total_failed > 0 else ""
    padding = "   " if total_passed > 0 and total_failed > 0 else ""
    console.print(
        Panel.fit(
            f"{passed_tests}{padding}{failed_tests}", title="[bold blue]Test Summary[/bold blue]", border_style="blue"
        )
    )


def group_assertion_results(results: List[AssertionResult]) -> dict[str, List[AssertionResult]]:
    """
    Group test results by case name.

    :param results: List of assertion results.
    :return: Dictionary where keys are case names and values are lists of assertion results.
    """
    grouped_results: dict[str, List[AssertionResult]] = {}
    for result in results:
        case_name = result.case
        if case_name and case_name not in grouped_results:
            grouped_results[case_name] = []

        if case_name:
            grouped_results[case_name].append(result)
    return grouped_results
