"""Textual terminal user interface application for pita.

Coordinates the main window, project management tabs, test execution,
live logs, and background worker threads.
"""

import asyncio
from typing import Any

from rich.panel import Panel
from rich.table import Table
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Button,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    SelectionList,
    Static,
    TabbedContent,
    TabPane,
)
from textual.worker import Worker

from src.core import project_manager
from src.core.agent import QABrowserAgent
from src.core.models import ProjectConfig, TestCase
from src.infrastructure.browser_service import BrowserService
from src.infrastructure.llm_client import LLMClient
from src.tui.screens.project_form import ProjectFormScreen
from src.tui.widgets.log_viewer import LogViewer
from src.tui.widgets.status_panel import StatusPanel


class PitaApp(App[None]):
    """Main Textual application for pita (Python Interactive Testing Agent)."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        ("q", "quit", "Quit Application"),
        ("c", "clear_logs", "Clear Logs View"),
        ("n", "new_project", "New Project"),
        ("e", "edit_project", "Edit Project"),
        ("d", "delete_project", "Delete Project"),
        ("l", "load_project", "Load Project"),
        ("r", "run_selected", "Run Selected Tests"),
        ("a", "run_all_tests", "Run All Tests"),
        ("s", "stop_run", "Stop Run"),
    ]

    def compose(self) -> ComposeResult:
        """Composes the application layout with tabbed content panels."""
        yield Header(show_clock=True)

        with TabbedContent(id="tui_tabs"):
            # Tab 1: Project Manager
            with TabPane("Manage Projects", id="tab_manage_projects"):
                with Container(id="manage-projects-container"):
                    with Vertical(id="projects-list-col"):
                        yield Label("Saved Projects", classes="panel-title")
                        yield OptionList(id="list_projects")
                        with Horizontal(classes="buttons-row-small"):
                            yield Button(
                                "New Project", id="btn_new_project", variant="success"
                            )
                            yield Button(
                                "Edit Selected",
                                id="btn_edit_project",
                                variant="primary",
                            )
                            yield Button(
                                "Delete Selected",
                                id="btn_delete_project",
                                variant="error",
                            )
                        yield Button(
                            "LOAD HIGHLIGHTED PROJECT",
                            id="btn_load_project",
                            variant="primary",
                        )

                    with Vertical(id="project-details-col"):
                        yield Label("Project Preview Details", classes="panel-title")
                        yield Static(id="project_details_view")

            # Tab 2: Test Case Runner
            with TabPane("Execute Tests", id="tab_execute_tests"):
                with Vertical(id="runner-panel-container"):
                    yield Label("Loaded Project Context", classes="panel-title")
                    yield Static(id="runner_project_context")

                    yield Label(
                        "Select Predefined Tests to Execute", classes="panel-title"
                    )
                    yield SelectionList[int](id="list_test_cases")

                    with Horizontal(classes="buttons-row-small"):
                        yield Button(
                            "Run Selected Tests",
                            id="btn_run_selected",
                            variant="success",
                        )
                        yield Button(
                            "Run All Tests", id="btn_run_all", variant="primary"
                        )

                    yield Label(
                        "Or Run a Custom Prompt (Soft Prompt)", classes="panel-title"
                    )
                    yield Input(
                        placeholder="e.g. Verify that clicking the logo redirects to the homepage...",
                        id="inp_custom_prompt",
                    )
                    yield Button(
                        "Run Custom Prompt", id="btn_run_custom", variant="primary"
                    )

            # Tab 3: Console live logs monitor
            with TabPane("Console Monitor", id="tab_console_monitor"):
                with Vertical(id="monitor-container"):
                    yield StatusPanel(id="status_panel")
                    with Horizontal(id="monitor-actions-row"):
                        yield Button(
                            "CANCEL ACTIVE RUN",
                            id="btn_stop",
                            variant="error",
                            disabled=True,
                        )
                    yield LogViewer(id="log_viewer")

        yield Footer()

    def on_mount(self) -> None:
        """Prepares references, loads initial configurations, and sets up state."""
        self.status_panel = self.query_one("#status_panel", StatusPanel)
        self.log_viewer = self.query_one("#log_viewer", LogViewer)
        self.btn_stop = self.query_one("#btn_stop", Button)

        self.list_projects = self.query_one("#list_projects", OptionList)
        self.project_details_view = self.query_one("#project_details_view", Static)
        self.runner_project_context = self.query_one("#runner_project_context", Static)
        self.list_test_cases = self.query_one("#list_test_cases", SelectionList)

        self.tabs = self.query_one("#tui_tabs", TabbedContent)

        self.agent_worker: Worker[None] | None = None
        self.loaded_project: ProjectConfig | None = None
        self.is_cancelling = False

        # Populate project file list
        self._reload_projects_list()

        # Auto-load the first project on startup if available
        projects = project_manager.list_projects()
        if projects:
            self.run_worker(self._load_project_to_runner(projects[0], switch_tab=False))

    def _reload_projects_list(self) -> None:
        """Loads project files from disk and repopulates the options list."""
        self.list_projects.clear_options()
        projects = project_manager.list_projects()
        for p in projects:
            self.list_projects.add_option(p)

        if not projects:
            self.project_details_view.update(
                Panel(
                    "[bold red]No saved projects found.[/bold red]\n\nClick 'New Project' below to create one.",
                    border_style="red",
                )
            )
        else:
            # Highlight first item and refresh details
            self.list_projects.highlighted = 0
            self._update_details_view(projects[0])

    def _update_details_view(self, name: str) -> None:
        """Loads and formats project metadata table inside the details preview block."""
        try:
            config = project_manager.load_project(name)
            table = Table.grid(padding=(0, 2))
            table.add_column("Property", style="bold magenta")
            table.add_column("Value", style="white")

            table.add_row("Name:", config.name)
            table.add_row("Target URL:", config.target_url)
            table.add_row("LiteLLM Model:", config.model)
            table.add_row("Base URL:", config.api_base or "Default API Base")
            table.add_row("Max Steps Limit:", str(config.max_steps))
            table.add_row(
                "Ignore HTTPS Errors:",
                "Yes" if config.ignore_https_errors else "No",
            )

            creds_keys = (
                ", ".join(config.credentials.keys()) if config.credentials else "None"
            )
            table.add_row("Credentials:", creds_keys)

            table.add_row("Test Cases Count:", str(len(config.tests)))

            self.project_details_view.update(
                Panel(
                    table,
                    title=f"[bold green]Project: {config.name}[/bold green]",
                    border_style="blue",
                )
            )
        except Exception as e:
            self.project_details_view.update(
                Panel(
                    f"[bold red]Failed to load project details: {e}[/bold red]",
                    border_style="red",
                )
            )

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """Dynamically updates the preview pane when a different project file is highlighted."""
        if event.option_list.id == "list_projects" and event.option_index is not None:
            project_name = event.option_list.get_option_at_index(
                event.option_index
            ).prompt
            # Option list items display_name could have spaces
            self._update_details_view(str(project_name))

    async def on_option_list_option_selected(
        self, event: OptionList.OptionSelected
    ) -> None:
        """Loads the project when an option in the list is selected (e.g., Enter pressed)."""
        if event.option_list.id == "list_projects" and event.option_index is not None:
            project_name = str(
                event.option_list.get_option_at_index(event.option_index).prompt
            )
            await self._load_project_to_runner(project_name)

    def action_clear_logs(self) -> None:
        """Clears the LogViewer screen."""
        self.log_viewer.clear()

    def action_new_project(self) -> None:
        """Hotkey to open 'New Project' modal if on project tab."""
        if self.tabs.active == "tab_manage_projects":
            self._on_new_project_pressed()

    def action_edit_project(self) -> None:
        """Hotkey to edit selected project if on project tab."""
        if self.tabs.active == "tab_manage_projects":
            self._on_edit_project_pressed()

    def action_delete_project(self) -> None:
        """Hotkey to delete selected project if on project tab."""
        if self.tabs.active == "tab_manage_projects":
            self._on_delete_project_pressed()

    async def action_load_project(self) -> None:
        """Hotkey to load selected project if on project tab."""
        if self.tabs.active == "tab_manage_projects":
            await self._on_load_project_pressed()

    async def action_run_selected(self) -> None:
        """Hotkey to run selected tests if on runner tab."""
        if self.tabs.active == "tab_execute_tests":
            await self.start_tests_run(run_mode="selected")

    async def action_run_all_tests(self) -> None:
        """Hotkey to run all tests if on runner tab."""
        if self.tabs.active == "tab_execute_tests":
            await self.start_tests_run(run_mode="all")

    async def action_stop_run(self) -> None:
        """Hotkey to cancel active run."""
        if not self.btn_stop.disabled:
            await self.cancel_active_run()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles screen button press events."""
        btn_id = event.button.id

        if btn_id == "btn_new_project":
            self._on_new_project_pressed()
        elif btn_id == "btn_edit_project":
            self._on_edit_project_pressed()
        elif btn_id == "btn_delete_project":
            self._on_delete_project_pressed()
        elif btn_id == "btn_load_project":
            await self._on_load_project_pressed()
        elif btn_id == "btn_run_selected":
            await self.start_tests_run(run_mode="selected")
        elif btn_id == "btn_run_all":
            await self.start_tests_run(run_mode="all")
        elif btn_id == "btn_run_custom":
            await self.start_tests_run(run_mode="custom")
        elif btn_id == "btn_stop":
            await self.cancel_active_run()

    def _on_new_project_pressed(self) -> None:
        """Handles the 'New Project' button action."""
        self.push_screen(ProjectFormScreen(), self._handle_project_created)

    def _on_edit_project_pressed(self) -> None:
        """Handles the 'Edit Selected' button action."""
        if self.list_projects.highlighted is not None:
            name = str(
                self.list_projects.get_option_at_index(
                    self.list_projects.highlighted
                ).prompt
            )
            try:
                config = project_manager.load_project(name)
                self.push_screen(ProjectFormScreen(config), self._handle_project_edited)
            except Exception as e:
                self.log_viewer.write_log(
                    f"Failed to load project for editing: {e}", "error"
                )

    def _on_delete_project_pressed(self) -> None:
        """Handles the 'Delete Selected' button action."""
        if self.list_projects.highlighted is not None:
            name = str(
                self.list_projects.get_option_at_index(
                    self.list_projects.highlighted
                ).prompt
            )
            try:
                project_manager.delete_project(name)
                self.log_viewer.write_log(f"Deleted project: {name}", "success")
                if self.loaded_project and self.loaded_project.name == name:
                    self.loaded_project = None
                    self.runner_project_context.update("[bold yellow]No project loaded.[/bold yellow]")
                    self.list_test_cases.clear_options()
                self._reload_projects_list()
            except Exception as e:
                self.log_viewer.write_log(f"Failed to delete project: {e}", "error")

    async def _on_load_project_pressed(self) -> None:
        """Handles the 'LOAD HIGHLIGHTED PROJECT' button action."""
        if self.list_projects.highlighted is not None:
            name = str(
                self.list_projects.get_option_at_index(
                    self.list_projects.highlighted
                ).prompt
            )
            await self._load_project_to_runner(name)

    def _handle_project_created(self, config: ProjectConfig | None) -> None:
        """Callback triggered after ProjectFormScreen dismisses for a new project."""
        if config:
            try:
                project_manager.save_project(config)
                self.log_viewer.write_log(
                    f"Created new project: {config.name}", "success"
                )
                self._reload_projects_list()
            except Exception as e:
                self.log_viewer.write_log(f"Failed to save new project: {e}", "error")

    def _handle_project_edited(self, config: ProjectConfig | None) -> None:
        """Callback triggered after ProjectFormScreen dismisses for an edited project."""
        if config:
            try:
                project_manager.save_project(config)
                self.log_viewer.write_log(
                    f"Updated project details: {config.name}", "success"
                )
                self._reload_projects_list()
                if self.loaded_project and self.loaded_project.name == config.name:
                    self.run_worker(self._load_project_to_runner(config.name, switch_tab=False))
            except Exception as e:
                self.log_viewer.write_log(f"Failed to save project edits: {e}", "error")

    async def _load_project_to_runner(self, name: str, switch_tab: bool = True) -> None:
        """Loads project config into active state and populates the runner selection widgets."""
        try:
            self.loaded_project = project_manager.load_project(name)

            # Update contexts labels
            self.runner_project_context.update(
                f"[bold green]Loaded Project:[/bold green] {self.loaded_project.name} | "
                f"[bold green]URL:[/bold green] {self.loaded_project.target_url} | "
                f"[bold green]Model:[/bold green] {self.loaded_project.model}"
            )

            # Populate SelectionList tests options
            self.list_test_cases.clear_options()
            for i, t in enumerate(self.loaded_project.tests):
                self.list_test_cases.add_option((t.name, i))

            # Select all by default
            for i in range(len(self.loaded_project.tests)):
                self.list_test_cases.select(i)

            self.log_viewer.write_log(
                f"Project '{name}' successfully loaded into runner.", "success"
            )

            # Direct switch tabs for better navigation
            if switch_tab:
                self.tabs.active = "tab_execute_tests"
        except Exception as e:
            self.log_viewer.write_log(f"Failed to load project: {e}", "error")

    async def start_tests_run(self, run_mode: str) -> None:
        """Starts test execution run in background."""
        if not self.loaded_project:
            self.tabs.active = "tab_console_monitor"
            self.log_viewer.write_log(
                "No project loaded. Please load a project first.", "error"
            )
            return

        test_tasks: list[TestCase] = []

        if run_mode == "all":
            test_tasks = list(self.loaded_project.tests)
        elif run_mode == "selected":
            selected_indices = self.list_test_cases.selected
            test_tasks = [self.loaded_project.tests[idx] for idx in selected_indices]
        elif run_mode == "custom":
            prompt_input = self.query_one("#inp_custom_prompt", Input).value.strip()
            if not prompt_input:
                self.log_viewer.write_log("Custom prompt cannot be empty.", "error")
                return
            test_tasks = [TestCase(name="Custom Run", description=prompt_input)]

        if not test_tasks:
            self.log_viewer.write_log("No tests selected for execution.", "error")
            return

        # Disable all UI interaction widgets for stability
        self._toggle_ui_state(enabled=False)

        # Switch screen view to monitor
        self.tabs.active = "tab_console_monitor"

        self.is_cancelling = False
        self.btn_stop.disabled = False

        # Spawn execution worker
        self.agent_worker = self.run_worker(
            self._execute_tests_worker(test_tasks), exclusive=True
        )

    async def cancel_active_run(self) -> None:
        """Requests active runner cancellation."""
        if self.agent_worker:
            self.is_cancelling = True
            self.log_viewer.write_log(
                "Run cancellation requested. Stopping active test loop...", "error"
            )
            self.agent_worker.cancel()
            self.btn_stop.disabled = True

    def _toggle_ui_state(self, enabled: bool) -> None:
        """Enables/Disables start, load, and edit buttons during test execution."""
        for btn_id in (
            "#btn_new_project",
            "#btn_edit_project",
            "#btn_delete_project",
            "#btn_load_project",
            "#btn_run_selected",
            "#btn_run_all",
            "#btn_run_custom",
        ):
            self.query_one(btn_id, Button).disabled = not enabled
        self.query_one("#inp_custom_prompt", Input).disabled = not enabled

    async def _execute_tests_worker(self, tests: list[TestCase]) -> None:
        """Background worker iterating through the queue of selected tests."""
        assert self.loaded_project is not None

        def agent_callback(event_type: str, data: dict[str, Any]) -> None:
            self.call_next(self._handle_agent_event, event_type, data)

        try:
            total_tests = len(tests)
            for idx, t_case in enumerate(tests, 1):
                if self.is_cancelling:
                    break

                test_banner = (
                    f"--- STARTING TEST CASE {idx}/{total_tests}: '{t_case.name}' ---"
                )
                self.log_viewer.write_log(test_banner, "info")

                # Browser configuration parameters
                browser_service = BrowserService(
                    headless=True,
                    ignore_https_errors=self.loaded_project.ignore_https_errors,
                )
                llm_client = LLMClient(
                    model=self.loaded_project.model,
                    api_base=self.loaded_project.api_base,
                )
                agent = QABrowserAgent(browser_service, llm_client)

                steps_limit = (
                    t_case.max_steps
                    if t_case.max_steps
                    else self.loaded_project.max_steps
                )

                # Execute run
                report = await agent.run_task(
                    target_url=self.loaded_project.target_url,
                    task_description=t_case.description,
                    max_steps=steps_limit,
                    credentials=self.loaded_project.credentials,
                    update_callback=agent_callback,
                )

                status_msg = f"--- TEST CASE '{t_case.name}' FINISHED WITH STATUS: {report.status.upper()} ---"
                level = "success" if report.status == "success" else "error"
                self.log_viewer.write_log(status_msg, level)

        except asyncio.CancelledError:
            self.log_viewer.write_log("Execution loop cancelled by the user.", "error")
            self.status_panel.state_desc = "Finished (Cancelled)"
        except Exception as e:
            self.log_viewer.write_log(f"Test run loop failed: {e}", "error")
            self.status_panel.state_desc = f"Finished (Error: {e})"
        finally:
            self._toggle_ui_state(enabled=True)
            self.btn_stop.disabled = True
            self.agent_worker = None

    def _handle_agent_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Updates UI status and logger from agent background event dispatches."""
        if event_type == "status":
            if "state" in data:
                self.status_panel.state_desc = data["state"]
            if "url" in data:
                self.status_panel.current_url = data["url"]
            if "step" in data:
                self.status_panel.step = data["step"]
            if "max_steps" in data:
                self.status_panel.max_steps = data["max_steps"]
            if "trace_path" in data:
                self.status_panel.trace_path = data["trace_path"]
        elif event_type == "screenshot":
            self.status_panel.screenshot_path = data["path"]
        elif event_type == "log":
            self.log_viewer.write_log(data["message"], data.get("level", "info"))
