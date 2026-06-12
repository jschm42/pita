"""Modal Screen for creating and editing Project Configurations."""

from textual.app import ComposeResult
from textual.containers import Horizontal, ScrollableContainer
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Input, Label, OptionList

from src.core.models import ProjectConfig, TestCase


class ProjectFormScreen(ModalScreen[ProjectConfig | None]):
    """Modal dialog screen containing inputs to define or update a ProjectConfig."""

    def __init__(self, config: ProjectConfig | None = None) -> None:
        """Initializes the form screen.

        Args:
            config: Optional existing ProjectConfig if editing.
        """
        super().__init__()
        self.config = config
        self.tests: list[TestCase] = list(config.tests) if config else []

    def compose(self) -> ComposeResult:
        """Composes the form inputs and layout."""
        is_edit = self.config is not None
        title = "Edit Project Configuration" if is_edit else "Create New Project"

        # Prepopulate values if editing
        name_val = self.config.name if self.config else ""
        url_val = self.config.target_url if self.config else ""
        model_val = self.config.model if self.config else "openai/gpt-4o"
        api_val = self.config.api_base if (self.config and self.config.api_base) else ""
        steps_val = str(self.config.max_steps) if self.config else "15"
        ignore_https_val = self.config.ignore_https_errors if self.config else False
        headless_val = self.config.headless if self.config else True

        # Prepopulate credentials if present
        user_val = ""
        pass_val = ""
        if self.config and self.config.credentials:
            user_val = self.config.credentials.get("username", "")
            pass_val = self.config.credentials.get("password", "")

        with ScrollableContainer(id="form-container"):
            yield Label(title, id="form-title")

            # Project base settings
            yield Label("Project Name *", classes="form-label")
            yield Input(
                value=name_val,
                placeholder="Enter unique project name...",
                id="proj_name",
                disabled=is_edit,  # File name rename safety
            )

            yield Label("Target Base URL *", classes="form-label")
            yield Input(
                value=url_val,
                placeholder="https://the-internet.herokuapp.com/login",
                id="proj_url",
            )

            yield Label("LiteLLM Model", classes="form-label")
            yield Input(
                value=model_val,
                placeholder="e.g. openai/gpt-4o, ollama/llama3",
                id="proj_model",
            )

            yield Label("Ollama / API Base URL (Optional)", classes="form-label")
            yield Input(
                value=api_val,
                placeholder="e.g. http://localhost:11434 (leave empty for default)",
                id="proj_api_base",
            )

            yield Label("Max Step Limit", classes="form-label")
            yield Input(
                value=steps_val,
                placeholder="Maximum step limit per test",
                id="proj_max_steps",
            )

            yield Checkbox(
                "Ignore HTTPS/SSL Certificate Errors",
                value=ignore_https_val,
                id="proj_ignore_https",
            )

            yield Checkbox(
                "Run Headless Browser (Invisible)",
                value=headless_val,
                id="proj_headless",
            )

            # Credentials sub-section
            yield Label("Credentials (Login Info)", classes="form-section-title")
            yield Label("Username / Email", classes="form-label")
            yield Input(
                value=user_val, placeholder="Optional login username", id="proj_user"
            )

            yield Label("Password", classes="form-label")
            yield Input(
                value=pass_val,
                placeholder="Optional login password",
                password=True,
                id="proj_pass",
            )

            # Predefined tests sub-section
            yield Label("Predefined Test Cases", classes="form-section-title")
            yield OptionList(id="proj_tests_list")

            with Horizontal(id="test-actions-row"):
                yield Button(
                    "Delete Selected Test", id="btn_delete_test", disabled=True
                )

            # Add test case input block
            yield Label("New Test Case", classes="form-label")
            yield Input(
                placeholder="Test Case Name (e.g. Success Login)", id="new_test_name"
            )
            yield Input(
                placeholder="Test Description / Soft Prompt (e.g. Log in and verify dashboard is loaded)",
                id="new_test_desc",
            )
            yield Button("Add Test Case", id="btn_add_test", variant="primary")

            # Main dialog buttons
            with Horizontal(id="form-buttons-row"):
                yield Button("Save Project", id="btn_save", variant="success")
                yield Button("Cancel", id="btn_cancel", variant="error")

    def on_mount(self) -> None:
        """Initializes the options list view once mounted."""
        self.tests_list = self.query_one("#proj_tests_list", OptionList)
        self.btn_delete_test = self.query_one("#btn_delete_test", Button)
        self._rebuild_tests_list()

    def _rebuild_tests_list(self) -> None:
        """Clears and repopulates the option list representation of preconfigured tests."""
        self.tests_list.clear_options()
        for t in self.tests:
            desc_preview = (
                t.description[:45] + "..." if len(t.description) > 45 else t.description
            )
            self.tests_list.add_option(f"{t.name}: {desc_preview}")
        self.btn_delete_test.disabled = True

    def on_option_list_option_highlighted(
        self, event: OptionList.OptionHighlighted
    ) -> None:
        """Enables deletion button when a test is selected."""
        self.btn_delete_test.disabled = event.option_index is None

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handles enter key presses inside test case input fields to add them automatically."""
        if event.input.id in ("new_test_name", "new_test_desc"):
            self._handle_add_test()

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handles screen buttons clicks."""
        btn_id = event.button.id

        if btn_id == "btn_cancel":
            self._handle_cancel()
        elif btn_id == "btn_add_test":
            self._handle_add_test()
        elif btn_id == "btn_delete_test":
            self._handle_delete_test()
        elif btn_id == "btn_save":
            self._handle_save()

    def _handle_cancel(self) -> None:
        """Closes the form screen without saving."""
        self.dismiss(None)

    def _handle_add_test(self) -> None:
        """Adds a new test case to the temporary tests list."""
        name_inp = self.query_one("#new_test_name", Input)
        desc_inp = self.query_one("#new_test_desc", Input)

        t_name = name_inp.value.strip()
        t_desc = desc_inp.value.strip()

        if t_name and t_desc:
            self.tests.append(TestCase(name=t_name, description=t_desc))
            self._rebuild_tests_list()
            name_inp.value = ""
            desc_inp.value = ""

    def _handle_delete_test(self) -> None:
        """Removes the selected test case from the list."""
        idx = self.tests_list.highlighted
        if idx is not None and 0 <= idx < len(self.tests):
            self.tests.pop(idx)
            self._rebuild_tests_list()

    def _handle_save(self) -> None:
        """Validates inputs, constructs the ProjectConfig, and dismisses screen."""
        name = self.query_one("#proj_name", Input).value.strip()
        url = self.query_one("#proj_url", Input).value.strip()
        model = self.query_one("#proj_model", Input).value.strip()
        api_base = self.query_one("#proj_api_base", Input).value.strip()
        max_steps_str = self.query_one("#proj_max_steps", Input).value.strip()

        user = self.query_one("#proj_user", Input).value.strip()
        pw = self.query_one("#proj_pass", Input).value.strip()
        ignore_https = self.query_one("#proj_ignore_https", Checkbox).value
        headless = self.query_one("#proj_headless", Checkbox).value

        if not name or not url:
            # Basic validation check
            return

        # Check if there is an unsaved/unadded test case in the inputs
        t_name = self.query_one("#new_test_name", Input).value.strip()
        t_desc = self.query_one("#new_test_desc", Input).value.strip()
        if t_name and t_desc:
            self.tests.append(TestCase(name=t_name, description=t_desc))

        try:
            max_steps = int(max_steps_str)
        except ValueError:
            max_steps = 15

        credentials = {}
        if user:
            credentials["username"] = user
        if pw:
            credentials["password"] = pw

        config = ProjectConfig(
            name=name,
            target_url=url,
            model=model,
            api_base=api_base if api_base else None,
            max_steps=max_steps,
            ignore_https_errors=ignore_https,
            headless=headless,
            credentials=credentials,
            tests=self.tests,
        )
        self.dismiss(config)
