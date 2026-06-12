"""Textual terminal user interface application for pita.

Coordinates the main window, sidebar input fields, reactive widgets, and
background worker orchestrations.
"""

import asyncio
from typing import Any

from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import Button, Footer, Header, Input, Label
from textual.worker import Worker

from src.core.agent import QABrowserAgent
from src.infrastructure.browser_service import BrowserService
from src.infrastructure.llm_client import LLMClient
from src.tui.widgets.log_viewer import LogViewer
from src.tui.widgets.status_panel import StatusPanel


class PitaApp(App[None]):
    """Main Textual application for pita (Python Interactive Testing Agent)."""

    CSS_PATH = "style.tcss"
    BINDINGS = [
        ("q", "quit", "Quit Application"),
        ("c", "clear_logs", "Clear Logs View"),
    ]

    def compose(self) -> ComposeResult:
        """Composes the application layout."""
        yield Header(show_clock=True)

        with Container(id="main-container"):
            # Left panel - Configuration
            with Vertical(id="left-container"):
                yield Label("Target URL", classes="field-label")
                yield Input(
                    value="https://the-internet.herokuapp.com/login",
                    placeholder="Enter URL to test...",
                    id="inp_url"
                )

                yield Label("Task Description (Soft Prompt)", classes="field-label")
                yield Input(
                    value="Log in with username 'tomsmith' and password 'SuperSecretPassword!', then verify that the secure area is loaded.",
                    placeholder="Describe testing goal...",
                    id="inp_task"
                )

                yield Label("LLM Model", classes="field-label")
                yield Input(
                    value="openai/gpt-4o",
                    placeholder="e.g. ollama/llama3 or openai/gpt-4o...",
                    id="inp_model"
                )

                yield Label("Ollama / API Base URL (Optional)", classes="field-label")
                yield Input(
                    value="",
                    placeholder="e.g. http://localhost:11434 (leave empty for cloud API keys)...",
                    id="inp_api_base"
                )

                yield Label("Max Steps", classes="field-label")
                yield Input(
                    value="15",
                    placeholder="Limit steps...",
                    id="inp_max_steps"
                )

                with Horizontal(id="buttons-row"):
                    yield Button("Start Run", id="btn_start")
                    yield Button("Cancel", id="btn_stop", disabled=True)

            # Right panel - Running view
            with Vertical(id="right-container"):
                yield StatusPanel(id="status_panel")
                yield LogViewer(id="log_viewer")

        yield Footer()

    def on_mount(self) -> None:
        """Prepares widget references once the application is mounted."""
        self.status_panel = self.query_one("#status_panel", StatusPanel)
        self.log_viewer = self.query_one("#log_viewer", LogViewer)
        self.btn_start = self.query_one("#btn_start", Button)
        self.btn_stop = self.query_one("#btn_stop", Button)
        self.agent_worker: Worker[None] | None = None

    def action_clear_logs(self) -> None:
        """Clears the LogViewer terminal widget."""
        self.log_viewer.clear()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles button clicks."""
        if event.button.id == "btn_start":
            await self.start_agent_run()
        elif event.button.id == "btn_stop":
            await self.cancel_agent_run()

    async def start_agent_run(self) -> None:
        """Starts the autonomous test loop as a background task."""
        url = self.query_one("#inp_url", Input).value.strip()
        task = self.query_one("#inp_task", Input).value.strip()
        model = self.query_one("#inp_model", Input).value.strip()
        api_base = self.query_one("#inp_api_base", Input).value.strip()
        max_steps_str = self.query_one("#inp_max_steps", Input).value.strip()

        if not url or not task:
            self.log_viewer.write_log("Target URL and Task Description cannot be empty.", "error")
            return

        try:
            max_steps = int(max_steps_str)
        except ValueError:
            max_steps = 15

        # Update button state
        self.btn_start.disabled = True
        self.btn_stop.disabled = False

        # Toggle inputs disablement for stability during run
        for inp_id in ("#inp_url", "#inp_task", "#inp_model", "#inp_api_base", "#inp_max_steps"):
            self.query_one(inp_id, Input).disabled = True

        # Launch background worker
        self.agent_worker = self.run_worker(
            self._execute_agent_loop(url, task, model, api_base, max_steps),
            exclusive=True
        )

    async def cancel_agent_run(self) -> None:
        """Cancels the active agent run worker."""
        if self.agent_worker:
            self.log_viewer.write_log("Cancellation requested. Stopping agent...", "error")
            self.agent_worker.cancel()
            self.btn_stop.disabled = True

    async def _execute_agent_loop(
        self, url: str, task: str, model: str, api_base: str, max_steps: int
    ) -> None:
        """Background execution worker loop."""
        api_base_opt = api_base if api_base else None

        # Build callback handler
        def agent_callback(event_type: str, data: dict[str, Any]) -> None:
            # Safely schedule execution onto Textual app main loop
            self.call_next(self._handle_agent_event, event_type, data)

        try:
            browser_service = BrowserService(headless=True)
            llm_client = LLMClient(model=model, api_base=api_base_opt)
            agent = QABrowserAgent(browser_service, llm_client)

            await agent.run_task(
                target_url=url,
                task_description=task,
                max_steps=max_steps,
                update_callback=agent_callback
            )

        except asyncio.CancelledError:
            # Handle user manual cancel
            self.log_viewer.write_log("Agent execution was cancelled by the user.", "error")
            self.status_panel.state_desc = "Finished (Cancelled)"
        except Exception as e:
            self.log_viewer.write_log(f"Unhandled agent exception: {e}", "error")
            self.status_panel.state_desc = f"Finished (Error: {e})"
        finally:
            # Re-enable inputs
            self.btn_start.disabled = False
            self.btn_stop.disabled = True
            for inp_id in ("#inp_url", "#inp_task", "#inp_model", "#inp_api_base", "#inp_max_steps"):
                self.query_one(inp_id, Input).disabled = False
            self.agent_worker = None

    def _handle_agent_event(self, event_type: str, data: dict[str, Any]) -> None:
        """Processes events dispatched by the agent in the main thread."""
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
