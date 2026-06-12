"""Custom LogViewer widget for the Textual UI.

Provides rich text formatting for agent logs, dividing them into thoughts,
actions, errors, and success statuses.
"""

from typing import Any

from rich.text import Text
from textual.widgets import RichLog


class LogViewer(RichLog):
    """Custom RichLog widget that supports semantic color styling."""

    def __init__(self, **kwargs: Any) -> None:
        """Initializes the LogViewer with scrolling options."""
        super().__init__(highlight=True, markup=True, wrap=True, **kwargs)

    def write_log(self, message: str, level: str = "info") -> None:
        """Writes a styled log message to the log screen.

        Args:
            message: The raw text log.
            level: Semantic category (thought, action, error, success, info).
        """
        styled_text = Text()

        if level == "thought":
            styled_text.append("💭 [Thought] ", style="italic yellow")
            styled_text.append(message, style="italic dim yellow")
        elif level == "action":
            styled_text.append("⚙️ [Action] ", style="bold cyan")
            styled_text.append(message, style="cyan")
        elif level == "error":
            styled_text.append("❌ [Error]  ", style="bold red")
            styled_text.append(message, style="red")
        elif level == "success":
            styled_text.append("✅ [Success] ", style="bold green")
            styled_text.append(message, style="green")
        else:
            styled_text.append("ℹ️ [Info]    ", style="bold white")
            styled_text.append(message, style="white")

        self.write(styled_text)
