"""Entry point for the pita application.

Initializes environment variables, sets up logging to a file,
and launches either the Textual TUI interface or the command line interface.
"""

import logging
import os
import sys

from dotenv import load_dotenv

# Enforce parent directory to be in PYTHONPATH to resolve 'src' package imports when run directly
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Configure logging to write to a local file, keeping stdout clean for the TUI / CLI
logging.basicConfig(
    filename="pita.log",
    filemode="a",
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def main() -> None:
    """Entry point function routing to CLI or TUI mode based on arguments."""
    load_dotenv()

    # Route based on the presence of command-line arguments
    if len(sys.argv) > 1:
        logger.info("Initializing pita application in CLI mode...")
        from src.cli import cli
        cli()
    else:
        logger.info("Initializing pita application in TUI mode...")
        from src.tui.app import PitaApp

        app = PitaApp()
        app.run()


if __name__ == "__main__":
    main()

