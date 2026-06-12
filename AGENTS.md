# Best Practices & Guidelines for Python Console Applications (CLIs)

This document serves as a guideline and set of rules for developers and AI agents working on this Python console application. It ensures that the code remains clean, maintainable, robust, and well-tested.

---

## 1. Clean Code & Architecture

A good console application strictly separates the user interface (CLI interaction/TUI) from the business logic (Core logic).

### Project Structure
We prefer a clear `src/` layout or a flat package layout with separated modules:
- **`cli.py` or `__main__.py`**: Entry point, argument parsing, console input/output.
- **`core/` or Core modules**: Pure business logic, independent of console print outputs (`print`, `rich`, etc.).
- **`utils.py` / `helpers.py`**: Helper functions.

```text
project/
├── src/
│   └── my_project/
│       ├── __init__.py
│       ├── __main__.py      # Entry point
│       ├── cli.py           # CLI definition (click/typer/argparse)
│       ├── core.py          # Pure business logic
│       └── utils.py         # Helper functions
├── tests/
│   ├── __init__.py
│   ├── test_cli.py
│   └── test_core.py
├── pyproject.toml           # Configuration (Ruff, Pytest, Dependency Management)
└── README.md
```

### CLI Frameworks
Use modern libraries instead of manual `sys.argv` parsing:
* **[Typer](https://typer.tiangolo.com/)** (Recommended for intuitive, type-based CLIs) or **[Click](https://click.palletsprojects.com/)**.
* **[Rich](https://rich.readthedocs.io/)** for appealing console outputs (colors, tables, loading bars).

### Clean Code Rules
1. **Separation of Concerns**: No `print()` statements in the core logic. Use return values, exceptions, or the standard `logging` module instead.
2. **Type Hinting**: All function signatures must be consistently typed.
   ```python
   def calculate_value(factor: float, basis: int = 10) -> float:
       return basis * factor
   ```
3. **Explicit Error Handling**:
   - Do not catch generic exceptions (`except Exception:`), unless they are logged and the program is terminated controlled.
   - Define custom exception classes for business-level errors.
   - The CLI layer catches exceptions and outputs user-friendly error messages (formatted in red) instead of showing a traceback (unless in `--debug` mode).
4. **Configuration**: Parameters and paths should be configurable via environment variables (e.g., using `python-dotenv`) or configuration files (TOML/JSON), not hardcoded.

---

## 2. Linting & Code Quality

We use automated tools to guarantee consistency and correctness.

### Ruff (Linter & Formatter)
[Ruff](https://github.com/astral-sh/ruff) replaces Flake8, Black, isort, and other tools with an extremely fast Go implementation.

Configuration in `pyproject.toml`:
```toml
[tool.ruff]
line-length = 88
target-version = "py310"

[tool.ruff.lint]
select = [
    "E",   # pycodestyle errors
    "W",   # pycodestyle warnings
    "F",   # Pyflakes
    "I",   # isort (import sorting)
    "C90", # mccabe (complexity)
    "B",   # flake8-bugbear
    "UP",  # pyupgrade (modern syntax)
]
ignore = []
```

### Mypy (Static Type Checking)
Static typing prevents runtime errors beforehand. Mypy should be strictly configured:
```toml
[tool.mypy]
python_version = "3.10"
strict = true
warn_unused_configs = true
```

### Git Pre-Commit Hooks
Use `pre-commit` to enforce formatting and linting before each commit:
```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/astral-sh/ruff-pre-commit
    rev: v0.1.0
    hooks:
      - id: ruff
        args: [ --fix ]
      - id: ruff-format
```

---

## 3. Testing

Code without tests is considered broken. CLI applications require both unit tests for logic and integration tests for the user interface.

### Test Framework
We use **[pytest](https://docs.pytest.org/)**.

### Core Testing Rules
1. **Test Logic in Isolation**: Test the core logic in `core.py` without triggering CLI inputs/outputs.
2. **Test CLI Interaction**:
   - Use `capsys` (standard in Pytest) to verify standard output (`stdout`) and standard error (`stderr`).
   - Use the `CliRunner` (if using Click/Typer) for simple integration tests.
3. **Mocking**: External API calls, file system accesses, or time-consuming processes must be mocked (e.g., with `unittest.mock` or `pytest-mock`).

### Testing Examples

**CLI Test with Click/Typer:**
```python
from click.testing import CliRunner
from my_project.cli import app

def test_cli_greeting():
    runner = CliRunner()
    result = runner.invoke(app, ["--name", "Alice"])
    assert result.exit_code == 0
    assert "Hello Alice" in result.output
```

**CLI Test with Standard `capsys` & `pytest`:**
```python
from my_project.cli import main
import pytest

def test_main_output(capsys):
    # Simulate program execution
    main(["--version"])
    captured = capsys.readouterr()
    assert "Version 1.0.0" in captured.out
```

---

## 4. Commenting & Documentation

Code should be written in a way that is mostly self-documenting. Comments explain the **Why**, not the **What**.

### Docstrings
Every module, class, and public method/function **must** have a Google-Style docstring.

```python
def read_file(file_path: str, ignore_if_empty: bool = False) -> list[str]:
    """Reads the content of a text file line by line.

    Args:
        file_path: The absolute or relative path to the target file.
        ignore_if_empty: If True, does not raise an error for an empty file,
            instead returns an empty list.

    Returns:
        A list of strings, representing the lines of the file.

    Raises:
        FileNotFoundError: If the file does not exist at the specified path.
        ValueError: If the file is empty and `ignore_if_empty` is False.
    """
    # Logic here...
```

### Inline Comments
- Use inline comments sparingly.
- Describe complex algorithms or design decisions (e.g., *"Why was this specific workaround chosen?"*).
- Avoid trivial comments like:
  ```python
  x = x + 1  # Increase x by 1 (NO!)
  ```

### Terminal Help Texts
The CLI itself is the primary documentation for the user.
- Ensure that every CLI command, argument, and option has a descriptive `help` text.
- Typer/Click automatically generate help pages from these definitions (`--help`).

```python
@app.command()
def import_data(
    file_path: Path = typer.Option(..., help="Path to the CSV file to import"),
):
    """Imports customer and order data from a CSV file into the local database."""
    pass
```
