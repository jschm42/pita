"""Unit tests for the LLMClient and structured JSON response parsing."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from src.core.exceptions import LLMResponseParseError
from src.core.models import ElementNode
from src.infrastructure.llm_client import LLMClient


def test_clean_and_parse_json_valid() -> None:
    """Verifies parsing of standard JSON and markdown-wrapped JSON."""
    client = LLMClient()

    # Raw standard JSON
    raw_json = '{"reasoning": "thought", "action_type": "click", "element_id": "qa-1"}'
    parsed = client._clean_and_parse_json(raw_json)
    assert parsed["action_type"] == "click"
    assert parsed["element_id"] == "qa-1"

    # Markdown json wrapped JSON
    wrapped_json = '```json\n{"reasoning": "thought", "action_type": "wait"}\n```'
    parsed = client._clean_and_parse_json(wrapped_json)
    assert parsed["action_type"] == "wait"

    # Braced JSON with prefix text
    conversational_json = (
        'Here is the action: {"reasoning": "thought", "action_type": "done"}'
    )
    parsed = client._clean_and_parse_json(conversational_json)
    assert parsed["action_type"] == "done"


def test_clean_and_parse_json_invalid() -> None:
    """Verifies that malformed JSON raises LLMResponseParseError."""
    client = LLMClient()

    bad_json = "{'reasoning': 'missing double quotes', action_type: click}"
    with pytest.raises(LLMResponseParseError):
        client._clean_and_parse_json(bad_json)


@pytest.mark.asyncio
@patch("src.infrastructure.llm_client.litellm.acompletion")
async def test_get_next_action_call(mock_acompletion: AsyncMock) -> None:
    """Verifies that acompletion is called and response is mapped successfully."""
    # Setup mock response choice
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = """```json
    {
        "reasoning": "Form submission button is visible",
        "action_type": "click",
        "element_id": "qa-2"
    }
    ```"""
    mock_response.choices = [mock_choice]
    mock_acompletion.return_value = mock_response

    client = LLMClient(model="openai/gpt-4o")

    elements = [ElementNode(id="qa-2", tag="button", text="Submit", selector="button")]

    action = await client.get_next_action(
        task_description="Submit the form",
        current_url="https://test.com/form",
        elements=elements,
        history=["Step 1 text"],
    )

    assert action.action_type == "click"
    assert action.element_id == "qa-2"
    assert "Form submission" in action.reasoning

    # Assert model parameter is passed correctly
    mock_acompletion.assert_called_once()
    called_kwargs = mock_acompletion.call_args[1]
    assert called_kwargs["model"] == "openai/gpt-4o"
    assert called_kwargs["temperature"] == 0.1


@pytest.mark.asyncio
@patch("src.infrastructure.llm_client.litellm.acompletion")
async def test_get_next_action_with_credentials(
    mock_acompletion: AsyncMock,
) -> None:
    """Verifies that credentials format helper works and credentials are in prompt."""
    mock_response = MagicMock()
    mock_choice = MagicMock()
    mock_choice.message.content = (
        '{"reasoning": "Goal achieved", "action_type": "done"}'
    )
    mock_response.choices = [mock_choice]
    mock_acompletion.return_value = mock_response

    client = LLMClient(model="openai/gpt-4o")

    # Directly check formatting helper
    formatted = client._format_credentials(
        {"username": "admin", "password": "password123"}
    )
    assert "username: 'admin'" in formatted
    assert "password: 'password123'" in formatted

    await client.get_next_action(
        task_description="Submit form",
        current_url="https://test.com/login",
        elements=[],
        history=[],
        credentials={"username": "admin", "password": "password123"},
    )

    mock_acompletion.assert_called_once()
    called_kwargs = mock_acompletion.call_args[1]
    messages = called_kwargs["messages"]
    user_prompt = messages[1]["content"]
    assert "AVAILABLE CREDENTIALS" in user_prompt
    assert "username: 'admin'" in user_prompt
    assert "password: 'password123'" in user_prompt
