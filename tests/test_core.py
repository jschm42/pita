"""Unit tests for core models and agent loop logic."""

from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

from src.core.agent import QABrowserAgent
from src.core.models import ActionIntent, ElementNode
from src.infrastructure.browser_service import BrowserService
from src.infrastructure.llm_client import LLMClient


def test_models_serialization() -> None:
    """Verifies Pydantic validation and serializations."""
    node = ElementNode(
        id="qa-1",
        tag="button",
        text="Submit",
        attributes={"type": "submit"},
        selector="button[data-qa-id='qa-1']",
    )
    assert node.id == "qa-1"
    assert node.attributes["type"] == "submit"

    action = ActionIntent(
        reasoning="I need to click the submit button.",
        action_type="click",
        element_id="qa-1",
    )
    assert action.action_type == "click"
    assert action.element_id == "qa-1"


@pytest.mark.asyncio
async def test_agent_run_loop_success() -> None:
    """Verifies that the agent loop runs and terminates on 'done' successfully."""
    # Setup mocks
    mock_browser = MagicMock(spec=BrowserService)
    mock_browser.page = MagicMock()
    mock_browser.navigate = AsyncMock(return_value="https://test.com/home")

    # First step returns elements, second step is just termination
    elements_step_1 = [
        ElementNode(
            id="qa-1", tag="button", text="Login", selector="[data-qa-id='qa-1']"
        )
    ]
    mock_browser.prune_dom = AsyncMock(return_value=elements_step_1)
    mock_browser.capture_screenshot = AsyncMock()
    mock_browser.start_tracing = AsyncMock()
    mock_browser.stop_tracing = AsyncMock()
    mock_browser.click = AsyncMock()
    mock_browser.stop = AsyncMock()

    mock_llm = MagicMock(spec=LLMClient)

    # LLM responses: Step 1 click button, Step 2 mark done
    intent_1 = ActionIntent(
        reasoning="Need to click login", action_type="click", element_id="qa-1"
    )
    intent_2 = ActionIntent(reasoning="Goal achieved", action_type="done")
    mock_llm.get_next_action = AsyncMock(side_effect=[intent_1, intent_2])

    agent = QABrowserAgent(mock_browser, mock_llm)

    callback_events = []

    def callback(event_type: str, data: dict[str, Any]) -> None:
        callback_events.append((event_type, data))

    report = await agent.run_task(
        target_url="https://test.com",
        task_description="Click login and complete",
        max_steps=5,
        update_callback=callback,
    )

    # Verification assertions
    assert report.status == "success"
    assert len(report.steps) == 2
    assert report.steps[0].action.action_type == "click"
    assert report.steps[1].action.action_type == "done"

    mock_browser.navigate.assert_called_once_with("https://test.com")
    mock_browser.click.assert_called_once_with("[data-qa-id='qa-1']")
    mock_browser.stop.assert_called_once()

    # Check that status and log events were fired
    assert any(event == "status" for event, _ in callback_events)
    assert any(event == "log" for event, _ in callback_events)


@pytest.mark.asyncio
async def test_agent_run_loop_passes_credentials() -> None:
    """Verifies that credentials dictionary is passed to the LLM client during the run."""
    # Setup mocks
    mock_browser = MagicMock(spec=BrowserService)
    mock_browser.page = MagicMock()
    mock_browser.navigate = AsyncMock(return_value="https://test.com/home")
    mock_browser.prune_dom = AsyncMock(return_value=[])
    mock_browser.capture_screenshot = AsyncMock()
    mock_browser.start_tracing = AsyncMock()
    mock_browser.stop_tracing = AsyncMock()
    mock_browser.stop = AsyncMock()

    mock_llm = MagicMock(spec=LLMClient)
    intent = ActionIntent(reasoning="Task done", action_type="done")
    mock_llm.get_next_action = AsyncMock(return_value=intent)

    agent = QABrowserAgent(mock_browser, mock_llm)
    credentials = {"username": "test_user", "password": "test_password"}

    await agent.run_task(
        target_url="https://test.com",
        task_description="Click login and complete",
        max_steps=5,
        credentials=credentials,
    )

    # Verify that get_next_action was called with the credentials dict
    mock_llm.get_next_action.assert_called_once()
    called_kwargs = mock_llm.get_next_action.call_args[1]
    assert called_kwargs["credentials"] == credentials
