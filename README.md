# pita - Python Interactive Testing Agent

**pita** is an Agentic QA system designed for autonomous browser testing in Python. It allows testers and developers to verify web applications (specifically dynamic SPAs built with Vue.js and HTMX) using natural language instructions ("Soft Prompts").

Instead of relying on hardcoded CSS selectors and rigid assertions, the system leverages a local or cloud-based Large Language Model (LLM) via LiteLLM to analyze the DOM, decide actions, and document any bugs or failures.

---

## Features

- **Hexagonal Architecture**: Strict separation of concerns between user interface (Textual TUI), domain orchestrator (Core Agent), and external dependencies (Playwright, LiteLLM).
- **DOM Pruning**: In-browser JavaScript engine that filters the full DOM tree $\mathcal{O}(V+E)$ down to visible and interactive nodes $\mathcal{O}(N)$, preserving context window limits.
- **Chain-of-Thought (CoT)**: Enforces detailed text-based reasoning before any actions are executed, preventing local LLM hallucinations.
- **Playwright Tracing & Screenshots**: Saves page-state screenshots for every single step and compiles a complete `trace.zip` record containing network requests, console logs, and snapshot views.
- **Dynamic Waiting**: Automatically waits for network settle states (`networkidle`) and dynamic HTMX/Vue.js swaps.

---

## Prerequisites

- **Python**: Version 3.11 or higher (developed and tested with Python 3.12.10)
- **Model Access**: A local model running via Ollama, or API keys for cloud providers (such as OpenAI or Anthropic).

---

## Installation & Setup

Follow these steps to set up the application locally:

### 1. Clone the Repository and Navigate to the Folder
```powershell
cd /path/to/pita
```

### 2. Create and Activate a Virtual Environment
```powershell
# Create the virtual environment
python -m venv .venv

# Activate on Windows (PowerShell)
.venv\Scripts\Activate.ps1

# Activate on Windows (CMD)
.venv\Scripts\activate.bat

# Activate on macOS/Linux
source .venv/bin/activate
```

### 3. Install Dependencies
```powershell
pip install -r requirements.txt
```

### 4. Install Playwright Browser Binaries
```powershell
playwright install chromium
```

### 5. Configure Environment Variables
Create a `.env` file in the project root directory and add your provider keys (e.g. if using OpenAI):
```env
OPENAI_API_KEY=your-openai-api-key-here
```
*Note: If using a local Ollama model, you don't need to specify an API key. Ensure your local Ollama service is running (default port is `http://localhost:11434`).*

---

## Running the Application

### Launch the Terminal UI (TUI)
Run the interactive console dashboard with:
```powershell
python src/main.py
```

### How to use the TUI:
1. **Target URL**: Enter the web page you wish to test (e.g., a login form).
2. **Task Description (Soft Prompt)**: Write your testing goal in plain English. Example:
   > *Log in with username 'tomsmith' and password 'SuperSecretPassword!', then verify that the secure area is loaded.*
3. **LLM Model**: Type in the LiteLLM model identifier (e.g. `openai/gpt-4o`, `openai/gpt-4-turbo` or `ollama/llama3` for local Ollama instances).
4. **Ollama / API Base URL (Optional)**: If using local Ollama, provide the endpoint address (e.g., `http://localhost:11434`). Leave empty for standard cloud API keys.
5. **Max Steps**: Set a limit for the maximum allowed step loop iterations.
6. **Start Run**: Press the button or Enter to launch the agent.
7. **UI Controls**:
   - The TUI displays real-time status at the top-right and live color-coded logs (thoughts, actions, results) at the bottom-right.
   - Press **C** to clear the Log screen.
   - Press **Q** (or `Ctrl+C` in your terminal shell) to quit the application.

---

## Traces & Reports

After each test run, a timestamped folder is generated inside `test_reports/run_YYYYMMDD_HHMMSS/` containing:
- `report.json`: Chronological audit log detailing executed steps, selectors, LLM reasons, and durations.
- `step_N.png`: Screenshot of the page captured before each action.
- `trace.zip`: A Playwright trace record. Open it for step-by-step interactive browser debugging with:
  ```powershell
  playwright show-trace test_reports/run_DATE_TIME/trace.zip
  ```

---

## Quality Assurance & Testing

The project maintains high code-quality standards using the Ruff linter, Mypy type-checking, and Pytest suites.

### 1. Run Linter Checks (Ruff)
```powershell
ruff check src tests
```

### 2. Run Static Type Checking (Mypy)
```powershell
mypy src tests
```

### 3. Run Automated Tests (Pytest)
The test suite executes unit validations on models, JSON extraction logic, and an integration test that boots a zero-dependency mock HTTP server to run a full Playwright page lifecycle:
```powershell
pytest -v
```
