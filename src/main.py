"""Entry point for the pita application.

Initializes environment variables, sets up logging to a file,
and launches the Textual TUI interface.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Enforce parent directory to be in PYTHONPATH to resolve 'src' package imports when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.tui.app import PitaApp  # noqa: E402

# Configure logging to write to a local file, keeping stdout clean for the TUI
logging.basicConfig(
    filename="pita.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point function loading config and running the Pita App."""
    logger.info("Initializing pita application...")
    load_dotenv()

    app = PitaApp()
    app.run()


if __name__ == "__main__":
    main()
