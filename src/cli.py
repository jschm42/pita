"""Command line interface for the pita application.

Allows running tests headlessly or using custom parameters directly from the console.
"""

import asyncio
import logging
import sys
from typing import Any

import click
from rich.console import Console
from rich.rule import Rule
from rich.text import Text

from src.core import project_manager
from src.core.agent import QABrowserAgent
from src.core.models import ProjectConfig, TestCase
from src.infrastructure.browser_service import BrowserService
from src.infrastructure.llm_client import LLMClient

# Disable verbose debug logs from other packages unless debug mode is active
logging.getLogger("pika").setLevel(logging.WARNING)
logging.getLogger("urllib3").setLevel(logging.WARNING)
logging.getLogger("playwright").setLevel(logging.WARNING)

console = Console()


def parse_credentials(
    ctx: click.Context | None, param: click.Parameter | None, value: tuple[str, ...]
) -> dict[str, str]:
    """Parses credential options in KEY=VALUE format into a dictionary.

    Args:
        ctx: Click context (optional).
        param: Click parameter (optional).
        value: Tuple of credential strings.

    Returns:
        A dictionary mapping credential keys to values.

    Raises:
        click.BadParameter: If any credential is not in KEY=VALUE format.
    """
    creds = {}
    for item in value:
        if "=" not in item:
            raise click.BadParameter(f"Credential '{item}' must be in KEY=VALUE format.")
        k, v = item.split("=", 1)
        creds[k.strip()] = v.strip()
    return creds


async def run_cli_tests(
    project_name: str | None,
    test_name: str | None,
    url: str | None,
    prompt: str | None,
    model: str | None,
    api_base: str | None,
    max_steps: int | None,
    headless: bool | None,
    ignore_https_errors: bool | None,
    credentials_override: dict[str, str],
    debug: bool,
) -> int:
    """Executes the test run using the specified parameters.

    Args:
        project_name: The name of the saved project to run tests for.
        test_name: The name of a specific test case within the project.
        url: Custom target URL for an ad-hoc run.
        prompt: Custom instruction prompt for an ad-hoc run.
        model: LiteLLM model override.
        api_base: API base URL override.
        max_steps: Maximum step limit override.
        headless: Headless browser mode override.
        ignore_https_errors: SSL validation behavior override.
        credentials_override: Dictionary of credential overrides.
        debug: Whether to print full tracebacks on exceptions.

    Returns:
        An exit code integer (0 for all success, 1 if any failure occurs).

    Raises:
        click.UsageError: If the input parameters are invalid.
    """
    if project_name:
        try:
            config = project_manager.load_project(project_name)
        except FileNotFoundError as e:
            raise click.UsageError(f"Project '{project_name}' not found.") from e

        # Apply CLI overrides to project config
        if model is not None:
            config.model = model
        if api_base is not None:
            config.api_base = api_base
        if max_steps is not None:
            config.max_steps = max_steps
        if headless is not None:
            config.headless = headless
        if ignore_https_errors is not None:
            config.ignore_https_errors = ignore_https_errors
        config.credentials.update(credentials_override)

        # Resolve which test cases to run
        if test_name:
            tests_to_run = [t for t in config.tests if t.name.lower() == test_name.lower()]
            if not tests_to_run:
                raise click.UsageError(
                    f"Test case '{test_name}' not found in project '{project_name}'."
                )
        else:
            tests_to_run = config.tests
            if not tests_to_run:
                console.print(
                    f"[yellow]Warning: Project '{project_name}' contains no test cases.[/yellow]"
                )
                return 0

    elif url and prompt:
        # Create an ad-hoc configuration
        config = ProjectConfig(
            name="Ad-hoc CLI Run",
            target_url=url,
            model=model or "openai/gpt-4o",
            api_base=api_base,
            max_steps=max_steps or 15,
            headless=headless if headless is not None else True,
            ignore_https_errors=ignore_https_errors if ignore_https_errors is not None else False,
            credentials=credentials_override,
            tests=[TestCase(name="Ad-hoc Test", description=prompt)],
        )
        tests_to_run = config.tests

    else:
        raise click.UsageError(
            "Must specify either --project or both --url and --prompt to execute tests."
        )

    def cli_callback(event_type: str, data: dict[str, Any]) -> None:
        """Callback to handle and format events from the QABrowserAgent."""
        if event_type == "log":
            msg = data.get("message", "")
            level = data.get("level", "info")
            styled_text = Text()

            if level == "thought":
                styled_text.append("💭 [Thought] ", style="italic yellow")
                styled_text.append(msg, style="italic dim yellow")
            elif level == "action":
                styled_text.append("⚙️ [Action] ", style="bold cyan")
                styled_text.append(msg, style="cyan")
            elif level == "error":
                styled_text.append("❌ [Error]  ", style="bold red")
                styled_text.append(msg, style="red")
            elif level == "success":
                styled_text.append("✅ [Success] ", style="bold green")
                styled_text.append(msg, style="green")
            else:
                styled_text.append("ℹ️ [Info]    ", style="bold white")
                styled_text.append(msg, style="white")

            console.print(styled_text)
        elif event_type == "status":
            if "state" in data:
                state_str = data["state"]
                console.print(f"[bold magenta]ℹ️ [Status][/bold magenta] [magenta]{state_str}[/magenta]")

    success_count = 0
    total_tests = len(tests_to_run)

    for idx, test_case in enumerate(tests_to_run, 1):
        console.print(Rule(f"[bold blue]STARTING TEST CASE {idx}/{total_tests}: '{test_case.name}'[/bold blue]"))

        browser_service = BrowserService(
            headless=config.headless,
            ignore_https_errors=config.ignore_https_errors,
        )
        llm_client = LLMClient(
            model=config.model,
            api_base=config.api_base,
        )
        agent = QABrowserAgent(browser_service, llm_client)

        steps_limit = (
            test_case.max_steps
            if test_case.max_steps is not None
            else config.max_steps
        )

        try:
            report = await agent.run_task(
                target_url=config.target_url,
                task_description=test_case.description,
                max_steps=steps_limit,
                credentials=config.credentials,
                update_callback=cli_callback,
            )

            if report.status == "success":
                success_count += 1
                console.print(Rule(f"[bold green]TEST CASE '{test_case.name}' PASSED[/bold green]"))
            else:
                console.print(Rule(f"[bold red]TEST CASE '{test_case.name}' FAILED: {report.error_message}[/bold red]"))
        except Exception as e:
            console.print(Rule(f"[bold red]TEST CASE '{test_case.name}' ENCOUNTERED EXCEPTION: {e}[/bold red]"))
            if debug:
                raise

    all_passed = (success_count == total_tests)
    console.print()
    console.print(Rule("[bold]EXECUTION SUMMARY[/bold]"))
    console.print(f"Total Tests Run: {total_tests}")
    console.print(f"Passed: [green]{success_count}[/green]")
    console.print(f"Failed: [red]{total_tests - success_count}[/red]")

    if all_passed:
        console.print("[bold green]All tests completed successfully.[/bold green]")
        return 0
    else:
        console.print("[bold red]Some tests failed.[/bold red]")
        return 1


