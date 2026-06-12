"""Unit tests for the CLI entry point."""

from unittest.mock import AsyncMock, MagicMock, patch

from click.testing import CliRunner

from src.cli import cli
from src.core.models import ProjectConfig, TestCase, TestReport


def test_cli_list_projects() -> None:
    """Verifies that --list-projects option prints the list of projects."""
    runner = CliRunner()
    with patch("src.cli.project_manager.list_projects") as mock_list:
        mock_list.return_value = ["Project A", "Project B"]
        result = runner.invoke(cli, ["--list-projects"])
        assert result.exit_code == 0
        assert "Saved Projects:" in result.output
        assert "Project A" in result.output
        assert "Project B" in result.output


def test_cli_list_projects_empty() -> None:
    """Verifies output when no projects are saved."""
    runner = CliRunner()
    with patch("src.cli.project_manager.list_projects") as mock_list:
        mock_list.return_value = []
        result = runner.invoke(cli, ["--list-projects"])
        assert result.exit_code == 0
        assert "No saved projects found." in result.output


def test_cli_tui_launch() -> None:
    """Verifies that launching with --tui runs the PitaApp."""
    runner = CliRunner()
    with patch("src.tui.app.PitaApp") as mock_app_class:
        mock_app = MagicMock()
        mock_app_class.return_value = mock_app
        result = runner.invoke(cli, ["--tui"])
        assert result.exit_code == 0
        mock_app.run.assert_called_once()


def test_cli_invalid_options() -> None:
    """Verifies usage error when neither project nor custom URL/prompt are provided."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--headless"])
    assert result.exit_code != 0
    assert "Error: Must specify either --project or both --url and --prompt to execute tests." in result.output


def test_cli_credential_parsing_error() -> None:
    """Verifies bad parameter error when credentials are not in key=value format."""
    runner = CliRunner()
    result = runner.invoke(cli, ["--url", "http://test.com", "--prompt", "test", "-c", "invalid_format"])
    assert result.exit_code != 0
    assert "Credential 'invalid_format' must be in KEY=VALUE format." in result.output



@patch("src.cli.QABrowserAgent")
def test_cli_run_custom_success(mock_agent_class: MagicMock) -> None:
    """Verifies successful custom ad-hoc test run."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_report = TestReport(
        target_url="http://test.com",
        task_description="test prompt",
        steps=[],
        status="success",
    )
    mock_agent.run_task = AsyncMock(return_value=mock_report)
    mock_agent_class.return_value = mock_agent

    result = runner.invoke(
        cli,
        [
            "--url",
            "http://test.com",
            "--prompt",
            "test prompt",
            "--headless",
            "-c",
            "user=test_val",
        ],
    )
    assert result.exit_code == 0
    assert "TEST CASE 'Ad-hoc Test' PASSED" in result.output
    assert "All tests completed successfully." in result.output


@patch("src.cli.QABrowserAgent")
def test_cli_run_custom_failure(mock_agent_class: MagicMock) -> None:
    """Verifies CLI exit code and output on test failure."""
    runner = CliRunner()

    mock_agent = MagicMock()
    mock_report = TestReport(
        target_url="http://test.com",
        task_description="test prompt",
        steps=[],
        status="failure",
        error_message="Could not find element",
    )
    mock_agent.run_task = AsyncMock(return_value=mock_report)
    mock_agent_class.return_value = mock_agent

    result = runner.invoke(cli, ["--url", "http://test.com", "--prompt", "test prompt"])
    assert result.exit_code == 1
    assert "TEST CASE 'Ad-hoc Test' FAILED: Could not find element" in result.output
    assert "Some tests failed." in result.output


@patch("src.cli.QABrowserAgent")
@patch("src.cli.project_manager.load_project")
def test_cli_run_project(
    mock_load_project: MagicMock, mock_agent_class: MagicMock
) -> None:
    """Verifies running tests from a project file."""
    runner = CliRunner()

    config = ProjectConfig(
        name="Project X",
        target_url="https://x.com",
        model="openai/gpt-4o",
        api_base=None,
        max_steps=5,
        tests=[
            TestCase(name="Test1", description="desc1"),
            TestCase(name="Test2", description="desc2"),
        ],
    )
    mock_load_project.return_value = config

    mock_agent = MagicMock()
    mock_report_success = TestReport(
        target_url="https://x.com",
        task_description="desc1",
        steps=[],
        status="success",
    )
    mock_report_failed = TestReport(
        target_url="https://x.com",
        task_description="desc2",
        steps=[],
        status="failure",
        error_message="timeout",
    )
    mock_agent.run_task = AsyncMock(
        side_effect=[mock_report_success, mock_report_failed]
    )
    mock_agent_class.return_value = mock_agent

    result = runner.invoke(cli, ["--project", "Project X"])
    assert result.exit_code == 1
    assert "STARTING TEST CASE 1/2: 'Test1'" in result.output
    assert "TEST CASE 'Test1' PASSED" in result.output
    assert "STARTING TEST CASE 2/2: 'Test2'" in result.output
    assert "TEST CASE 'Test2' FAILED: timeout" in result.output
    assert "Total Tests Run: 2" in result.output
    assert "Passed: 1" in result.output
    assert "Failed: 1" in result.output
