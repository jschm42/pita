"""Custom StatusPanel widget for the Textual UI.

Displays a high-level view of the current agent state, step counters, active URLs,
and paths to captured artifacts (screenshots, traces).
"""

from rich.panel import Panel
from rich.table import Table
from textual.reactive import reactive
from textual.widgets import Static


class StatusPanel(Static):
    """Visual panel representing the real-time execution state of the agent."""

    state_desc = reactive("Idle")
    current_url = reactive("N/A")
    step = reactive(0)
    max_steps = reactive(15)
    screenshot_path = reactive("N/A")
    trace_path = reactive("N/A")

    def render(self) -> Panel:
        """Renders the status panel into a beautiful, structured grid Table."""
        table = Table.grid(padding=(0, 2))
        table.add_column("Property", style="bold magenta")
        table.add_column("Value", style="bold white")

        # Color-code status descriptor
        state_style = "bold white"
        if "Success" in self.state_desc:
            state_style = "bold green"
        elif "Failure" in self.state_desc or "Error" in self.state_desc:
            state_style = "bold red"
        elif "Step" in self.state_desc:
            state_style = "bold cyan"

        table.add_row("Agent State:", f"[{state_style}]{self.state_desc}[/{state_style}]")
        table.add_row("Current URL:", self.current_url)

        step_text = f"{self.step} / {self.max_steps}" if self.step > 0 else "N/A"
        table.add_row("Current Step:", step_text)
        table.add_row("Screenshot:", self.screenshot_path)
        table.add_row("Trace Zip:", self.trace_path)

        return Panel(
            table,
            title="[bold yellow]QA Agent Dashboard[/bold yellow]",
            border_style="blue",
            expand=True,
        )