@click.command()
@click.option("--project", help="Name of the project to load.")
@click.option("--test", help="Name of the test case to run (runs all if omitted).")
@click.option("--url", help="Target URL for running a custom prompt.")
@click.option("--prompt", help="Custom natural language instruction to execute.")
@click.option("--model", help="LiteLLM model identifier to override.")
@click.option("--api-base", help="Optional local Ollama base URL to override.")
@click.option("--max-steps", type=int, help="Maximum step limit override.")
@click.option(
    "--headless/--no-headless",
    default=None,
    help="Force headless or headed browser mode.",
)
@click.option(
    "--ignore-https-errors/--no-ignore-https-errors",
    default=None,
    help="Ignore HTTPS certificate errors.",
)
@click.option(
    "--credential",
    "-c",
    multiple=True,
    help="Credentials in KEY=VALUE format.",
)
@click.option("--list-projects", is_flag=True, help="List all saved projects and exit.")
@click.option("--tui", is_flag=True, help="Explicitly launch the Textual TUI.")
@click.option(
    "--debug",
    is_flag=True,
    help="Enable debug mode to show full stack traces on error.",
)
def cli(
    project: str | None,
    test: str | None,
    url: str | None,
    prompt: str | None,
    model: str | None,
    api_base: str | None,
    max_steps: int | None,
    headless: bool | None,
    ignore_https_errors: bool | None,
    credential: tuple[str, ...],
    list_projects: bool,
    tui: bool,
    debug: bool,
) -> None:
    """Python Interactive Testing Agent (pita) Command Line Interface."""
    if tui:
        # Import dynamically to avoid loading textual components unnecessarily
        from src.tui.app import PitaApp

        app = PitaApp()
        app.run()
        return

    if list_projects:
        projects = project_manager.list_projects()
        if not projects:
            console.print("[yellow]No saved projects found.[/yellow]")
        else:
            console.print("[bold green]Saved Projects:[/bold green]")
            for p in projects:
                console.print(f" - {p}")
        return

    try:
        if not project and not (url and prompt):
            raise click.UsageError(
                "Must specify either --project or both --url and --prompt to execute tests."
            )

        credentials_override = parse_credentials(None, None, credential)

        exit_code = asyncio.run(
            run_cli_tests(
                project_name=project,
                test_name=test,
                url=url,
                prompt=prompt,
                model=model,
                api_base=api_base,
                max_steps=max_steps,
                headless=headless,
                ignore_https_errors=ignore_https_errors,
                credentials_override=credentials_override,
                debug=debug,
            )
        )
        sys.exit(exit_code)
    except click.ClickException:
        raise
    except Exception as e:
        if debug:
            raise
        console.print(f"[bold red]Error:[/bold red] {e}")
        sys.exit(1)



if __name__ == "__main__":
    cli()
