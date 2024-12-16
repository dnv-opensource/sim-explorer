from rich.console import Console
from rich.panel import Panel

console = Console()

def log_assertion_results(results):
    """
    Log test scenarios and results in a visually appealing bullet-point list format.

    :param scenarios: Dictionary where keys are scenario names and values are lists of test results.
                      Each test result is a tuple (test_name, status, details).
                      Status is True for pass, False for fail.
    """
    total_passed = 0
    total_failed = 0

    for case in results:
        console.print(f"[bold magenta]• {case['name']}[/bold magenta]")
        for assertion in case['assertions']:
            if assertion['status']:
                total_passed += 1
            else:
                total_failed += 1

            status_icon = "✅" if assertion['status'] else "❌"
            status_color = "green" if assertion['status'] else "red"
            console.print(f"   [{status_color}]{status_icon}[/] [cyan]{assertion['formulation']}[/cyan]: Assertion has failed.")
        console.print()  # Add spacing between scenarios

    # Summary at the end
    console.print(Panel.fit(
        f"[green]✅ {total_passed} tests passed[/green] 😎   [red]❌ {total_failed} tests failed[/red] 😭",
        title="[bold blue]Test Summary[/bold blue]",
        border_style="blue"
    ))
